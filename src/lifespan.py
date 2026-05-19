"""FastAPI lifespan — initialise Neo4j, Langfuse, auth, prompt manager, agent runner."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI

from src.auth.auth import build_token_validator
from src.config.settings import settings
from src.modules.agent_runner import AgentRunner
from src.modules.knowledge_graph import KnowledgeGraphClient
from src.modules.prompt_manager import PromptManager
from src.pipeline.workflow import DiagnosticWorkflow

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Set log level idempotently. basicConfig() is a no-op if already configured,
    so apply the level directly to the root logger."""
    level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level)
    root.setLevel(level)


def _init_langfuse() -> Optional[Any]:
    if not settings.LANGFUSE_ENABLED:
        return None
    try:
        from langfuse import Langfuse  # type: ignore
    except ImportError:
        logger.warning("langfuse not installed — observability disabled")
        return None
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        logger.warning("Langfuse keys missing — observability disabled")
        return None
    return Langfuse(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY.get_secret_value(),
        host=settings.LANGFUSE_HOST,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _configure_logging()
    logger.info("Starting vehicle diagnostic agent (env=%s)", settings.ENVIRONMENT)

    # --- Neo4j ---
    kg = KnowledgeGraphClient()
    await kg.connect()
    app.state.kg = kg
    app.state.kg_healthy = await kg.verify_connectivity()
    if not app.state.kg_healthy and settings.ENVIRONMENT in {"staging", "prod"}:
        # Fail startup loudly rather than serving traffic with a dead KG.
        await kg.close()
        raise RuntimeError(
            f"Neo4j connectivity check failed in env={settings.ENVIRONMENT}; refusing to start"
        )

    # --- Langfuse ---
    langfuse = _init_langfuse()
    app.state.langfuse = langfuse

    # --- Prompt manager ---
    prompts = PromptManager()
    if langfuse is not None:
        prompts.attach_langfuse(langfuse)
    app.state.prompts = prompts

    # --- Agent runner ---
    runner = AgentRunner()
    app.state.runner = runner

    # --- Workflow (single instance — owns the pipeline-wide semaphore) ---
    app.state.workflow = DiagnosticWorkflow(kg=kg, prompts=prompts, runner=runner)

    # --- Auth ---
    app.state.token_validator = build_token_validator()

    logger.info("Startup complete")
    try:
        yield
    finally:
        logger.info("Shutting down")
        await kg.close()
        if langfuse is not None:
            try:
                langfuse.flush()
            except Exception:  # pragma: no cover
                logger.exception("Langfuse flush failed")
