"""Asking questions, and the 3-day question history (P4-01 - P4-06, P4-09, P4-11; D-55).

`HashingEmbeddings` stands in for the embedding model, so texts that share words are similar,
and `ScriptedLanguageModel` stands in for Ollama. With the provisional threshold of 0.5, each
sample question below finds only the passage it shares most of its words with.
"""

import logging
import math
import re
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.db.models import Answer, Citation, Document, Question, WorkspaceMembership
from app.domain.indexing import EMBEDDING_DIMENSION
from app.domain.questions import AbstentionReason, AnswerMode, AnswerRecord
from app.providers.embeddings import EmbeddingUnavailableError
from app.repositories import questions as question_repository
from tests.conftest import AppFactory
from tests.support import (
    CSRF_HEADERS,
    HashingEmbeddings,
    Heading,
    ScriptedLanguageModel,
    ask,
    create_workspace,
    docx_bytes,
    error_code,
    hashed_vector,
    index_queued_documents,
    pdf_bytes,
    register,
    upload,
)

pytestmark = pytest.mark.integration

RETENTION_TEXT = "Project records are kept for seven years."
MEETING_TEXT = "Team meetings start at nine on Mondays."
RETENTION_QUESTION = "How long are project records kept?"
MEETING_QUESTION = "When do team meetings start on Mondays?"
UNRELATED_QUESTION = "Which train leaves first tomorrow morning?"
WAIT_SECONDS = 10
DECLINED = {"mode": "search_only", "text": None, "abstained": True, "model_name": None}


@dataclass
class Workspace:
    """A signed-in user's workspace, in an app whose background workers are off."""

    app: FastAPI
    client: TestClient
    id: str

    def add(self, filename: str, content: bytes) -> str:
        """Upload a document and index it, as the background worker would."""
        response = upload(self.client, self.id, filename, content)
        assert response.status_code == 202, response.text
        index_queued_documents(self.app)
        document_id: str = response.json()["id"]
        return document_id

    def ask(self, question: str) -> dict[str, Any]:
        response = ask(self.client, self.id, question)
        assert response.status_code == 201, response.text
        body: dict[str, Any] = response.json()
        return body

    def history(self) -> list[dict[str, Any]]:
        response = self.client.get(f"/api/v1/workspaces/{self.id}/questions")
        assert response.status_code == 200, response.text
        items: list[dict[str, Any]] = response.json()["items"]
        return items

    def delete(self, document_id: str) -> None:
        response = self.client.delete(f"/api/v1/documents/{document_id}", headers=CSRF_HEADERS)
        assert response.status_code == 204, response.text


@pytest.fixture
def make_workspace(
    make_db_app: AppFactory, make_client: Callable[[FastAPI], TestClient]
) -> Callable[..., Workspace]:
    def factory(**overrides: Any) -> Workspace:
        app = make_db_app(**overrides)
        client = make_client(app)
        assert register(client).status_code == 201
        return Workspace(app, client, create_workspace(client)["id"])

    return factory


def ids(questions: Sequence[dict[str, Any]]) -> list[str]:
    return [question["id"] for question in questions]


def outcome(answer: dict[str, Any]) -> dict[str, Any]:
    """An answer without its citations or abstention reason."""
    return {key: answer[key] for key in ("mode", "text", "abstained", "model_name")}


def make_older(app: FastAPI, question_id: str, hours: float) -> None:
    with app.state.session_factory() as session:
        session.execute(
            update(Question)
            .where(Question.id == uuid.UUID(question_id))
            .values(created_at=Question.created_at - timedelta(hours=hours))
        )
        session.commit()


def stored_question_ids(app: FastAPI) -> set[str]:
    with app.state.session_factory() as session:
        return {str(question_id) for question_id in session.scalars(select(Question.id))}


def count(app: FastAPI, table: type[Answer] | type[Citation]) -> int:
    with app.state.session_factory() as session:
        return session.scalar(select(func.count()).select_from(table)) or 0


def cosine(first: str, second: str) -> float:
    return sum(a * b for a, b in zip(hashed_vector(first), hashed_vector(second), strict=True))


def test_the_sample_texts_are_as_similar_as_these_tests_assume() -> None:
    assert cosine(RETENTION_QUESTION, RETENTION_TEXT) > 0.55
    assert cosine(MEETING_QUESTION, MEETING_TEXT) > 0.55
    for question in (MEETING_QUESTION, UNRELATED_QUESTION):
        assert cosine(question, RETENTION_TEXT) < 0.3
    for question in (RETENTION_QUESTION, UNRELATED_QUESTION):
        assert cosine(question, MEETING_TEXT) < 0.3


