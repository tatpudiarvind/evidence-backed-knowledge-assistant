import logging
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Query, Response
from fastapi.responses import RedirectResponse

from app.api.deps import (
    SESSION_COOKIE_NAME,
    CurrentUser,
    DbSession,
    OidcDep,
    PasswordsDep,
    SessionToken,
    SettingsDep,
    limit_registration_attempts,
    limit_sign_in_attempts,
)
from app.api.v1.schemas import AuthOptionsOut, LoginRequest, RegisterRequest, UserOut
from app.core.config import Settings
from app.providers.oidc import OidcError
from app.services import auth as auth_service
from app.services import oidc as oidc_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

OIDC_LOGIN_COOKIE_NAME = "eka_oidc_login"
# The login cookie is only needed by these two routes.
_OIDC_COOKIE_PATH = "/api/v1/auth/oidc"
_SIGN_IN_ERROR_PARAMETER = "sign_in_error"


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


@router.post(
    "/register",
    status_code=201,
    summary="Create an account and sign in",
    dependencies=[Depends(limit_registration_attempts)],
)
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


@router.post("/login", summary="Sign in", dependencies=[Depends(limit_sign_in_attempts)])
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


@router.get("/options", summary="How this server lets people sign in")
def options(settings: SettingsDep) -> AuthOptionsOut:
    return AuthOptionsOut(
        password=settings.password_sign_in_enabled,
        registration=settings.password_sign_in_enabled and settings.registration_enabled,
        provider_name=settings.oidc_provider_name if settings.oidc_enabled else None,
    )


def _delete_login_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        OIDC_LOGIN_COOKIE_NAME,
        path=_OIDC_COOKIE_PATH,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _sign_in_error(settings: Settings, code: str) -> RedirectResponse:
    response = RedirectResponse(f"/?{_SIGN_IN_ERROR_PARAMETER}={code}", status_code=303)
    _delete_login_cookie(response, settings)
    return response


@router.get(
    "/oidc/login",
    status_code=302,
    summary="Start signing in through the identity provider",
    response_class=RedirectResponse,
    dependencies=[Depends(limit_sign_in_attempts)],
)
def oidc_login(
    session: DbSession,
    settings: SettingsDep,
    provider: OidcDep,
    return_to: Annotated[str | None, Query(max_length=1024)] = None,
) -> RedirectResponse:
    started = oidc_service.start_login(session, settings, provider, return_to)
    response = RedirectResponse(started.authorization_url, status_code=302)
    response.set_cookie(
        OIDC_LOGIN_COOKIE_NAME,
        started.login_token,
        max_age=started.max_age_seconds,
        path=_OIDC_COOKIE_PATH,
        secure=settings.session_cookie_secure,
        httponly=True,
        # Lax, not Strict: the provider sends the browser back with a cross-site navigation,
        # which doesn't carry Strict cookies, and this cookie must come along with it.
        samesite="lax",
    )
    return response


@router.get(
    "/oidc/callback",
    status_code=303,
    summary="Finish signing in through the identity provider",
    response_class=RedirectResponse,
    dependencies=[Depends(limit_sign_in_attempts)],
)
def oidc_callback(
    session: DbSession,
    settings: SettingsDep,
    provider: OidcDep,
    login_token: Annotated[str | None, Cookie(alias=OIDC_LOGIN_COOKIE_NAME)] = None,
    code: Annotated[str | None, Query(max_length=2048)] = None,
    state: Annotated[str | None, Query(max_length=2048)] = None,
    error: Annotated[str | None, Query(max_length=200)] = None,
) -> RedirectResponse:
    # Every failure goes back to the sign-in page with a short code and nothing else.
    if error is not None:
        oidc_service.abandon_login(session, login_token)
        logger.warning("The identity provider sent the browser back with an error")
        return _sign_in_error(settings, "sign_in_refused")
    try:
        finished = oidc_service.finish_login(session, settings, provider, login_token, code, state)
    except OidcError as failure:
        logger.warning("Provider sign-in failed: %s", failure)
        return _sign_in_error(settings, failure.code)
    # The return path was checked when the sign-in started, and was stored on the server.
    response = RedirectResponse(finished.return_to, status_code=303)
    _set_session_cookie(response, settings, finished.signed_in)
    _delete_login_cookie(response, settings)
    return response
