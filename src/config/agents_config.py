"""Agent definitions. Agents self-register in AGENT_REGISTRY via __post_init__."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LLMProvider(str, Enum):
    AZURE_OPENAI = "azure_openai"
    GEMINI = "gemini"


AGENT_REGISTRY: dict[str, "AgentConfig"] = {}


@dataclass
class AgentConfig:
    name: str
    provider: LLMProvider
    model: str
    system_prompt: str
    temperature: float = 0.1
    max_output_tokens: int = 2048
    azure_region: Optional[str] = "primary"
    response_format: str = "json_schema"
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.name in AGENT_REGISTRY:
            return
        AGENT_REGISTRY[self.name] = self


def get_agent(name: str) -> AgentConfig:
    if name not in AGENT_REGISTRY:
        raise KeyError(f"Agent '{name}' not registered. Known agents: {list(AGENT_REGISTRY)}")
    return AGENT_REGISTRY[name]


def clear_agent_registry() -> None:
    """Test helper — clears registered agents to avoid state leaks between tests."""
    AGENT_REGISTRY.clear()


# --- Shared system prompt fragments ---

_BASE_FMEA_CONTEXT = (
    "You are a vehicle diagnostic assistant grounded in FMEA (Failure Mode and Effects Analysis) data. "
    "You reason over a knowledge graph of failure modes, causes, effects, and detection methods. "
    "Never fabricate diagnoses — always justify conclusions using the KG context provided. "
    "Always return valid JSON matching the requested schema."
)


# --- Azure OpenAI agents (4) ---

AgentConfig(
    name="triage_agent_azure",
    provider=LLMProvider.AZURE_OPENAI,
    model="gpt-4o",
    system_prompt=(
        f"{_BASE_FMEA_CONTEXT}\n\n"
        "TASK: Triage fault codes. Rank DTC codes by severity, identify urgency, "
        "and flag conditions that require immediate driver attention."
    ),
    tags=["triage", "azure"],
)

AgentConfig(
    name="telemetry_agent_azure",
    provider=LLMProvider.AZURE_OPENAI,
    model="gpt-4o",
    system_prompt=(
        f"{_BASE_FMEA_CONTEXT}\n\n"
        "TASK: Analyse vehicle sensor time-series for anomalies. Identify outliers, "
        "trends, and correlations relevant to the active DTCs."
    ),
    tags=["telemetry", "azure"],
)

AgentConfig(
    name="root_cause_agent_azure",
    provider=LLMProvider.AZURE_OPENAI,
    model="gpt-4o",
    system_prompt=(
        f"{_BASE_FMEA_CONTEXT}\n\n"
        "TASK: Identify root cause. Trace the causal chain backwards from observed effects "
        "and failure modes to the most likely underlying cause. Provide confidence with reasoning."
    ),
    tags=["root_cause", "azure"],
)

AgentConfig(
    name="impact_agent_azure",
    provider=LLMProvider.AZURE_OPENAI,
    model="gpt-4o",
    system_prompt=(
        f"{_BASE_FMEA_CONTEXT}\n\n"
        "TASK: Assess impact. Evaluate safety, reliability, cost, and compliance implications "
        "of the diagnosed fault. Recommend mitigations and corrective actions."
    ),
    tags=["impact", "azure"],
)

# --- Gemini agents (4) ---

AgentConfig(
    name="triage_agent_gemini",
    provider=LLMProvider.GEMINI,
    model="gemini-2.0-flash-001",
    system_prompt=(
        f"{_BASE_FMEA_CONTEXT}\n\n"
        "TASK: Triage fault codes. Rank DTC codes by severity, identify urgency, "
        "and flag conditions that require immediate driver attention."
    ),
    response_format="json_in_prompt",
    tags=["triage", "gemini"],
)

AgentConfig(
    name="telemetry_agent_gemini",
    provider=LLMProvider.GEMINI,
    model="gemini-2.0-flash-001",
    system_prompt=(
        f"{_BASE_FMEA_CONTEXT}\n\n"
        "TASK: Analyse vehicle sensor time-series for anomalies."
    ),
    response_format="json_in_prompt",
    tags=["telemetry", "gemini"],
)

AgentConfig(
    name="root_cause_agent_gemini",
    provider=LLMProvider.GEMINI,
    model="gemini-2.0-flash-001",
    system_prompt=(
        f"{_BASE_FMEA_CONTEXT}\n\n"
        "TASK: Identify root cause."
    ),
    response_format="json_in_prompt",
    tags=["root_cause", "gemini"],
)

AgentConfig(
    name="impact_agent_gemini",
    provider=LLMProvider.GEMINI,
    model="gemini-2.0-flash-001",
    system_prompt=(
        f"{_BASE_FMEA_CONTEXT}\n\n"
        "TASK: Assess impact."
    ),
    response_format="json_in_prompt",
    tags=["impact", "gemini"],
)

# --- Test agent (echo) ---

AgentConfig(
    name="test_echo_agent",
    provider=LLMProvider.AZURE_OPENAI,
    model="gpt-4o",
    system_prompt="Echo the user's input back as JSON: {\"echo\": <input>}.",
    temperature=0.0,
    tags=["test"],
)