def test_a_generated_answer_cites_the_passages_it_relies_on(
    make_workspace: Callable[..., Workspace],
) -> None:
    model = ScriptedLanguageModel("Project records are kept for seven years [S1].")
    workspace = make_workspace(language_model=model)
    document_id = workspace.add("retention.txt", RETENTION_TEXT.encode())
    workspace.add("meetings.txt", MEETING_TEXT.encode())

    question = workspace.ask("  How long are project\n records   kept? ")

    assert question["text"] == RETENTION_QUESTION
    assert question["workspace_id"] == workspace.id
    asked = datetime.fromisoformat(question["created_at"])
    assert datetime.fromisoformat(question["expires_at"]) - asked == timedelta(days=3)
    answer = question["answer"]
    assert outcome(answer) == {
        "mode": "generated",
        "text": "Project records are kept for seven years [1].",
        "abstained": False,
        "model_name": "scripted-model",
    }
    assert answer["abstention_reason"] is None
    [citation] = answer["citations"]
    assert citation["number"] == 1
    assert citation["document_id"] == document_id
    assert citation["document_name"] == "retention.txt"
    assert citation["excerpt"] == RETENTION_TEXT
    assert (citation["page_number"], citation["section"]) == (None, None)
    # Rounded to 4 places, from vectors PostgreSQL stores in single precision.
    expected_similarity = cosine(RETENTION_QUESTION, RETENTION_TEXT)
    assert citation["similarity"] == pytest.approx(expected_similarity, abs=1e-4)
    uuid.UUID(citation["chunk_id"])
    # The model was shown only the passage close enough to the question, and the question.
    [[_, prompt]] = model.prompts
    assert prompt.content.count("<<<BEGIN SOURCE") == 1
    assert RETENTION_TEXT in prompt.content
    assert MEETING_TEXT not in prompt.content
    assert f"Question: {RETENTION_QUESTION}\n" in prompt.content
    assert workspace.history() == [question]


def test_only_the_passages_an_answer_cites_become_its_citations(
    make_workspace: Callable[..., Workspace],
) -> None:
    model = ScriptedLanguageModel("Records are kept for seven years [S2].")
    workspace = make_workspace(language_model=model)
    workspace.add("retention.txt", RETENTION_TEXT.encode())
    workspace.add("policy.docx", docx_bytes(Heading("Retention"), RETENTION_TEXT))

    answer = workspace.ask(RETENTION_QUESTION)["answer"]

    [[_, prompt]] = model.prompts
    assert prompt.content.count("<<<BEGIN SOURCE") == 2
    second = re.search(
        r"<<<BEGIN SOURCE S2 (\w+)>>>\n(.*?)\n<<<END SOURCE S2 \1>>>", prompt.content, re.DOTALL
    )
    assert second is not None
    assert answer["text"] == "Records are kept for seven years [1]."
    [citation] = answer["citations"]
    assert (citation["number"], citation["excerpt"]) == (1, second[2])


def test_citations_give_the_pdf_page_or_the_word_section(
    make_workspace: Callable[..., Workspace],
) -> None:
    workspace = make_workspace()
    pdf_id = workspace.add("handbook.pdf", pdf_bytes("Synthetic cover page.", RETENTION_TEXT))
    docx_id = workspace.add("policy.docx", docx_bytes(Heading("Retention"), RETENTION_TEXT))

    citations = workspace.ask(RETENTION_QUESTION)["answer"]["citations"]

    places = {item["document_id"]: (item["page_number"], item["section"]) for item in citations}
    assert places == {pdf_id: (2, None), docx_id: (None, "Retention")}


def test_without_a_model_the_closest_passages_are_the_answer(
    make_workspace: Callable[..., Workspace],
) -> None:
    workspace = make_workspace(retrieval_top_k=2)
    workspace.add("retention.txt", RETENTION_TEXT.encode())
    workspace.add("policy.docx", docx_bytes(Heading("Retention"), RETENTION_TEXT))
    workspace.add("handbook.pdf", pdf_bytes(RETENTION_TEXT))
    workspace.add("meetings.txt", MEETING_TEXT.encode())

    answer = workspace.ask(RETENTION_QUESTION)["answer"]

    assert outcome(answer) == {
        "mode": "search_only",
        "text": None,
        "abstained": False,
        "model_name": None,
    }
    assert answer["abstention_reason"] is None
    citations = answer["citations"]
    assert [citation["number"] for citation in citations] == [1, 2]
    similarities = [citation["similarity"] for citation in citations]
    assert similarities == sorted(similarities, reverse=True)
    assert all(citation["excerpt"].endswith(RETENTION_TEXT) for citation in citations)


