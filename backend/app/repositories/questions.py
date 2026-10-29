"""Questions, their answers, and the passages the answers cite (Phase 4)."""

import uuid
from collections import defaultdict

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.db.models import (
    Answer,
    Citation,
    Document,
    DocumentChunk,
    Question,
    WorkspaceMembership,
)
from app.domain.questions import (
    HISTORY_LIMIT,
    QUESTION_RETENTION,
    AbstentionReason,
    AnswerMode,
    AnswerRecord,
    CitationRecord,
    Passage,
    QuestionRecord,
)


def add_answered(
    session: Session,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    text: str,
    answer: AnswerRecord,
) -> QuestionRecord:
    question = Question(id=uuid.uuid4(), workspace_id=workspace_id, user_id=user_id, text=text)
    session.add(question)
    # Flushed one at a time, as the models declare no relationships to order the inserts by.
    session.flush()
    answer_row = Answer(
        id=uuid.uuid4(),
        question_id=question.id,
        mode=answer.mode.value,
        text=answer.text,
        abstention_reason=answer.abstention_reason and answer.abstention_reason.value,
        model_name=answer.model_name,
    )
    session.add(answer_row)
    session.flush()
    if answer.citations:
        session.execute(
            insert(Citation),
            [
                {
                    "id": uuid.uuid4(),
                    "answer_id": answer_row.id,
                    "number": citation.number,
                    "document_id": citation.passage.document_id,
                    "chunk_id": citation.passage.chunk_id,
                    "similarity": citation.passage.similarity,
                }
                for citation in answer.citations
            ],
        )
    return QuestionRecord(question.id, workspace_id, text, question.created_at, answer)


def list_recent_for_member(
    session: Session, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> list[QuestionRecord]:
    """The member's own questions in the workspace from the last three days, newest first."""
    statement = (
        select(Question, Answer)
        .join(Answer, Answer.question_id == Question.id)
        .join(
            WorkspaceMembership,
            (WorkspaceMembership.workspace_id == Question.workspace_id)
            & (WorkspaceMembership.user_id == user_id),
        )
        .where(
            Question.workspace_id == workspace_id,
            Question.user_id == user_id,
            # Expired questions stay hidden even before the cleanup deletes them.
            Question.created_at > func.now() - QUESTION_RETENTION,
        )
        .order_by(Question.created_at.desc(), Question.id.desc())
        .limit(HISTORY_LIMIT)
    )
    rows = session.execute(statement).tuples().all()
    citations = _citations_for(session, [answer.id for _, answer in rows])
    return [
        QuestionRecord(
            question.id,
            question.workspace_id,
            question.text,
            question.created_at,
            AnswerRecord(
                AnswerMode(answer.mode),
                answer.text,
                AbstentionReason(answer.abstention_reason) if answer.abstention_reason else None,
                answer.model_name,
                tuple(citations[answer.id]),
            ),
        )
        for question, answer in rows
    ]


def _citations_for(
    session: Session, answer_ids: list[uuid.UUID]
) -> defaultdict[uuid.UUID, list[CitationRecord]]:
    citations: defaultdict[uuid.UUID, list[CitationRecord]] = defaultdict(list)
    if not answer_ids:
        return citations
    statement = (
        select(
            Citation.answer_id,
            Citation.number,
            Citation.similarity,
            DocumentChunk.id,
            DocumentChunk.document_id,
            Document.display_name,
            DocumentChunk.text,
            DocumentChunk.page_number,
            DocumentChunk.section,
        )
        .join(DocumentChunk, DocumentChunk.id == Citation.chunk_id)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Citation.answer_id.in_(answer_ids))
        .order_by(Citation.answer_id, Citation.number)
    )
    for row in session.execute(statement):
        citations[row.answer_id].append(
            CitationRecord(
                row.number,
                Passage(
                    chunk_id=row.id,
                    document_id=row.document_id,
                    document_name=row.display_name,
                    text=row.text,
                    page_number=row.page_number,
                    section=row.section,
                    similarity=row.similarity,
                ),
            )
        )
    return citations


def delete_expired(session: Session) -> int:
    """Delete questions asked more than three days ago, with their answers and citations."""
    statement = (
        delete(Question)
        .where(Question.created_at <= func.now() - QUESTION_RETENTION)
        .returning(Question.id)
    )
    return len(session.scalars(statement).all())


def delete_citing_document(session: Session, document_id: uuid.UUID) -> int:
    """Delete the questions whose answers cite the document."""
    citing = (
        select(Answer.question_id)
        .join(Citation, Citation.answer_id == Answer.id)
        .where(Citation.document_id == document_id)
    )
    statement = delete(Question).where(Question.id.in_(citing)).returning(Question.id)
    return len(session.scalars(statement).all())
