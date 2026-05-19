"""FastAPI app factory: CORS, lifespan, routers, health endpoint."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from src import __version__
from src.config.settings import settings
from src.lifespan import lifespan
from src.models.request_response import HealthResponse
from src.routers import diagnostic_router

logger = logging.getLogger(__name__)


def _resolve_cors_origins() -> list[str]:
    """Local dev gets a wildcard; every other env must opt-in via env var."""
    configured = settings.CORS_ALLOW_ORIGINS
    if configured:
        return configured
    if settings.ENVIRONMENT == "local":
        return ["*"]
    logger.warning(
        "CORS_ALLOW_ORIGINS is empty in env=%s — cross-origin requests will be blocked",
        settings.ENVIRONMENT,
    )
    return []


def create_app() -> FastAPI:
    app = FastAPI(
        title="Vehicle Diagnostic Agent",
        version=__version__,
        description="FMEA-grounded vehicle diagnostic pipeline (FastAPI + Neo4j + LLM).",
        lifespan=lifespan,
    )

    origins = _resolve_cors_origins()
    # Wildcard + credentials is invalid per the CORS spec; force-disable
    # credentials when "*" is in use so we never ship the unsafe combo.
    allow_credentials = settings.CORS_ALLOW_CREDENTIALS and "*" not in origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(diagnostic_router)

    @app.get("/health", response_model=HealthResponse, tags=["meta"])
    async def health(request: Request) -> HealthResponse:
        kg_healthy = bool(getattr(request.app.state, "kg_healthy", False))
        langfuse_state = "enabled" if getattr(request.app.state, "langfuse", None) else "disabled"
        validator = getattr(request.app.state, "token_validator", None)
        auth_state = type(validator).__name__ if validator else "unconfigured"
        return HealthResponse(
            status="ok" if kg_healthy else "degraded",
            neo4j="connected" if kg_healthy else "disconnected",
            auth=auth_state,
            langfuse=langfuse_state,
            version=__version__,
        )

    return app


app = create_app()