def test_when_the_model_does_not_reply_the_closest_passages_are_shown(
    make_workspace: Callable[..., Workspace],
) -> None:
    model = ScriptedLanguageModel(fail=True)
    workspace = make_workspace(language_model=model)
    document_id = workspace.add("retention.txt", RETENTION_TEXT.encode())

    answer = workspace.ask(RETENTION_QUESTION)["answer"]

    assert len(model.prompts) == 1
    assert outcome(answer) == {
        "mode": "search_only",
        "text": None,
        "abstained": False,
        "model_name": "scripted-model",
    }
    assert [citation["document_id"] for citation in answer["citations"]] == [document_id]


def test_questions_are_declined_until_a_document_is_indexed(
    make_workspace: Callable[..., Workspace],
) -> None:
    model = ScriptedLanguageModel("Unused [S1].")
    workspace = make_workspace(language_model=model)

    before_upload = workspace.ask(RETENTION_QUESTION)["answer"]
    response = upload(workspace.client, workspace.id, "retention.txt", RETENTION_TEXT.encode())
    assert response.status_code == 202
    while_queued = workspace.ask(RETENTION_QUESTION)["answer"]

    for answer in (before_upload, while_queued):
        assert outcome(answer) == DECLINED
        assert answer["abstention_reason"] == "no_indexed_documents"
        assert answer["citations"] == []
    assert model.prompts == []


@pytest.mark.parametrize("status", ["queued", "processing", "failed", "deleting"])
def test_only_ready_documents_are_searched(
    make_workspace: Callable[..., Workspace], status: str
) -> None:
    workspace = make_workspace()
    document_id = workspace.add("retention.txt", RETENTION_TEXT.encode())
    with workspace.app.state.session_factory() as session:
        session.execute(
            update(Document).where(Document.id == uuid.UUID(document_id)).values(status=status)
        )
        session.commit()

    answer = workspace.ask(RETENTION_QUESTION)["answer"]

    assert answer["abstention_reason"] == "no_indexed_documents"


def test_questions_without_a_close_enough_passage_are_declined(
    make_workspace: Callable[..., Workspace],
) -> None:
    model = ScriptedLanguageModel("Unused [S1].")
    workspace = make_workspace(language_model=model)
    workspace.add("retention.txt", RETENTION_TEXT.encode())

    answer = workspace.ask(UNRELATED_QUESTION)["answer"]

    assert outcome(answer) == DECLINED
    assert answer["abstention_reason"] == "weak_evidence"
    assert answer["citations"] == []
    assert model.prompts == []


def test_the_similarity_threshold_is_a_setting(make_workspace: Callable[..., Workspace]) -> None:
    workspace = make_workspace(retrieval_min_similarity=0.9)
    workspace.add("retention.txt", RETENTION_TEXT.encode())

    assert workspace.ask(RETENTION_QUESTION)["answer"]["abstention_reason"] == "weak_evidence"


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        ("INSUFFICIENT_EVIDENCE", "insufficient_evidence"),
        ("Records are kept forever.", "uncited_answer"),
        ("Records are kept forever [S7].", "uncited_answer"),
    ],
)
def test_generated_answers_that_decline_or_cite_nothing_keep_no_text(
    make_workspace: Callable[..., Workspace], reply: str, reason: str
) -> None:
    workspace = make_workspace(language_model=ScriptedLanguageModel(reply))
    workspace.add("retention.txt", RETENTION_TEXT.encode())

    answer = workspace.ask(RETENTION_QUESTION)["answer"]

    assert outcome(answer) == {
        "mode": "generated",
        "text": None,
        "abstained": True,
        "model_name": "scripted-model",
    }
    assert answer["abstention_reason"] == reason
    assert answer["citations"] == []
    assert workspace.history()[0]["answer"] == answer


