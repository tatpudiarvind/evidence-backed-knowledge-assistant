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
from app.providers.storage import LocalDocumentStorage


def create_app(
    settings: Settings | None = None, *, passwords: PasswordHashing | None = None
) -> FastAPI:
    settings = settings or get_settings()
    engine = create_database_engine(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.storage = LocalDocumentStorage(settings.storage_dir)
    app.state.passwords = passwords or PasswordHashing()

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
