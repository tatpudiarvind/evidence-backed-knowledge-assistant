"""Sign-in through an OpenID Connect provider (Phase 10, D-85).

The API is the provider's client and runs the authorization code flow itself: it exchanges the
code with its client secret and a PKCE verifier, and checks the ID token that comes back as
OpenID Connect Core §3.1.3.7 requires. The tokens are never given to the browser or stored; only
the issuer and the subject are kept. A maintained library (PyJWT) verifies the signature, and
nothing here is cryptography.
"""

import base64
import hmac
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

import jwt

from app.core.config import Settings, is_loopback_host
from app.providers.llm import _NoRedirects

logger = logging.getLogger(__name__)

# What a provider's ID tokens may be signed with. Never "none", and never a shared-secret
# algorithm, which would let anyone who knows the client secret make tokens.
ALLOWED_ALGORITHMS = ("RS256", "PS256", "ES256")
_MAX_RESPONSE_BYTES = 1024 * 1024
_DISCOVERY_TTL_SECONDS = 3600.0
# An unknown key id makes the API fetch the provider's keys again, but at most this often, so
# tokens with made-up key ids can't make it fetch them on every request.
_KEYS_REFRESH_SECONDS = 30.0
_CLOCK_LEEWAY_SECONDS = 60
_REQUIRED_CLAIMS = ["exp", "iat", "iss", "aud", "sub"]
_MAX_SUBJECT_LENGTH = 255