def test_answers_only_use_the_workspace_asked_about(
    make_workspace: Callable[..., Workspace], make_client: Callable[[FastAPI], TestClient]
) -> None:
    owner = make_workspace()
    owner_document = owner.add("retention.txt", RETENTION_TEXT.encode())
    second_workspace = Workspace(owner.app, owner.client, create_workspace(owner.client)["id"])
    other_client = make_client(owner.app)
    assert register(other_client, "other@example.com").status_code == 201
    other = Workspace(owner.app, other_client, create_workspace(other_client)["id"])
    other_document = other.add("copy.txt", RETENTION_TEXT.encode())

    owner_citations = owner.ask(RETENTION_QUESTION)["answer"]["citations"]
    other_citations = other.ask(RETENTION_QUESTION)["answer"]["citations"]
    empty_answer = second_workspace.ask(RETENTION_QUESTION)["answer"]

    assert [citation["document_id"] for citation in owner_citations] == [owner_document]
    assert [citation["document_id"] for citation in other_citations] == [other_document]
    assert empty_answer["abstention_reason"] == "no_indexed_documents"
    for response in (
        ask(other_client, owner.id, RETENTION_QUESTION),
        other_client.get(f"/api/v1/workspaces/{owner.id}/questions"),
    ):
        assert response.status_code == 404
        assert error_code(response) == "workspace_not_found"
        assert RETENTION_TEXT not in response.text


def test_history_lists_your_own_recent_questions_newest_first(
    make_workspace: Callable[..., Workspace], make_client: Callable[[FastAPI], TestClient]
) -> None:
    workspace = make_workspace()
    workspace.add("retention.txt", RETENTION_TEXT.encode())
    first = workspace.ask(RETENTION_QUESTION)
    second = workspace.ask(MEETING_QUESTION)
    third = workspace.ask(UNRELATED_QUESTION)
    # Another member of the same workspace; the app has no way to invite one yet.
    member_client = make_client(workspace.app)
    member = register(member_client, "member@example.com").json()
    with workspace.app.state.session_factory() as session:
        session.add(
            WorkspaceMembership(
                workspace_id=uuid.UUID(workspace.id), user_id=uuid.UUID(member["id"]), role="member"
            )
        )
        session.commit()
    members_question = Workspace(workspace.app, member_client, workspace.id).ask(RETENTION_QUESTION)

    assert ids(workspace.history()) == ids([third, second, first])
    member_history = Workspace(workspace.app, member_client, workspace.id).history()
    assert ids(member_history) == ids([members_question])

    make_older(workspace.app, first["id"], hours=72)
    make_older(workspace.app, second["id"], hours=71)

    assert ids(workspace.history()) == ids([third, second])


def test_history_shows_at_most_50_questions(make_workspace: Callable[..., Workspace]) -> None:
    workspace = make_workspace()
    user_id = uuid.UUID(workspace.client.get("/api/v1/auth/me").json()["id"])
    declined = AnswerRecord(AnswerMode.SEARCH_ONLY, None, AbstentionReason.WEAK_EVIDENCE, None, ())
    with workspace.app.state.session_factory() as session:
        for number in range(51):
            question_repository.add_answered(
                session, uuid.UUID(workspace.id), user_id, f"Question {number}?", declined
            )
        session.commit()

    assert len(workspace.history()) == 50


def test_the_cleanup_deletes_questions_once_they_are_three_days_old(
    make_workspace: Callable[..., Workspace],
) -> None:
    workspace = make_workspace()
    workspace.add("retention.txt", RETENTION_TEXT.encode())
    expired = workspace.ask(RETENTION_QUESTION)
    kept = workspace.ask(RETENTION_QUESTION)
    make_older(workspace.app, expired["id"], hours=72)
    make_older(workspace.app, kept["id"], hours=71)
    cleanup = workspace.app.state.question_cleanup

    assert cleanup.run_once() == 1
    assert cleanup.run_once() == 0

    assert stored_question_ids(workspace.app) == {kept["id"]}
    assert count(workspace.app, Answer) == 1
    assert count(workspace.app, Citation) == 1


def test_the_api_deletes_expired_questions_when_it_starts(
    make_workspace: Callable[..., Workspace], make_client: Callable[[FastAPI], TestClient]
) -> None:
    workspace = make_workspace(question_cleanup_enabled=True)
    expired = workspace.ask(RETENTION_QUESTION)
    make_older(workspace.app, expired["id"], hours=73)
    cleanup = workspace.app.state.question_cleanup
    assert not cleanup.running

    # Entering the client runs the app's startup, which starts the cleanup.
    with make_client(workspace.app):
        deadline = time.monotonic() + WAIT_SECONDS
        while stored_question_ids(workspace.app) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert cleanup.running

    assert stored_question_ids(workspace.app) == set()
    assert not cleanup.running


