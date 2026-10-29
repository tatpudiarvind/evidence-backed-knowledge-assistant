"""Questions: ask one about a workspace's documents, and list the recent ones (Phase 4)."""

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, EmbeddingsDep, LanguageModelDep, SettingsDep
from app.api.v1.schemas import (
    AnswerOut,
    CitationOut,
    QuestionCreateRequest,
    QuestionList,
    QuestionOut,
)
from app.domain.questions import QuestionRecord
from app.services import questions as question_service

router = APIRouter(tags=["questions"])


@router.post(
    "/workspaces/{workspace_id}/questions",
    status_code=201,
    summary="Ask a question about a workspace's documents",
    description=(
        "Finds the passages in the workspace's indexed documents closest to the question. With "
        "a language model configured, the answer is written from those passages and cites them, "
        "or abstains when they don't answer the question; otherwise the passages are the "
        "answer. A local model can take a minute or more. Questions are kept for three days."
    ),
)
def ask_question(
    workspace_id: uuid.UUID,
    body: QuestionCreateRequest,
    user: CurrentUser,
    session: DbSession,
    settings: SettingsDep,
    embeddings: EmbeddingsDep,
    language_model: LanguageModelDep,
) -> QuestionOut:
    record = question_service.ask_question(
        session,
        user,
        workspace_id,
        body.text,
        settings=settings,
        embeddings=embeddings,
        language_model=language_model,
    )
    return _question_out(record)


@router.get(
    "/workspaces/{workspace_id}/questions",
    summary="List your recent questions in a workspace",
    description="Your questions from the last three days, newest first, up to 50.",
)
def list_questions(workspace_id: uuid.UUID, user: CurrentUser, session: DbSession) -> QuestionList:
    records = question_service.list_questions(session, user, workspace_id)
    return QuestionList(items=[_question_out(record) for record in records])


def _question_out(record: QuestionRecord) -> QuestionOut:
    answer = record.answer
    return QuestionOut(
        id=record.id,
        workspace_id=record.workspace_id,
        text=record.text,
        created_at=record.created_at,
        expires_at=record.expires_at,
        answer=AnswerOut(
            mode=answer.mode,
            text=answer.text,
            abstained=answer.abstained,
            abstention_reason=answer.abstention_reason,
            model_name=answer.model_name,
            citations=[
                CitationOut(
                    number=citation.number,
                    document_id=citation.passage.document_id,
                    document_name=citation.passage.document_name,
                    chunk_id=citation.passage.chunk_id,
                    page_number=citation.passage.page_number,
                    section=citation.passage.section,
                    excerpt=citation.passage.text,
                    similarity=round(citation.passage.similarity, 4),
                )
                for citation in answer.citations
            ],
        ),
    )
