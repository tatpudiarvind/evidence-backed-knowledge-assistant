"""Retrieval (Phase 7, D-81): find the passages that count as evidence for a question.

`vector` mode is the search of Phases 4 to 6: the RETRIEVAL_TOP_K passages closest to the
question. The hybrid modes take RETRIEVAL_CANDIDATES passages from each of two searches, by
meaning and by the question's words, drop those below the minimum similarity, and merge the
two rankings by reciprocal rank fusion; `hybrid_rerank` then has a cross-encoder reorder the
merged candidates. Every mode searches only the workspace's ready documents, for its members,
and applies the same minimum similarity, so declines stay comparable.
"""

import logging
import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.metrics import Metrics
from app.domain.questions import Passage
from app.domain.retrieval import RetrievalMode, keyword_query, reciprocal_rank_fusion
from app.providers.rerankers import Reranker, RerankerUnavailableError
from app.repositories import chunks as chunk_repository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RankedPassage:
    passage: Passage
    # The passage's rank among each search's passages that passed the minimum similarity, from
    # 1, or None where that search didn't find it or didn't run.
    vector_rank: int | None
    keyword_rank: int | None
    # Reciprocal rank fusion's score, in the hybrid modes.
    fused_score: float | None = None
    # The cross-encoder's score, in `hybrid_rerank` mode when it ran.
    rerank_score: float | None = None


@dataclass(frozen=True)
class RetrievalResult:
    mode: RetrievalMode
    # How many different passages the searches returned, before the minimum similarity.
    candidates: int
    # The passages that passed the minimum similarity, best first.
    ranked: tuple[RankedPassage, ...]
    # The first RETRIEVAL_TOP_K of them: what the answer is written from.
    evidence: tuple[Passage, ...]
    # Whether the workspace had a ready, indexed document that the member could search.
    has_documents: bool
    # In the hybrid modes: how many passages the keyword search returned, and how many of them
    # the minimum similarity dropped.
    keyword_matches: int = 0
    keyword_dropped: int = 0
    # In `hybrid_rerank` mode: the reranker failed, so the fused order was kept.
    rerank_failed: bool = False


def retrieve(
    session: Session,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    question: str,
    vector: Sequence[float],
    *,
    settings: Settings,
    reranker: Reranker | None = None,
    metrics: Metrics | None = None,
) -> RetrievalResult:
    """Find a question's evidence in the mode that RETRIEVAL_MODE sets.

    `vector` is the question's embedding. The read transaction ends before any reranking, so
    no connection is held while the cross-encoder runs.
    """
    if settings.retrieval_mode == "vector":
        return _by_meaning(session, workspace_id, user_id, vector, settings)
    return _hybrid(session, workspace_id, user_id, question, vector, settings, reranker, metrics)


def _by_meaning(
    session: Session,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    vector: Sequence[float],
    settings: Settings,
) -> RetrievalResult:
    passages = chunk_repository.search_workspace(
        session, workspace_id, user_id, vector, settings.retrieval_top_k
    )
    has_documents = bool(passages) or chunk_repository.workspace_has_indexed_chunks(
        session, workspace_id, user_id
    )
    session.rollback()
    ranked = tuple(
        RankedPassage(passage, rank, None)
        for rank, passage in enumerate(_evidence_only(passages, settings), 1)
    )
    return RetrievalResult(
        mode="vector",
        candidates=len(passages),
        ranked=ranked,
        evidence=tuple(entry.passage for entry in ranked),
        has_documents=has_documents,
    )


def _hybrid(
    session: Session,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    question: str,
    vector: Sequence[float],
    settings: Settings,
    reranker: Reranker | None,
    metrics: Metrics | None,
) -> RetrievalResult:
    limit = settings.retrieval_candidates
    by_meaning = chunk_repository.search_workspace(session, workspace_id, user_id, vector, limit)
    query = keyword_query(question)
    by_words = (
        chunk_repository.keyword_search(session, workspace_id, user_id, query, vector, limit)
        if query
        else []
    )
    has_documents = bool(by_meaning or by_words) or chunk_repository.workspace_has_indexed_chunks(
        session, workspace_id, user_id
    )
    session.rollback()

    meaning_kept = _evidence_only(by_meaning, settings)
    words_kept = _evidence_only(by_words, settings)
    passages: dict[uuid.UUID, Passage] = {}
    for passage in [*meaning_kept, *words_kept]:
        passages.setdefault(passage.chunk_id, passage)
    fused = reciprocal_rank_fusion(
        [
            [passage.chunk_id for passage in meaning_kept],
            [passage.chunk_id for passage in words_kept],
        ],
        settings.rrf_k,
    )
    ranked = [
        RankedPassage(passages[entry.item], entry.ranks[0], entry.ranks[1], entry.score)
        for entry in fused
    ]
    rerank_failed = False
    if settings.retrieval_mode == "hybrid_rerank" and ranked:
        reranked = _reranked(question, ranked, reranker)
        if reranked is None:
            rerank_failed = True
            if metrics is not None:
                metrics.count_reranker_failure()
        else:
            ranked = reranked
    return RetrievalResult(
        mode=settings.retrieval_mode,
        candidates=len({passage.chunk_id for passage in [*by_meaning, *by_words]}),
        ranked=tuple(ranked),
        evidence=tuple(entry.passage for entry in ranked[: settings.retrieval_top_k]),
        has_documents=has_documents,
        keyword_matches=len(by_words),
        keyword_dropped=len(by_words) - len(words_kept),
        rerank_failed=rerank_failed,
    )


def _reranked(
    question: str, ranked: Sequence[RankedPassage], reranker: Reranker | None
) -> list[RankedPassage] | None:
    """The candidates in the reranker's order, or None if it failed: it never stops an answer."""
    try:
        if reranker is None:
            raise RerankerUnavailableError("No reranker is configured")
        scores = reranker.score(question, [entry.passage.text for entry in ranked])
    except RerankerUnavailableError:
        logger.warning("Kept the fused order, because the reranker failed")
        return None
    if len(scores) != len(ranked) or not all(
        isinstance(score, float) and math.isfinite(score) for score in scores
    ):
        logger.warning("Kept the fused order, because the reranker returned unusable scores")
        return None
    # A stable sort, so equal scores keep the fused order.
    order = sorted(range(len(ranked)), key=lambda index: -scores[index])
    return [replace(ranked[index], rerank_score=scores[index]) for index in order]


def _evidence_only(passages: Sequence[Passage], settings: Settings) -> list[Passage]:
    return [
        passage for passage in passages if passage.similarity >= settings.retrieval_min_similarity
    ]
