"""Questions (Phase 4): find the passages closest to a question in a workspace's ready
documents, have a language model answer from them with citations or decline to, and keep the
result for three days.

No database transaction stays open while a model runs, which can take a minute or more, so the
workspace and the cited documents are checked again before the answer is stored.
"""

import logging
import time
import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models import User
from app.domain.grounding import build_prompt, check_answer
from app.domain.questions import (
    AbstentionReason,
    AnswerMode,
    AnswerRecord,
    CitationRecord,
    Passage,
    QuestionRecord,
)
from app.providers.embeddings import EmbeddingProvider, EmbeddingUnavailableError, check_vectors
from app.providers.llm import LanguageModel, LanguageModelUnavailableError
from app.repositories import chunks as chunk_repository
from app.repositories import documents as document_repository
from app.repositories import questions as question_repository
from app.services.workspaces import require_workspace

logger = logging.getLogger(__name__)


def list_questions(session: Session, user: User, workspace_id: uuid.UUID) -> list[QuestionRecord]:
    require_workspace(session, user, workspace_id)
    return question_repository.list_recent_for_member(session, workspace_id, user.id)


def ask_question(
    session: Session,
    user: User,
    workspace_id: uuid.UUID,
    text: str,
    *,
    settings: Settings,
    embeddings: EmbeddingProvider,
    language_model: LanguageModel | None,
) -> QuestionRecord:
    """Answer a question from the workspace's documents, or say why it can't be answered."""
    started = time.perf_counter()
    require_workspace(session, user, workspace_id)
    user_id = user.id
    # Ends the read transaction, so no connection is held while the question is embedded.
    session.rollback()

    vector = _embed(embeddings, text)
    passages = chunk_repository.search_workspace(
        session, workspace_id, user_id, vector, settings.retrieval_top_k
    )
    has_documents = bool(passages) or chunk_repository.workspace_has_indexed_chunks(
        session, workspace_id, user_id
    )
    session.rollback()
    evidence = [
        passage for passage in passages if passage.similarity >= settings.retrieval_min_similarity
    ]
    answer = _answer(text, evidence, has_documents, settings, language_model)

    require_workspace(session, user, workspace_id)
    cited = {citation.passage.document_id for citation in answer.citations}
    # The lock keeps the cited documents from being deleted until the answer is stored.
    if cited and document_repository.lock_ready(session, cited) != cited:
        session.rollback()
        raise AppError(
            409,
            "answer_sources_changed",
            "A document this answer relies on was deleted while the answer was being prepared. "
            "Ask again.",
        )
    record = question_repository.add_answered(session, workspace_id, user_id, text, answer)
    session.commit()
    # Never the question's or the answer's text.
    logger.info(
        "Answered question %s: mode=%s abstention=%s passages=%d evidence=%d citations=%d "
        "in %.1f s",
        record.id,
        answer.mode.value,
        answer.abstention_reason.value if answer.abstention_reason else "none",
        len(passages),
        len(evidence),
        len(answer.citations),
        time.perf_counter() - started,
    )
    return record


def _embed(embeddings: EmbeddingProvider, text: str) -> list[float]:
    try:
        vector = embeddings.embed_query(text)
    except EmbeddingUnavailableError:
        raise _search_unavailable() from None
    if not check_vectors([vector], 1):
        logger.warning("The embedding model returned an unusable vector for a question")
        raise _search_unavailable()
    return vector


def _answer(
    question: str,
    evidence: Sequence[Passage],
    has_documents: bool,
    settings: Settings,
    language_model: LanguageModel | None,
) -> AnswerRecord:
    if not has_documents:
        return _declined(AbstentionReason.NO_INDEXED_DOCUMENTS)
    if not evidence:
        return _declined(AbstentionReason.WEAK_EVIDENCE)
    if language_model is None:
        return _passages_only(evidence, None)
    prompt = build_prompt(question, evidence, settings.answer_context_characters)
    try:
        generation = language_model.generate(prompt.messages)
    except LanguageModelUnavailableError:
        # The matching passages are still worth showing.
        return _passages_only(evidence, language_model.name)
    checked = check_answer(generation.text, prompt.sources)
    return AnswerRecord(
        AnswerMode.GENERATED,
        checked.text,
        checked.abstention_reason,
        generation.model_name,
        _numbered(checked.cited),
    )


def _declined(reason: AbstentionReason) -> AnswerRecord:
    return AnswerRecord(AnswerMode.SEARCH_ONLY, None, reason, None, ())


def _passages_only(evidence: Sequence[Passage], model_name: str | None) -> AnswerRecord:
    return AnswerRecord(AnswerMode.SEARCH_ONLY, None, None, model_name, _numbered(evidence))


def _numbered(passages: Sequence[Passage]) -> tuple[CitationRecord, ...]:
    return tuple(CitationRecord(number, passage) for number, passage in enumerate(passages, 1))


def _search_unavailable() -> AppError:
    return AppError(
        503,
        "embedding_unavailable",
        "Questions can't be answered right now because the search model isn't available. "
        "Try again later.",
    )
