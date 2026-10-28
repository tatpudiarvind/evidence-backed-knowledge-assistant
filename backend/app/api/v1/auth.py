from fastapi import APIRouter, Response

from app.api.deps import (
    SESSION_COOKIE_NAME,
    CurrentUser,
    DbSession,
    PasswordsDep,
    SessionToken,
    SettingsDep,
)
from app.api.v1.schemas import LoginRequest, RegisterRequest, UserOut
from app.core.config import Settings
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(
    response: Response, settings: Settings, signed_in: auth_service.SignedIn
) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        signed_in.session_token,
        max_age=signed_in.max_age_seconds,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )


def _user_out(signed_in: auth_service.SignedIn) -> UserOut:
    return UserOut(id=signed_in.user.id, email=signed_in.user.email)


@router.post("/register", status_code=201, summary="Create an account and sign in")
def register(
    body: RegisterRequest,
    response: Response,
    session: DbSession,
    passwords: PasswordsDep,
    settings: SettingsDep,
) -> UserOut:
    signed_in = auth_service.register(session, passwords, settings, body.email, body.password)
    _set_session_cookie(response, settings, signed_in)
    return _user_out(signed_in)


@router.post("/login", summary="Sign in")
def login(
    body: LoginRequest,
    response: Response,
    session: DbSession,
    passwords: PasswordsDep,
    settings: SettingsDep,
    previous_token: SessionToken,
) -> UserOut:
    signed_in = auth_service.login(
        session, passwords, settings, body.email, body.password, previous_token
    )
    _set_session_cookie(response, settings, signed_in)
    return _user_out(signed_in)


@router.post("/logout", status_code=204, summary="Sign out", response_class=Response)
def logout(session: DbSession, settings: SettingsDep, token: SessionToken) -> Response:
    auth_service.logout(session, token)
    response = Response(status_code=204)
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return response


@router.get("/me", summary="Get the signed-in user")
def me(user: CurrentUser) -> UserOut:
    return UserOut(id=user.id, email=user.email)
