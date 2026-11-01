"""Hybrid search with PostgreSQL (P7-03 - P7-06; D-81).

Migration 0006's keyword index, the keyword search over it, and questions in each retrieval
mode: how the two searches' rankings merge, how the reranker reorders them or is bypassed when
it fails, and that every mode applies the same minimum similarity and searches only the ready
documents of the workspace asked about, for its members.

`PlannedEmbeddings` gives each passage a set similarity to every question, so the ranking by
meaning is known exactly, and `LengthReranker` stands in for the cross-encoder.
test_robustness.py runs its tests in every mode as well.
"""

import logging
import math
import uuid
from collections.abc import Callable, Sequence
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, update
from sqlalchemy.pool import NullPool

from alembic import command
from app.db.maintenance import run_alembic
from app.db.models import Document, WorkspaceMembership
from app.domain.indexing import EMBEDDING_DIMENSION
from app.domain.questions import Passage
from app.domain.retrieval import RETRIEVAL_MODES, keyword_query
from app.repositories import chunks as chunk_repository
from app.services.retrieval import RetrievalResult, retrieve
from tests.support import (
    HashingEmbeddings,
    LengthReranker,
    Workspace,
    ask,
    create_workspace,
    error_code,
    metric_value,
    register,
)

pytestmark = pytest.mark.integration

# Its words for the keyword search are room, badge, XQ7731, and open; the others are stop words.
QUESTION = "Which room does badge XQ7731 open?"
BADGE_TEXT = "Badge XQ7731 opens the archive room."
CLOSE_TEXT = "Visitors sign in at the front desk before each meeting."
LONG_TEXT = (
    "The cafeteria on the ground floor serves breakfast from seven and lunch from noon until two."
)
FAR_TEXT = "Lost badges are replaced by the security office."
CHECK_TEXT = "Each badge is checked at the door."
LUNCH_TEXT = "Lunch is served at noon."
# Each office passage's similarity to every question. With the minimum of 0.5, the closest
# passage has none of the question's words, the badge passage has all four, the cafeteria
# passage is the longest, and the lost-badges passage is too far in meaning to count.
SIMILARITIES = {CLOSE_TEXT: 0.9, BADGE_TEXT: 0.6, LONG_TEXT: 0.55, FAR_TEXT: 0.3}
OFFICE_FILES = {
    "visitors.txt": CLOSE_TEXT,
    "badges.txt": BADGE_TEXT,
    "cafeteria.txt": LONG_TEXT,
    "lost.txt": FAR_TEXT,
}
RERANKER_FAILURES = "knowledge_assistant_reranker_failures_total"


def planned_vector(similarity: float) -> list[float]:
    """A unit vector whose cosine similarity to `QUESTION_VECTOR` is `similarity`."""
    vector = [0.0] * EMBEDDING_DIMENSION
    vector[0], vector[1] = similarity, math.sqrt(1 - similarity**2)
    return vector


QUESTION_VECTOR = planned_vector(1.0)


