"""Running the evaluation (P5-02).

The corpus is uploaded to a new workspace and indexed the way the app indexes uploads. Then each
question is searched for three ways, to see how PostgreSQL reads the chunks and whether the
approximate HNSW index finds what an exact scan finds, and is asked the way the API asks it.
With a language model, the model's prompt and raw reply are kept too, for review.
"""

import hashlib
import importlib.metadata
import json
import os
import platform
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.expression import ClauseElement, Executable

from app.core.config import Settings
from app.core.database import create_database_engine, create_session_factory
from app.core.errors import AppError
from app.db.models import Document, User
from app.domain.documents import DocumentStatus, ReceivedFile
from app.domain.grounding import ChatMessage
from app.domain.questions import AnswerMode, Passage, clean_question
from app.evaluation.corpus import CorpusDocument, corpus_sha256
from app.evaluation.dataset import EvalQuestion
from app.evaluation.scoring import (
    SEARCH_LIMIT,
    AnswerOutcome,
    AnswerScore,
    FoundPassage,
    IndexComparison,
    Json,
    Retrieval,
    judge,
    score_answer,
)
from app.providers.embeddings import EmbeddingProvider, EmbeddingUnavailableError
from app.providers.llm import Generation, LanguageModel, LanguageModelUnavailableError
from app.providers.storage import LocalDocumentStorage
from app.repositories import chunks as chunk_repository
from app.repositories import users as user_repository
from app.services.documents import store_upload
from app.services.ingestion import DocumentIndexer
from app.services.questions import ask_question
from app.services.workspaces import create_workspace

# Planner settings for each way of searching, on top of the app's own: the app's query as the
# planner runs it; the HNSW index forced, by ruling out full scans and sorting, which only the
# index's ordered scan avoids; and an exact search, which computes every chunk's distance.
SEARCH_MODES: dict[str, tuple[str, ...]] = {
    "default": (),
    "index": ("enable_seqscan = off", "enable_sort = off"),
    "exact": ("enable_indexscan = off",),
}
# Not a valid password hash, so nobody can sign in as the evaluation's user.
_NO_PASSWORD = "!"
# Versions that affect what the evaluation measures.
_PACKAGES = (
    "fastapi",
    "sqlalchemy",
    "psycopg",
    "pgvector",
    "sentence-transformers",
    "transformers",
    "torch",
    "pypdf",
    "python-docx",
)


class EvaluationError(Exception):
    """The evaluation can't run or finish, for a reason worth telling whoever started it."""


@dataclass(frozen=True)
class IndexedDocument:
    """A corpus document as the evaluation uploaded and indexed it."""

    name: str
    mime_type: str
    source_name: str
    source_sha256: str
    size_bytes: int
    chunks: int


@dataclass(frozen=True)
class QuestionResult:
    retrieval: Retrieval
    comparison: IndexComparison
    score: AnswerScore
    # The app worked from what the evaluation's own search found: without a model, its evidence
    # is exactly those passages; with one, it cites only them.
    evidence_matches: bool
    # How long the model took to reply, if it was asked.
    model_seconds: float | None


@dataclass(frozen=True)
class EvaluationRun:
    started_at: datetime
    seconds: float
    settings: Settings
    language_model: str | None
    # The most full-size chunks that fit in the answer's context budget.
    max_k: int
    corpus_sha256: str
    documents: tuple[IndexedDocument, ...]
    results: tuple[QuestionResult, ...]
    environment: Json


@dataclass(frozen=True)
class _Context:
    session_factory: sessionmaker[Session]
    settings: Settings
    embeddings: EmbeddingProvider
    language_model: LanguageModel | None
    user: User
    workspace_id: uuid.UUID


def max_k(settings: Settings) -> int:
    """How many full-size chunks fit in the answer's context budget; more never reach a model."""
    fitting = settings.answer_context_characters // settings.chunk_size_characters
    return max(1, min(SEARCH_LIMIT, fitting))


