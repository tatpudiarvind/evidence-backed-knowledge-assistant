"""Finding a question's evidence in each retrieval mode (P7-04, P7-05, P7-06; D-81), with a
stand-in for the chunk repository, so the fusion, the evidence gate, and the reranker's fallback
are tested without a database. The searches themselves are tested against PostgreSQL in
test_hybrid_search.py."""

import logging
import math
import uuid
from collections.abc import Sequence
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session

from app.core.metrics import Metrics
from app.domain.questions import Passage
from app.providers.rerankers import RerankerUnavailableError
from app.services import retrieval
from app.services.retrieval import RankedPassage, retrieve
from tests.support import make_settings, sample_value

WORKSPACE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
QUESTION = "How long are project records kept?"
VECTOR = [1.0, 0.0]
FAILURES = "knowledge_assistant_reranker_failures_total"


def passage(name: str, similarity: float) -> Passage:
    return Passage(
        chunk_id=uuid.uuid5(uuid.NAMESPACE_URL, name),
        document_id=uuid.uuid5(uuid.NAMESPACE_DNS, name),
        document_name=f"{name}.txt",
        text=f"The text of {name}.",
        page_number=None,
        section=None,
        similarity=similarity,
    )


A, B, C, D, E = (
    passage("a", 0.9),
    passage("b", 0.8),
    passage("c", 0.45),
    passage("d", 0.6),
    passage("e", 0.3),
)


class FakeSession:
    def __init__(self) -> None:
        self.rollbacks = 0

    def rollback(self) -> None:
        self.rollbacks += 1


