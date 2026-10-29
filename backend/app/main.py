import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import CSRF_HEADER_NAME
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.database import create_database_engine, create_session_factory
from app.core.errors import register_error_handlers
from app.core.middleware import REQUEST_ID_HEADER, RequestIdMiddleware, UnhandledErrorMiddleware
from app.core.security import PasswordHashing
from app.providers.embeddings import EmbeddingProvider, SentenceTransformerEmbeddings
from app.providers.llm import LanguageModel, OllamaChatModel
from app.providers.storage import LocalDocumentStorage
from app.services.ingestion import DocumentIndexer
from app.workers.ingestion import IngestionWorker
from app.workers.retention import QuestionCleanupWorker


def create_app(
    settings: Settings | None = None,
    *,
    passwords: PasswordHashing | None = None,
    embeddings: EmbeddingProvider | None = None,
    language_model: LanguageModel | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    storage = LocalDocumentStorage(settings.storage_dir)
    # The model loads on first use, so creating the app stays fast.
    embeddings = embeddings or SentenceTransformerEmbeddings(settings)
    worker = IngestionWorker(DocumentIndexer(session_factory, storage, embeddings, settings))
    # Without a model, answers list the passages that match the question.
    if language_model is None and settings.llm_provider == "ollama":
        language_model = OllamaChatModel(settings)
    cleanup = QuestionCleanupWorker(session_factory)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if settings.ingestion_worker_enabled:
            worker.start()
        if settings.question_cleanup_enabled:
            cleanup.start()
        try:
            yield
        finally:
            # Waits for the document being indexed, if any, without blocking the event loop.
            await asyncio.to_thread(worker.stop)
            await asyncio.to_thread(cleanup.stop)
            engine.dispose()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.storage = storage
    app.state.passwords = passwords or PasswordHashing()
    app.state.embeddings = embeddings
    app.state.language_model = language_model
    app.state.ingestion_worker = worker
    app.state.question_cleanup = cleanup

    register_error_handlers(app)
    # The last middleware added runs first: request ID, then CORS, then the error fallback.
    # Errors are turned into JSON inside CORS, so browsers can read them.
    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", CSRF_HEADER_NAME],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(RequestIdMiddleware)
    app.include_router(api_router)
    return app


app = create_app()