def run_evaluation(
    settings: Settings,
    documents: Sequence[CorpusDocument],
    questions: Sequence[EvalQuestion],
    *,
    embeddings: EmbeddingProvider,
    language_model: LanguageModel | None,
    progress: Callable[[str], None] | None = None,
) -> EvaluationRun:
    """Index the corpus in a new workspace, then ask every question.

    Use a throwaway database: the evaluation adds a user, a workspace, the documents, and every
    question and answer to it. Uploaded files go to `settings.storage_dir`.
    """
    notify = progress or (lambda message: None)
    started_at = datetime.now(UTC)
    started = time.perf_counter()
    _warm_up(embeddings, language_model)
    engine = create_database_engine(settings)
    try:
        session_factory = create_session_factory(engine)
        user, workspace_id = _create_workspace(session_factory)
        context = _Context(
            session_factory, settings, embeddings, language_model, user, workspace_id
        )
        indexed = _index_corpus(context, documents)
        notify(
            f"Indexed {len(indexed)} documents into "
            f"{sum(document.chunks for document in indexed)} chunks"
        )
        results: list[QuestionResult] = []
        for number, question in enumerate(questions, start=1):
            results.append(_ask(context, question))
            notify(f"Asked {question.id} ({number} of {len(questions)})")
        environment = _environment(session_factory)
    finally:
        engine.dispose()
    return EvaluationRun(
        started_at,
        time.perf_counter() - started,
        settings,
        language_model.name if language_model else None,
        max_k(settings),
        corpus_sha256(documents),
        indexed,
        tuple(results),
        environment,
    )


def chunk_access(plan: Any) -> str:
    """How an `EXPLAIN (FORMAT JSON)` plan reads the chunks, such as "Seq Scan"."""
    if isinstance(plan, str):
        plan = json.loads(plan)
    found: set[str] = set()
    nodes = [entry["Plan"] for entry in plan]
    while nodes:
        node = nodes.pop()
        if node.get("Relation Name") == "document_chunks":
            index = node.get("Index Name")
            found.add(f"{node['Node Type']} using {index}" if index else node["Node Type"])
        nodes.extend(node.get("Plans", []))
    return ", ".join(sorted(found)) or "not read"


class _Explain(Executable, ClauseElement):
    """`EXPLAIN (FORMAT JSON)` of a statement, its parameters bound as they would be."""

    inherit_cache = False

    def __init__(self, statement: ClauseElement) -> None:
        self.statement = statement


@compiles(_Explain, "postgresql")
def _compile_explain(element: _Explain, compiler: SQLCompiler, **kw: Any) -> str:
    return "EXPLAIN (FORMAT JSON) " + compiler.process(element.statement, **kw)


class _RecordingModel:
    """Passes a prompt on to the model, keeping the user message, the reply, and the time."""

    def __init__(self, model: LanguageModel) -> None:
        self._model = model
        self.prompt: str | None = None
        self.reply: str | None = None
        self.seconds: float | None = None

    @property
    def name(self) -> str:
        return self._model.name

    def generate(self, messages: Sequence[ChatMessage]) -> Generation:
        self.prompt = next(
            (message.content for message in messages if message.role == "user"), None
        )
        started = time.perf_counter()
        try:
            generation = self._model.generate(messages)
        finally:
            self.seconds = time.perf_counter() - started
        self.reply = generation.text
        return generation


def _warm_up(embeddings: EmbeddingProvider, language_model: LanguageModel | None) -> None:
    """Load the models before anything is timed, and stop early if one isn't available."""
    try:
        embeddings.embed_query("A warm-up question?")
    except EmbeddingUnavailableError:
        raise EvaluationError(
            "The embedding model isn't available. Download it with "
            "`python -m app.cli download-embedding-model`."
        ) from None
    if language_model is None:
        return
    try:
        language_model.generate([ChatMessage("user", "Reply with the word ready.")])
    except LanguageModelUnavailableError:
        raise EvaluationError(
            f"The language model {language_model.name} didn't reply. Check that its server is "
            "running and the model is installed."
        ) from None


def _create_workspace(session_factory: sessionmaker[Session]) -> tuple[User, uuid.UUID]:
    with session_factory() as session:
        email = f"evaluation-{uuid.uuid4().hex[:12]}@example.invalid"
        user = user_repository.add_user(session, email, _NO_PASSWORD)
        session.commit()
        workspace = create_workspace(session, user, "Evaluation").workspace
    return user, workspace.id