class FakeChunks:
    """Stands in for app.repositories.chunks, recording each search."""

    def __init__(
        self,
        by_meaning: Sequence[Passage] = (),
        by_words: Sequence[Passage] = (),
        *,
        has_chunks: bool = True,
    ) -> None:
        self.by_meaning = list(by_meaning)
        self.by_words = list(by_words)
        self.has_chunks = has_chunks
        self.calls: list[tuple[Any, ...]] = []

    def search_workspace(
        self,
        session: object,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        vector: Sequence[float],
        limit: int,
    ) -> list[Passage]:
        self.calls.append(("vector", workspace_id, user_id, list(vector), limit))
        return self.by_meaning[:limit]

    def keyword_search(
        self,
        session: object,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        query: str,
        vector: Sequence[float],
        limit: int,
    ) -> list[Passage]:
        self.calls.append(("keyword", workspace_id, user_id, query, list(vector), limit))
        return self.by_words[:limit]

    def workspace_has_indexed_chunks(
        self, session: object, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        self.calls.append(("has_chunks", workspace_id, user_id))
        return self.has_chunks


class FakeReranker:
    """Scores the texts it's given with set scores, or fails, recording each call."""

    name = "fake-reranker"

    def __init__(self, scores: Sequence[object] = (), *, fail: bool = False) -> None:
        self.scores = list(scores)
        self.fail = fail
        self.calls: list[tuple[str, list[str], int]] = []
        self.session: FakeSession | None = None

    def score(self, question: str, texts: Sequence[str]) -> list[float]:
        # How many times the session had ended its transaction when the reranker ran.
        rollbacks = self.session.rollbacks if self.session else -1
        self.calls.append((question, list(texts), rollbacks))
        if self.fail:
            raise RerankerUnavailableError(self.name)
        return cast(list[float], list(self.scores))


def run(
    chunks: FakeChunks,
    monkeypatch: pytest.MonkeyPatch,
    *,
    question: str = QUESTION,
    reranker: FakeReranker | None = None,
    metrics: Metrics | None = None,
    **overrides: Any,
) -> retrieval.RetrievalResult:
    monkeypatch.setattr(retrieval, "chunk_repository", chunks)
    values: dict[str, Any] = {
        "retrieval_top_k": 2,
        "retrieval_candidates": 3,
        "retrieval_min_similarity": 0.5,
    }
    values.update(overrides)
    session = FakeSession()
    if reranker is not None:
        reranker.session = session
    result = retrieve(
        cast(Session, session),
        WORKSPACE_ID,
        USER_ID,
        question,
        VECTOR,
        settings=make_settings(**values),
        reranker=reranker,
        metrics=metrics,
    )
    # The read transaction always ends, so no connection is held afterwards.
    assert session.rollbacks == 1
    return result


def names(ranked: Sequence[RankedPassage]) -> list[str]:
    return [entry.passage.document_name.removesuffix(".txt") for entry in ranked]


def failures(metrics: Metrics) -> float | None:
    body, _ = metrics.exposition("")
    return sample_value(body.decode(), FAILURES)


def test_vector_mode_keeps_the_closest_passages_above_the_minimum_similarity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks = FakeChunks([A, D, C], [E])
    reranker = FakeReranker()

    result = run(chunks, monkeypatch, reranker=reranker, retrieval_top_k=3)

    assert result.mode == "vector"
    assert chunks.calls == [("vector", WORKSPACE_ID, USER_ID, VECTOR, 3)]
    assert result.candidates == 3
    assert result.ranked == (RankedPassage(A, 1, None), RankedPassage(D, 2, None))
    assert result.evidence == (A, D)
    assert result.has_documents is True
    assert (result.keyword_matches, result.keyword_dropped, result.rerank_failed) == (0, 0, False)
    assert reranker.calls == []


@pytest.mark.parametrize("mode", ["vector", "hybrid", "hybrid_rerank"])
@pytest.mark.parametrize("has_chunks", [True, False])
def test_without_passages_the_index_says_whether_there_are_documents(
    monkeypatch: pytest.MonkeyPatch, mode: str, has_chunks: bool
) -> None:
    chunks = FakeChunks(has_chunks=has_chunks)
    reranker = FakeReranker()

    result = run(chunks, monkeypatch, reranker=reranker, retrieval_mode=mode)

    assert result.has_documents is has_chunks
    assert chunks.calls[-1] == ("has_chunks", WORKSPACE_ID, USER_ID)
    assert (result.candidates, result.ranked, result.evidence) == (0, (), ())
    # Nothing to reorder, so the reranker isn't asked and hasn't failed.
    assert reranker.calls == []
    assert result.rerank_failed is False


def test_hybrid_fuses_both_searches_after_dropping_weak_passages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # By meaning: a, b, then c below the minimum. By words: d, b, then e below the minimum.
    chunks = FakeChunks([A, B, C], [D, B, E])
    reranker = FakeReranker()

    result = run(chunks, monkeypatch, reranker=reranker, retrieval_mode="hybrid")

    assert chunks.calls == [
        ("vector", WORKSPACE_ID, USER_ID, VECTOR, 3),
        (
            "keyword",
            WORKSPACE_ID,
            USER_ID,
            "How or long or are or project or records or kept",
            VECTOR,
            3,
        ),
    ]
    # b is in both rankings, at 2nd each. a and d tie at 1st in one ranking; a was seen first.
    assert result.ranked == (
        RankedPassage(B, 2, 2, 1 / 62 + 1 / 62),
        RankedPassage(A, 1, None, 1 / 61),
        RankedPassage(D, None, 1, 1 / 61),
    )
    assert result.evidence == (B, A)
    assert result.candidates == 5
    assert (result.keyword_matches, result.keyword_dropped) == (3, 1)
    assert result.has_documents is True
    assert result.rerank_failed is False
    assert reranker.calls == []


def test_rrf_k_is_a_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    result = run(FakeChunks([A], [A]), monkeypatch, retrieval_mode="hybrid", rrf_k=1)

    assert [entry.fused_score for entry in result.ranked] == [1.0]


def test_a_passage_found_only_by_its_words_can_be_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = run(FakeChunks([], [D]), monkeypatch, retrieval_mode="hybrid")

    assert result.ranked == (RankedPassage(D, None, 1, 1 / 61),)
    assert result.evidence == (D,)


def test_the_minimum_similarity_applies_to_keyword_matches_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = run(FakeChunks([], [C, E]), monkeypatch, retrieval_mode="hybrid")

    assert result.evidence == ()
    assert (result.keyword_matches, result.keyword_dropped) == (2, 2)
    assert result.has_documents is True


@pytest.mark.parametrize("question", ["?!", "or", "-- ''"])
def test_a_question_without_words_is_searched_by_meaning_only(
    monkeypatch: pytest.MonkeyPatch, question: str
) -> None:
    chunks = FakeChunks([A], [D])

    result = run(chunks, monkeypatch, question=question, retrieval_mode="hybrid")

    assert [call[0] for call in chunks.calls] == ["vector"]
    assert result.ranked == (RankedPassage(A, 1, None, 1 / 61),)
    assert result.keyword_matches == 0


def test_hybrid_rerank_reorders_the_fused_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    # The fused order is b, a, d; the reranker likes a best, then d.
    reranker = FakeReranker([0.1, 0.9, 0.5])
    metrics = Metrics()

    result = run(
        FakeChunks([A, B, C], [D, B, E]),
        monkeypatch,
        reranker=reranker,
        metrics=metrics,
        retrieval_mode="hybrid_rerank",
    )

    # Every fused candidate is scored once, after the read transaction ended.
    assert reranker.calls == [(QUESTION, [B.text, A.text, D.text], 1)]
    assert result.ranked == (
        RankedPassage(A, 1, None, 1 / 61, 0.9),
        RankedPassage(D, None, 1, 1 / 61, 0.5),
        RankedPassage(B, 2, 2, 1 / 62 + 1 / 62, 0.1),
    )
    assert result.evidence == (A, D)
    assert result.rerank_failed is False
    assert failures(metrics) == 0


def test_equal_reranker_scores_keep_the_fused_order(monkeypatch: pytest.MonkeyPatch) -> None:
    result = run(
        FakeChunks([A, B], [D, B]),
        monkeypatch,
        reranker=FakeReranker([2.0, 2.0, 2.0]),
        retrieval_mode="hybrid_rerank",
    )

    assert names(result.ranked) == ["b", "a", "d"]
    assert [entry.rerank_score for entry in result.ranked] == [2.0, 2.0, 2.0]


@pytest.mark.parametrize(
    ("reranker", "warning"),
    [
        (None, "the reranker failed"),
        (FakeReranker(fail=True), "the reranker failed"),
        (FakeReranker([0.9, 0.1]), "the reranker returned unusable scores"),
        (FakeReranker([0.9, 0.1, 0.5, 0.7]), "the reranker returned unusable scores"),
        (FakeReranker([0.9, math.nan, 0.5]), "the reranker returned unusable scores"),
        (FakeReranker([0.9, math.inf, 0.5]), "the reranker returned unusable scores"),
        (FakeReranker([3, 1, 2]), "the reranker returned unusable scores"),
        (FakeReranker(["0.9", "0.1", "0.5"]), "the reranker returned unusable scores"),
    ],
    ids=[
        "none",
        "unavailable",
        "too-few",
        "too-many",
        "not-a-number",
        "infinite",
        "integers",
        "strings",
    ],
)
def test_a_failed_reranker_keeps_the_fused_order_and_is_counted(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    reranker: FakeReranker | None,
    warning: str,
) -> None:
    metrics = Metrics()
    caplog.set_level(logging.WARNING, logger="app.services.retrieval")

    result = run(
        FakeChunks([A, B, C], [D, B, E]),
        monkeypatch,
        reranker=reranker,
        metrics=metrics,
        retrieval_mode="hybrid_rerank",
    )

    assert names(result.ranked) == ["b", "a", "d"]
    assert all(entry.rerank_score is None for entry in result.ranked)
    assert result.evidence == (B, A)
    assert result.rerank_failed is True
    assert failures(metrics) == 1
    assert f"Kept the fused order, because {warning}" in caplog.text
    # Never the question or the passages.
    assert QUESTION not in caplog.text
    assert A.text not in caplog.text


def test_a_failed_reranker_needs_no_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    result = run(
        FakeChunks([A], []),
        monkeypatch,
        reranker=FakeReranker(fail=True),
        retrieval_mode="hybrid_rerank",
    )

    assert result.rerank_failed is True
    assert result.evidence == (A,)


def test_without_candidates_above_the_minimum_the_reranker_is_not_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reranker = FakeReranker(fail=True)
    metrics = Metrics()

    result = run(
        FakeChunks([C], [E]),
        monkeypatch,
        reranker=reranker,
        metrics=metrics,
        retrieval_mode="hybrid_rerank",
    )

    assert reranker.calls == []
    assert result.evidence == ()
    assert result.rerank_failed is False
    assert failures(metrics) == 0
    assert result.has_documents is True
