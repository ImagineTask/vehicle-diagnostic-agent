"""Token validators — NoAuth (dev), Hardcoded (dev/test), Keycloak JWT (prod)."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config.settings import settings

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


class TokenValidator(ABC):
    @abstractmethod
    async def validate(self, token: Optional[str]) -> dict[str, Any]:
        """Return claims dict on success, raise HTTPException on failure."""


class NoAuthValidator(TokenValidator):
    """Permits all requests. Use only when USE_AUTH=false."""

    async def validate(self, token: Optional[str]) -> dict[str, Any]:
        return {"sub": "anonymous", "auth": "none"}


class HardcodedTokenValidator(TokenValidator):
    """Compares against a single shared token from settings.HARD_CODED_TOKEN."""

    def __init__(self, expected_token: str) -> None:
        self._expected = expected_token

    async def validate(self, token: Optional[str]) -> dict[str, Any]:
        if not token or token != self._expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing token",
            )
        return {"sub": "hardcoded", "auth": "hardcoded"}


class KeycloakJWTValidator(TokenValidator):
    """Validates JWTs against Keycloak JWKS. Requires PyJWT[crypto]."""

    def __init__(self, jwks_url: str, issuer: str, audience: Optional[str] = None) -> None:
        self._jwks_url = jwks_url
        self._issuer = issuer
        self._audience = audience
        self._jwks_client: Any = None

    def _client(self) -> Any:
        if self._jwks_client is None:
            try:
                import jwt  # type: ignore
            except ImportError as e:
                raise RuntimeError(
                    "PyJWT[crypto] is required for KeycloakJWTValidator"
                ) from e
            self._jwks_client = jwt.PyJWKClient(self._jwks_url)
        return self._jwks_client

    async def validate(self, token: Optional[str]) -> dict[str, Any]:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token"
            )
        try:
            import jwt  # type: ignore
            from jwt import (  # type: ignore
                InvalidTokenError,
                PyJWKClientError,
            )
        except ImportError as e:
            logger.error("PyJWT not installed; cannot validate JWTs")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Auth subsystem misconfigured",
            ) from e

        try:
            signing_key = self._client().get_signing_key_from_jwt(token).key
        except PyJWKClientError as e:
            # JWKS fetch/network failure — operational issue, not a bad token.
            logger.error("JWKS retrieval failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Auth provider unavailable",
            ) from e

        try:
            options = {"verify_aud": bool(self._audience)}
            return jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options=options,
            )
        except InvalidTokenError as e:
            logger.warning("JWT validation failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            ) from e


def build_token_validator() -> TokenValidator:
    if not settings.USE_AUTH:
        return NoAuthValidator()
    provider = settings.AUTH_PROVIDER
    if provider == "none":
        return NoAuthValidator()
    if provider == "hardcoded":
        token_secret = settings.HARD_CODED_TOKEN
        if token_secret is None:
            raise RuntimeError("HARD_CODED_TOKEN must be set when AUTH_PROVIDER=hardcoded")
        return HardcodedTokenValidator(token_secret.get_secret_value())
    if provider == "keycloak":
        if not settings.KEYCLOAK_JWKS_URL or not settings.KEYCLOAK_ISSUER:
            raise RuntimeError(
                "KEYCLOAK_JWKS_URL and KEYCLOAK_ISSUER must be set for Keycloak auth"
            )
        return KeycloakJWTValidator(
            jwks_url=settings.KEYCLOAK_JWKS_URL,
            issuer=settings.KEYCLOAK_ISSUER,
            audience=settings.KEYCLOAK_AUDIENCE,
        )
    raise RuntimeError(f"Unknown AUTH_PROVIDER: {provider}")


async def bearer_dependency(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict[str, Any]:
    """FastAPI dependency. The actual validator is set on app.state at startup."""
    from fastapi import Request  # local import to avoid cycle
    import contextvars

    # The validator is attached to app.state in lifespan; routers retrieve via request.
    # This helper exists so individual routes can declare auth via Depends(bearer_dependency).
    # Concrete validation happens in the router using request.app.state.token_validator.
    token = credentials.credentials if credentials else None
    return {"_raw_token": token}