class PlannedEmbeddings(HashingEmbeddings):
    """Gives each passage the similarity to every question that the test planned for it."""

    def __init__(self, similarities: dict[str, float] | None = None) -> None:
        super().__init__()
        self.similarities = SIMILARITIES if similarities is None else similarities

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.document_batches.append(list(texts))
        return [planned_vector(self.similarities[text]) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return QUESTION_VECTOR


def new_workspace(
    make_workspace: Callable[..., Workspace], mode: str, **overrides: Any
) -> Workspace:
    """A workspace in an app in `mode`, with the office passages' planned similarities. In
    `hybrid_rerank` mode, the app has a `LengthReranker` unless the test gives a reranker."""
    overrides.setdefault("embeddings", PlannedEmbeddings())
    if mode == "hybrid_rerank":
        overrides.setdefault("reranker", LengthReranker())
    return make_workspace(retrieval_mode=mode, **overrides)


def add_office(workspace: Workspace) -> None:
    for filename, text in OFFICE_FILES.items():
        workspace.add(filename, text.encode())


def member_id(workspace: Workspace) -> uuid.UUID:
    """The id of the workspace's only member, the user who created it."""
    with workspace.app.state.session_factory() as session:
        user_id: uuid.UUID = session.scalars(
            select(WorkspaceMembership.user_id).where(
                WorkspaceMembership.workspace_id == uuid.UUID(workspace.id)
            )
        ).one()
    return user_id


def found_by_words(
    workspace: Workspace, question: str, user_id: uuid.UUID | None = None
) -> list[Passage]:
    """What the keyword search finds for a question, for the workspace's member by default."""
    user_id = user_id or member_id(workspace)
    with workspace.app.state.session_factory() as session:
        return chunk_repository.keyword_search(
            session,
            uuid.UUID(workspace.id),
            user_id,
            keyword_query(question),
            QUESTION_VECTOR,
            20,
        )


def retrieved(workspace: Workspace, question: str, **options: Any) -> RetrievalResult:
    """A question's evidence for the workspace's member, with the app's settings by default."""
    options.setdefault("settings", workspace.app.state.settings)
    user_id = member_id(workspace)
    with workspace.app.state.session_factory() as session:
        return retrieve(
            session, uuid.UUID(workspace.id), user_id, question, QUESTION_VECTOR, **options
        )


def set_status(app: FastAPI, document_id: str, status: str) -> None:
    with app.state.session_factory() as session:
        session.execute(
            update(Document).where(Document.id == uuid.UUID(document_id)).values(status=status)
        )
        session.commit()


def keyword_index(database_url: str) -> tuple[list[str], list[str]]:
    """The names of document_chunks' search_vector column and of its GIN indexes."""
    engine = create_engine(database_url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            columns = [
                column["name"]
                for column in inspector.get_columns("document_chunks")
                if column["name"] == "search_vector"
            ]
            indexes = [
                str(index["name"])
                for index in inspector.get_indexes("document_chunks")
                if index.get("dialect_options", {}).get("postgresql_using") == "gin"
            ]
    finally:
        engine.dispose()
    return columns, indexes


def test_migration_0006_adds_the_keyword_index_and_fills_it_for_existing_chunks(
    make_workspace: Callable[..., Workspace], database_url: str
) -> None:
    workspace = new_workspace(make_workspace, "hybrid")
    workspace.add("badges.txt", BADGE_TEXT.encode())
    # So that no pooled connection holds a lock, or a prepared statement, across the migrations.
    workspace.app.state.engine.dispose()

    try:
        run_alembic(
            database_url, lambda config: command.downgrade(config, "0005_questions_answers")
        )
        downgraded = keyword_index(database_url)
    finally:
        run_alembic(database_url, lambda config: command.upgrade(config, "head"))

    assert downgraded == ([], [])
    assert keyword_index(database_url) == (["search_vector"], ["ix_document_chunks_search_vector"])
    # PostgreSQL filled the new column for the chunk indexed before it existed.
    assert [passage.text for passage in found_by_words(workspace, QUESTION)] == [BADGE_TEXT]


def test_keyword_search_ranks_passages_with_more_of_the_question_s_words_first(
    make_workspace: Callable[..., Workspace],
) -> None:
    embeddings = PlannedEmbeddings(
        {BADGE_TEXT: 0.2, FAR_TEXT: 0.7, CHECK_TEXT: 0.9, LUNCH_TEXT: 0.95}
    )
    workspace = new_workspace(make_workspace, "hybrid", embeddings=embeddings)
    for number, text in enumerate(embeddings.similarities, 1):
        workspace.add(f"note-{number}.txt", text.encode())

    passages = found_by_words(workspace, QUESTION)

    # The passage with all four words comes first, though it's the furthest in meaning. Of those
    # with one word each, the closer comes first, and "badges" counts as "badge". The closest
    # passage of all has none of the words, so it isn't found. Similarities are as planned.
    assert [(passage.text, round(passage.similarity, 4)) for passage in passages] == [
        (BADGE_TEXT, 0.2),
        (CHECK_TEXT, 0.9),
        (FAR_TEXT, 0.7),
    ]


def test_a_question_of_stop_words_is_searched_by_meaning_alone(
    make_workspace: Callable[..., Workspace],
) -> None:
    workspace = new_workspace(make_workspace, "hybrid", retrieval_top_k=2)
    add_office(workspace)
    question = "What is it about?"

    result = retrieved(workspace, question)

    assert keyword_query(question) == "What or is or it or about"
    assert found_by_words(workspace, question) == []
    assert [
        (entry.passage.text, entry.vector_rank, entry.keyword_rank) for entry in result.ranked
    ] == [
        (CLOSE_TEXT, 1, None),
        (BADGE_TEXT, 2, None),
        (LONG_TEXT, 3, None),
    ]
    assert [passage.text for passage in result.evidence] == [CLOSE_TEXT, BADGE_TEXT]
    assert (result.keyword_matches, result.keyword_dropped) == (0, 0)


def test_keyword_search_covers_only_the_ready_documents_of_a_members_workspace(
    make_workspace: Callable[..., Workspace], make_client: Callable[[FastAPI], TestClient]
) -> None:
    owner = new_workspace(make_workspace, "hybrid")
    owner_document = owner.add("badges.txt", BADGE_TEXT.encode())
    other_client = make_client(owner.app)
    assert register(other_client, "other@example.com").status_code == 201
    other = Workspace(owner.app, other_client, create_workspace(other_client)["id"])
    other_document = other.add("copy.txt", BADGE_TEXT.encode())
    owner_id, other_id = member_id(owner), member_id(other)

    def found(workspace: Workspace, user_id: uuid.UUID) -> list[str]:
        return [
            str(passage.document_id) for passage in found_by_words(workspace, QUESTION, user_id)
        ]

    assert found(owner, owner_id) == [owner_document]
    assert found(other, other_id) == [other_document]
    # Each user's words are in the other's workspace too, but only members find anything.
    assert found(owner, other_id) == []
    assert found(other, owner_id) == []
    set_status(owner.app, owner_document, "failed")
    assert found(owner, owner_id) == []


def test_hybrid_search_merges_both_rankings_by_reciprocal_rank_fusion(
    make_workspace: Callable[..., Workspace],
) -> None:
    workspace = new_workspace(make_workspace, "hybrid", retrieval_top_k=2)
    add_office(workspace)

    result = retrieved(workspace, QUESTION)

    # By meaning: close, badge, cafeteria; by words: badge. The lost-badges passage matches
    # by a word, but is too far in meaning for either list.
    assert [
        (entry.passage.text, entry.vector_rank, entry.keyword_rank) for entry in result.ranked
    ] == [
        (BADGE_TEXT, 2, 1),
        (CLOSE_TEXT, 1, None),
        (LONG_TEXT, 3, None),
    ]
    # RRF_K is 60.
    assert [entry.fused_score for entry in result.ranked] == pytest.approx(
        [1 / 62 + 1 / 61, 1 / 61, 1 / 63]
    )
    assert [entry.rerank_score for entry in result.ranked] == [None, None, None]
    assert [passage.text for passage in result.evidence] == [BADGE_TEXT, CLOSE_TEXT]
    assert (result.mode, result.candidates, result.keyword_matches, result.keyword_dropped) == (
        "hybrid",
        4,
        2,
        1,
    )
    assert result.has_documents is True
    assert result.rerank_failed is False


def test_the_reranker_reorders_the_merged_passages_which_keep_their_ranks(
    make_workspace: Callable[..., Workspace],
) -> None:
    workspace = new_workspace(make_workspace, "hybrid_rerank", retrieval_top_k=2)
    add_office(workspace)
    reranker = LengthReranker()

    result = retrieved(workspace, QUESTION, reranker=reranker)

    # It scores the passages that passed the minimum similarity, in the merged order, once.
    assert reranker.calls == [(QUESTION, [BADGE_TEXT, CLOSE_TEXT, LONG_TEXT])]
    ranked = [
        (entry.passage.text, entry.vector_rank, entry.keyword_rank, entry.rerank_score)
        for entry in result.ranked
    ]
    assert ranked == [
        (LONG_TEXT, 3, None, float(len(LONG_TEXT))),
        (CLOSE_TEXT, 1, None, float(len(CLOSE_TEXT))),
        (BADGE_TEXT, 2, 1, float(len(BADGE_TEXT))),
    ]
    assert [passage.text for passage in result.evidence] == [LONG_TEXT, CLOSE_TEXT]
    assert (result.mode, result.rerank_failed) == ("hybrid_rerank", False)


@pytest.mark.parametrize(
    ("mode", "cited"),
    [
        ("vector", [CLOSE_TEXT, BADGE_TEXT]),
        ("hybrid", [BADGE_TEXT, CLOSE_TEXT]),
        ("hybrid_rerank", [LONG_TEXT, CLOSE_TEXT]),
    ],
)
def test_each_mode_answers_from_the_passages_it_ranks_first(
    make_workspace: Callable[..., Workspace],
    caplog: pytest.LogCaptureFixture,
    mode: str,
    cited: list[str],
) -> None:
    caplog.set_level(logging.INFO)
    workspace = new_workspace(make_workspace, mode, retrieval_top_k=2)
    add_office(workspace)

    question = workspace.ask(QUESTION)

    citations = question["answer"]["citations"]
    assert [citation["excerpt"] for citation in citations] == cited
    assert [citation["number"] for citation in citations] == [1, 2]
    # Whatever the order, each citation gives its passage's similarity to the question.
    for citation in citations:
        expected = SIMILARITIES[citation["excerpt"]]
        assert citation["similarity"] == pytest.approx(expected, abs=1e-4)
    passages = 2 if mode == "vector" else 4
    assert (
        f"Answered question {question['id']}: mode=search_only abstention=none "
        f"retrieval={mode} passages={passages} evidence=2 citations=2"
    ) in caplog.text
    for text in (QUESTION, *SIMILARITIES):
        assert text not in caplog.text
    assert metric_value(workspace.app, RERANKER_FAILURES) == 0
    if mode == "hybrid_rerank":
        assert workspace.app.state.reranker.calls == [
            (QUESTION, [BADGE_TEXT, CLOSE_TEXT, LONG_TEXT])
        ]


def test_when_the_reranker_fails_the_merged_order_is_kept_and_counted(
    make_workspace: Callable[..., Workspace], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    reranker = LengthReranker(fail=True)
    workspace = new_workspace(make_workspace, "hybrid_rerank", retrieval_top_k=2, reranker=reranker)
    add_office(workspace)

    answer = workspace.ask(QUESTION)["answer"]

    assert [citation["excerpt"] for citation in answer["citations"]] == [BADGE_TEXT, CLOSE_TEXT]
    assert answer["abstained"] is False
    assert len(reranker.calls) == 1
    assert metric_value(workspace.app, RERANKER_FAILURES) == 1
    assert "Kept the fused order, because the reranker failed" in caplog.text
    for text in (QUESTION, *SIMILARITIES):
        assert text not in caplog.text


@pytest.mark.parametrize("mode", RETRIEVAL_MODES)
def test_a_passage_with_the_question_s_words_but_far_in_meaning_is_not_evidence(
    make_workspace: Callable[..., Workspace], mode: str
) -> None:
    workspace = new_workspace(make_workspace, mode)
    workspace.add("lost.txt", FAR_TEXT.encode())

    answer = workspace.ask(QUESTION)["answer"]

    assert [passage.text for passage in found_by_words(workspace, QUESTION)] == [FAR_TEXT]
    assert answer["abstention_reason"] == "weak_evidence"
    assert answer["citations"] == []
    if mode == "hybrid_rerank":
        assert workspace.app.state.reranker.calls == []


@pytest.mark.parametrize("mode", RETRIEVAL_MODES)
def test_every_mode_searches_only_the_workspace_asked_about(
    make_workspace: Callable[..., Workspace],
    make_client: Callable[[FastAPI], TestClient],
    mode: str,
) -> None:
    owner = new_workspace(make_workspace, mode)
    owner_document = owner.add("badges.txt", BADGE_TEXT.encode())
    second_workspace = Workspace(owner.app, owner.client, create_workspace(owner.client)["id"])
    other_client = make_client(owner.app)
    assert register(other_client, "other@example.com").status_code == 201
    other = Workspace(owner.app, other_client, create_workspace(other_client)["id"])
    other_document = other.add("copy.txt", BADGE_TEXT.encode())

    owner_citations = owner.ask(QUESTION)["answer"]["citations"]
    other_citations = other.ask(QUESTION)["answer"]["citations"]
    empty_answer = second_workspace.ask(QUESTION)["answer"]

    assert [citation["document_id"] for citation in owner_citations] == [owner_document]
    assert [citation["document_id"] for citation in other_citations] == [other_document]
    assert empty_answer["abstention_reason"] == "no_indexed_documents"
    response = ask(other_client, owner.id, QUESTION)
    assert response.status_code == 404
    assert error_code(response) == "workspace_not_found"
    assert BADGE_TEXT not in response.text


@pytest.mark.parametrize("mode", RETRIEVAL_MODES)
def test_every_mode_searches_only_ready_documents(
    make_workspace: Callable[..., Workspace], mode: str
) -> None:
    workspace = new_workspace(make_workspace, mode)
    document_id = workspace.add("badges.txt", BADGE_TEXT.encode())

    for status in ("queued", "processing", "failed", "deleting"):
        set_status(workspace.app, document_id, status)
        answer = workspace.ask(QUESTION)["answer"]
        assert answer["abstention_reason"] == "no_indexed_documents", status
    set_status(workspace.app, document_id, "ready")
    [citation] = workspace.ask(QUESTION)["answer"]["citations"]
    assert citation["document_id"] == document_id