def test_deleting_a_document_deletes_the_answers_that_cite_it(
    make_workspace: Callable[..., Workspace],
) -> None:
    workspace = make_workspace()
    retention_id = workspace.add("retention.txt", RETENTION_TEXT.encode())
    workspace.add("meetings.txt", MEETING_TEXT.encode())
    cites_retention = workspace.ask(RETENTION_QUESTION)
    cites_meetings = workspace.ask(MEETING_QUESTION)
    cites_nothing = workspace.ask(UNRELATED_QUESTION)
    assert cites_retention["answer"]["citations"]

    workspace.delete(retention_id)

    assert ids(workspace.history()) == ids([cites_nothing, cites_meetings])
    assert count(workspace.app, Answer) == 2
    assert count(workspace.app, Citation) == 1


def test_an_answer_is_not_kept_if_its_document_is_deleted_while_it_is_written(
    make_workspace: Callable[..., Workspace],
) -> None:
    model = ScriptedLanguageModel("Records are kept for seven years [S1].")
    workspace = make_workspace(language_model=model)
    document_id = workspace.add("retention.txt", RETENTION_TEXT.encode())
    model.before = lambda: workspace.delete(document_id)

    response = ask(workspace.client, workspace.id, RETENTION_QUESTION)

    assert response.status_code == 409
    assert error_code(response) == "answer_sources_changed"
    assert workspace.history() == []
    assert stored_question_ids(workspace.app) == set()


class QueryEmbeddings(HashingEmbeddings):
    """Hashing embeddings for documents, but questions get a set vector, or none at all."""

    def __init__(self, query_vector: list[float] | None) -> None:
        super().__init__()
        self.query_vector = query_vector

    def embed_query(self, text: str) -> list[float]:
        if self.query_vector is None:
            raise EmbeddingUnavailableError("synthetic-model")
        return self.query_vector


@pytest.mark.parametrize(
    "query_vector",
    [None, [0.1] * 10, [math.nan] * EMBEDDING_DIMENSION],
    ids=["down", "short", "nan"],
)
def test_questions_wait_while_the_search_model_is_unavailable(
    make_workspace: Callable[..., Workspace], query_vector: list[float] | None
) -> None:
    workspace = make_workspace(embeddings=QueryEmbeddings(query_vector))
    workspace.add("retention.txt", RETENTION_TEXT.encode())

    response = ask(workspace.client, workspace.id, RETENTION_QUESTION)

    assert response.status_code == 503
    assert error_code(response) == "embedding_unavailable"
    assert workspace.history() == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"text": None},
        {"text": 7},
        {"text": ""},
        {"text": " \n\t\u200b "},
        {"text": "x" * 1001},
        {"text": "x " * 2001},
    ],
    ids=["missing", "null", "number", "empty", "blank", "too-long", "far-too-long"],
)
def test_questions_must_have_1_to_1000_characters(
    make_workspace: Callable[..., Workspace], body: dict[str, Any]
) -> None:
    workspace = make_workspace()

    response = workspace.client.post(
        f"/api/v1/workspaces/{workspace.id}/questions", json=body, headers=CSRF_HEADERS
    )

    assert response.status_code == 422
    assert error_code(response) == "validation_failed"


def test_the_length_limit_applies_after_spaces_are_tidied(
    make_workspace: Callable[..., Workspace],
) -> None:
    workspace = make_workspace()

    question = workspace.ask(" " * 500 + "x" * 1000 + "\n" * 500)

    assert question["text"] == "x" * 1000


def test_asking_needs_the_csrf_header(make_workspace: Callable[..., Workspace]) -> None:
    workspace = make_workspace()

    response = workspace.client.post(
        f"/api/v1/workspaces/{workspace.id}/questions", json={"text": RETENTION_QUESTION}
    )

    assert response.status_code == 403
    assert error_code(response) == "csrf_header_missing"


def test_question_and_answer_text_never_reach_the_logs(
    make_workspace: Callable[..., Workspace], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    model = ScriptedLanguageModel("Synthetic confidential answer [S1].")
    workspace = make_workspace(language_model=model)
    workspace.add("retention.txt", RETENTION_TEXT.encode())

    question = workspace.ask(RETENTION_QUESTION)

    assert f"Answered question {question['id']}: mode=generated abstention=none" in caplog.text
    for secret in (RETENTION_QUESTION, "confidential answer", RETENTION_TEXT):
        assert secret not in caplog.text