def _index_corpus(
    context: _Context, documents: Sequence[CorpusDocument]
) -> tuple[IndexedDocument, ...]:
    storage = LocalDocumentStorage(context.settings.storage_dir)
    uploaded: list[tuple[CorpusDocument, uuid.UUID]] = []
    for document in documents:
        path, file = storage.create_temp_file()
        with file:
            file.write(document.content)
        received = ReceivedFile(
            path, document.name, len(document.content), hashlib.sha256(document.content).hexdigest()
        )
        try:
            with context.session_factory() as session:
                stored = store_upload(
                    session,
                    storage,
                    context.settings,
                    context.user,
                    context.workspace_id,
                    received,
                )
        except AppError as error:
            raise EvaluationError(f"{document.name} wasn't accepted: {error.message}") from None
        finally:
            received.discard()
        if stored.display_name != document.name:
            # The questions name their sources by document name.
            raise EvaluationError(f"{document.name} was stored as {stored.display_name}.")
        uploaded.append((document, stored.id))

    indexer = DocumentIndexer(
        context.session_factory, storage, context.embeddings, context.settings
    )
    while indexer.process_next():
        pass

    indexed: list[IndexedDocument] = []
    with context.session_factory() as session:
        for document, document_id in uploaded:
            current = session.get(Document, document_id)
            if current is None or current.status != DocumentStatus.READY.value:
                reason = current.failure_message if current is not None else None
                raise EvaluationError(
                    f"{document.name} wasn't indexed: {reason or 'it is no longer there'}"
                )
            indexed.append(
                IndexedDocument(
                    document.name,
                    document.mime_type,
                    document.source_name,
                    document.source_sha256,
                    len(document.content),
                    chunk_repository.count_for_document(session, document_id),
                )
            )
        # Fresh statistics, so the planner sees the tables as they now are.
        session.execute(text("ANALYZE document_chunks, documents, workspace_memberships"))
        session.commit()
    return tuple(indexed)


def _ask(context: _Context, question: EvalQuestion) -> QuestionResult:
    settings = context.settings
    # As the API cleans questions before asking them.
    asked = clean_question(question.question)
    vector = context.embeddings.embed_query(asked)
    searches = {mode: _search(context, vector, mode) for mode in SEARCH_MODES}
    found = searches["default"][0]
    ids = {
        mode: tuple(passage.chunk_id for passage in passages)
        for mode, (passages, _) in searches.items()
    }
    comparison = IndexComparison(
        ids["default"],
        ids["index"],
        ids["exact"],
        {mode: plan for mode, (_, plan) in searches.items()},
    )

    model = _RecordingModel(context.language_model) if context.language_model else None
    started = time.perf_counter()
    try:
        with context.session_factory() as session:
            record = ask_question(
                session,
                context.user,
                context.workspace_id,
                asked,
                settings=settings,
                embeddings=context.embeddings,
                language_model=model,
            )
    except AppError as error:
        raise EvaluationError(f"{question.id} couldn't be asked: {error.message}") from None
    seconds = time.perf_counter() - started

    answer = record.answer
    evidence = [
        passage.chunk_id
        for passage in found[: settings.retrieval_top_k]
        if passage.similarity >= settings.retrieval_min_similarity
    ]
    cited = [citation.passage.chunk_id for citation in answer.citations]
    if answer.mode is AnswerMode.GENERATED:
        evidence_matches = set(cited) <= set(evidence)
    else:
        evidence_matches = cited == evidence
    outcome = AnswerOutcome(
        answer, model.prompt if model else None, model.reply if model else None, seconds
    )
    return QuestionResult(
        Retrieval(question, judge(question, (FoundPassage.of(passage) for passage in found))),
        comparison,
        score_answer(question, outcome),
        evidence_matches,
        model.seconds if model else None,
    )


def _search(context: _Context, vector: Sequence[float], mode: str) -> tuple[list[Passage], str]:
    """The closest chunks found one way, and how PostgreSQL read the chunks to find them."""
    workspace_id, user_id = context.workspace_id, context.user.id
    with context.session_factory() as session:
        # SET LOCAL lasts until the transaction ends, so the plan is the search's own.
        for setting in SEARCH_MODES[mode]:
            session.execute(text(f"SET LOCAL {setting}"))
        passages = chunk_repository.search_workspace(
            session, workspace_id, user_id, vector, SEARCH_LIMIT
        )
        statement = chunk_repository.search_statement(workspace_id, user_id, vector, SEARCH_LIMIT)
        plan = session.execute(_Explain(statement)).scalar_one()
        session.rollback()
    return passages, chunk_access(plan)


def _environment(session_factory: sessionmaker[Session]) -> Json:
    """What the results depend on besides the code and the data. Never the computer's name, its
    users, or its paths."""
    with session_factory() as session:
        server_version = session.scalar(text("SHOW server_version"))
        pgvector = session.scalar(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        )
        # Using the vector type loads pgvector, which defines its settings.
        session.execute(text("SELECT '[1,2,3]'::vector"))
        ef_search = session.scalar(text("SELECT current_setting('hnsw.ef_search', true)"))
        session.rollback()
    return {
        "python": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "logical_cpus": os.cpu_count(),
        "packages": {name: _package_version(name) for name in _PACKAGES},
        "postgresql": str(server_version).split()[0] if server_version else None,
        "pgvector": pgvector,
        "hnsw_ef_search": int(ef_search) if ef_search else None,
    }


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None