class OidcError(Exception):
    """A sign-in that can't finish. `code` is safe to show; the message is for the log only."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


@dataclass(frozen=True)
class OidcIdentity:
    issuer: str
    subject: str
    email: str | None
    email_verified: bool


class OidcProvider(Protocol):
    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str: ...

    def complete(self, *, code: str, code_verifier: str, nonce: str) -> OidcIdentity: ...


def _check_endpoint(url: object, name: str) -> str:
    if not isinstance(url, str):
        raise OidcError("provider_unavailable", f"The provider's {name} is missing.")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username:
        raise OidcError("provider_unavailable", f"The provider's {name} isn't a plain URL.")
    if parts.scheme != "https" and not is_loopback_host(parts.hostname):
        raise OidcError("provider_unavailable", f"The provider's {name} isn't https.")
    return url


class OpenIdConnectProvider:
    def __init__(
        self,
        settings: Settings,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        assert settings.oidc_issuer and settings.oidc_client_id and settings.oidc_client_secret
        assert settings.oidc_redirect_uri
        self._issuer = settings.oidc_issuer
        self._client_id = settings.oidc_client_id
        self._client_secret = settings.oidc_client_secret
        self._redirect_uri = settings.oidc_redirect_uri
        self._scopes = settings.oidc_scopes
        self._timeout = settings.oidc_timeout_seconds
        self._clock = clock
        hostname = urlsplit(self._issuer).hostname or ""
        # A provider on this computer is reached directly; any other follows the environment's
        # proxy settings. Redirects are never followed, so the secret can't be sent elsewhere.
        self._opener = urllib.request.build_opener(
            _NoRedirects,
            *([urllib.request.ProxyHandler({})] if is_loopback_host(hostname) else []),
        )
        self._lock = threading.Lock()
        self._discovery: dict[str, Any] | None = None
        self._discovery_at = 0.0
        self._keys: list[dict[str, Any]] = []
        self._keys_at: float | None = None

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        endpoint = _check_endpoint(
            self._get_discovery().get("authorization_endpoint"), "authorization endpoint"
        )
        parts = urlsplit(endpoint)
        query = parse_qsl(parts.query, keep_blank_values=True)
        query += [
            ("response_type", "code"),
            ("client_id", self._client_id),
            ("redirect_uri", self._redirect_uri),
            ("scope", self._scopes),
            ("state", state),
            ("nonce", nonce),
            ("code_challenge", code_challenge),
            ("code_challenge_method", "S256"),
        ]
        return urlunsplit(parts._replace(query=urlencode(query)))

    def complete(self, *, code: str, code_verifier: str, nonce: str) -> OidcIdentity:
        token_endpoint = _check_endpoint(
            self._get_discovery().get("token_endpoint"), "token endpoint"
        )
        # The client secret goes in the Authorization header (RFC 6749 §2.3.1), form-encoded
        # first, as the RFC says.
        credentials = (
            f"{quote_plus(self._client_id)}:{quote_plus(self._client_secret.get_secret_value())}"
        )
        body = urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._redirect_uri,
                "client_id": self._client_id,
                "code_verifier": code_verifier,
            }
        ).encode()
        reply = self._request(
            token_endpoint,
            data=body,
            headers={
                "Authorization": "Basic " + base64.b64encode(credentials.encode()).decode(),
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            refused_statuses=(400, 401),
        )
        id_token = reply.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise OidcError("sign_in_refused", "The token reply has no ID token.")
        return self._verify(id_token, nonce)

    def _verify(self, id_token: str, nonce: str) -> OidcIdentity:
        try:
            header = jwt.get_unverified_header(id_token)
            algorithm = header.get("alg")
            if algorithm not in ALLOWED_ALGORITHMS:
                raise OidcError("sign_in_refused", "The ID token's algorithm isn't allowed.")
            key = self._signing_key(header.get("kid"), algorithm)
            claims = jwt.decode(
                id_token,
                key,
                algorithms=list(ALLOWED_ALGORITHMS),
                audience=self._client_id,
                issuer=self._issuer,
                leeway=_CLOCK_LEEWAY_SECONDS,
                options={"require": _REQUIRED_CLAIMS},
            )
        except jwt.PyJWTError as error:
            raise OidcError(
                "sign_in_refused", f"ID token refused: {type(error).__name__}"
            ) from None
        received_nonce = claims.get("nonce")
        if not isinstance(received_nonce, str) or not hmac.compare_digest(
            received_nonce.encode(), nonce.encode()
        ):
            raise OidcError("sign_in_refused", "The ID token's nonce doesn't match.")
        audience = claims["aud"]
        authorized_party = claims.get("azp")
        if (isinstance(audience, list) and len(audience) > 1 and authorized_party is None) or (
            authorized_party is not None and authorized_party != self._client_id
        ):
            raise OidcError("sign_in_refused", "The ID token's authorized party is wrong.")
        subject = claims["sub"]
        if not isinstance(subject, str) or not 1 <= len(subject) <= _MAX_SUBJECT_LENGTH:
            raise OidcError("sign_in_refused", "The ID token's subject is unusable.")
        email = claims.get("email")
        return OidcIdentity(
            issuer=self._issuer,
            subject=subject,
            email=email if isinstance(email, str) else None,
            # Only a literal true counts; a string such as "false" must not.
            email_verified=claims.get("email_verified") is True,
        )

    def _signing_key(self, key_id: object, algorithm: str) -> Any:
        keys = self._get_keys(refresh=False)
        match = self._find_key(keys, key_id)
        if match is None:
            match = self._find_key(self._get_keys(refresh=True), key_id)
        if match is None:
            raise OidcError("sign_in_refused", "The ID token's key isn't one of the provider's.")
        try:
            return jwt.PyJWK.from_dict(match, algorithm=algorithm).key
        except jwt.PyJWTError:
            raise OidcError("sign_in_refused", "The provider's key doesn't fit.") from None

    @staticmethod
    def _find_key(keys: list[dict[str, Any]], key_id: object) -> dict[str, Any] | None:
        for key in keys:
            if key.get("kid") == key_id and key.get("use", "sig") == "sig":
                return key
        return None

    def _get_discovery(self) -> dict[str, Any]:
        with self._lock:
            now = self._clock()
            if self._discovery is not None and now - self._discovery_at < _DISCOVERY_TTL_SECONDS:
                return self._discovery
        url = self._issuer.rstrip("/") + "/.well-known/openid-configuration"
        document = self._request(_check_endpoint(url, "discovery address"))
        # The document must name the issuer that was configured (OpenID Connect Discovery
        # §4.3), or a provider could be impersonated through a look-alike address.
        if document.get("issuer") != self._issuer:
            raise OidcError("provider_unavailable", "The discovery document names another issuer.")
        with self._lock:
            self._discovery = document
            self._discovery_at = self._clock()
        return document

    def _get_keys(self, *, refresh: bool) -> list[dict[str, Any]]:
        with self._lock:
            now = self._clock()
            if self._keys_at is not None:
                if not refresh:
                    return self._keys
                if now - self._keys_at < _KEYS_REFRESH_SECONDS:
                    return self._keys
        jwks_uri = _check_endpoint(self._get_discovery().get("jwks_uri"), "key set address")
        document = self._request(jwks_uri)
        keys = document.get("keys")
        if not isinstance(keys, list):
            raise OidcError("provider_unavailable", "The provider's key set is unusable.")
        usable = [key for key in keys if isinstance(key, dict)]
        with self._lock:
            self._keys = usable
            self._keys_at = self._clock()
        return usable

    def _request(
        self,
        url: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        refused_statuses: tuple[int, ...] = (),
    ) -> dict[str, Any]:
        request = urllib.request.Request(url, data=data, headers=headers or {})
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                payload = response.read(_MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            if error.code in refused_statuses:
                raise OidcError("sign_in_refused", f"The provider refused: {error.code}") from None
            raise OidcError("provider_unavailable", f"The provider replied {error.code}.") from None
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise OidcError(
                "provider_unavailable", f"The provider can't be reached: {type(error).__name__}"
            ) from None
        if len(payload) > _MAX_RESPONSE_BYTES:
            raise OidcError("provider_unavailable", "The provider's reply is too large.")
        try:
            document = json.loads(payload)
        except ValueError:
            raise OidcError("provider_unavailable", "The provider's reply isn't JSON.") from None
        if not isinstance(document, dict):
            raise OidcError("provider_unavailable", "The provider's reply isn't an object.")
        return document
