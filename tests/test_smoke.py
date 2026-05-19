"""Smoke tests — imports compile, registries populate, app builds."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_imports_compile() -> None:
    import src.api  # noqa: F401
    import src.lifespan  # noqa: F401
    import src.routers.diagnostic_router  # noqa: F401
    import src.pipeline.workflow  # noqa: F401
    import src.modules.agent_runner  # noqa: F401
    import src.modules.knowledge_graph  # noqa: F401
    import src.modules.prompt_manager  # noqa: F401
    import src.modules.utils  # noqa: F401
    import src.config.settings  # noqa: F401
    import src.config.agents_config  # noqa: F401
    import src.config.prompts_config  # noqa: F401
    import src.config.kg_schema  # noqa: F401
    import src.models.diagnostic_models  # noqa: F401
    import src.models.kg_models  # noqa: F401
    import src.models.request_response  # noqa: F401
    import src.auth.auth  # noqa: F401


def test_agent_registry_populated() -> None:
    from src.config.agents_config import AGENT_REGISTRY

    assert "triage_agent_azure" in AGENT_REGISTRY
    assert "root_cause_agent_azure" in AGENT_REGISTRY
    assert "impact_agent_azure" in AGENT_REGISTRY
    assert "triage_agent_gemini" in AGENT_REGISTRY
    assert "test_echo_agent" in AGENT_REGISTRY


def test_prompt_registry_populated() -> None:
    from src.config.prompts_config import PROMPT_REGISTRY

    expected = {
        "data_gathering_prompt",
        "triage_prompt",
        "telemetry_prompt",
        "root_cause_prompt",
        "impact_prompt",
        "summary_prompt",
        "test_echo_prompt",
    }
    assert expected.issubset(PROMPT_REGISTRY.keys())


def test_app_builds() -> None:
    from src.api import create_app

    app = create_app()
    routes = {r.path for r in app.routes}
    assert "/health" in routes
    assert "/diagnostic/run-case" in routes


def test_strip_json_fences() -> None:
    from src.modules.utils import parse_json_safe

    raw = '```json\n{"a": 1}\n```'
    assert parse_json_safe(raw) == {"a": 1}
