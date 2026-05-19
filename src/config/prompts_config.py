"""Prompt templates + Pydantic output schemas. Prompts self-register on import."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Type

from pydantic import BaseModel

from src.config.settings import settings
from src.models.diagnostic_models import (
    DataGatheringOutput,
    TriageOutput,
    TelemetryOutput,
    RootCauseOutput,
    ImpactOutput,
    DiagnosisSummary,
    EchoOutput,
)


PROMPT_REGISTRY: dict[str, "PromptConfig"] = {}


@dataclass
class PromptConfig:
    name: str
    agent_name: str
    template: str
    output_schema: Type[BaseModel]
    langfuse_prompt_name: Optional[str] = None
    variables: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.name in PROMPT_REGISTRY:
            return
        PROMPT_REGISTRY[self.name] = self


def get_prompt(name: str) -> PromptConfig:
    if name not in PROMPT_REGISTRY:
        raise KeyError(f"Prompt '{name}' not registered. Known: {list(PROMPT_REGISTRY)}")
    return PROMPT_REGISTRY[name]


def clear_prompt_registry() -> None:
    PROMPT_REGISTRY.clear()


# --- 1. Data Gathering (KG-only, no LLM call usually, but a prompt is provided) ---

PromptConfig(
    name="data_gathering_prompt",
    agent_name="triage_agent_azure",
    template=(
        "Summarise the FMEA knowledge graph data retrieved for the following DTC codes.\n"
        "DTC codes: {{dtc_codes}}\n"
        "KG data:\n{{kg_data}}\n\n"
        "Return JSON with: failure_modes (list), known_causes (list), known_effects (list)."
    ),
    output_schema=DataGatheringOutput,
    langfuse_prompt_name="vda/data_gathering",
    variables=["dtc_codes", "kg_data"],
)


# --- 2. Triage ---

PromptConfig(
    name="triage_prompt",
    agent_name="triage_agent_azure",
    template=(
        "You are triaging vehicle fault codes.\n"
        "Vehicle: {{vehicle_info}}\n"
        "Active DTCs: {{dtc_codes}}\n"
        "KG context (failure modes, severity hints):\n{{kg_context}}\n\n"
        "Rank the DTCs from most to least urgent. For each, output: "
        "code, severity (low|medium|high|critical), urgency (low|medium|high), reasoning. "
        "Set immediate_attention_required if any code is critical."
    ),
    output_schema=TriageOutput,
    langfuse_prompt_name="vda/triage",
    variables=["vehicle_info", "dtc_codes", "kg_context"],
)


# --- 3. Telemetry (optional) ---

PromptConfig(
    name="telemetry_prompt",
    agent_name="telemetry_agent_azure",
    template=(
        "Analyse the following sensor telemetry for anomalies relevant to the active DTCs.\n"
        "DTCs: {{dtc_codes}}\n"
        "Sensor readings (time-series):\n{{telemetry}}\n"
        "KG-linked sensors:\n{{kg_sensor_links}}\n\n"
        "Identify out-of-range readings, suspicious trends, and correlations with the DTCs."
    ),
    output_schema=TelemetryOutput,
    langfuse_prompt_name="vda/telemetry",
    variables=["dtc_codes", "telemetry", "kg_sensor_links"],
)


# --- 4. Root Cause ---

PromptConfig(
    name="root_cause_prompt",
    agent_name="root_cause_agent_azure",
    template=(
        "Identify the most likely root cause given:\n"
        "Triage results: {{triage_results}}\n"
        "Telemetry findings: {{telemetry_findings}}\n"
        "Causal chains from KG:\n{{causal_chains}}\n\n"
        "Trace the causal chain backwards from observed effects to the root cause. "
        "Provide root_cause, confidence (low|medium|high), reasoning, "
        "and the supporting causal_chain as a list of nodes."
    ),
    output_schema=RootCauseOutput,
    langfuse_prompt_name="vda/root_cause",
    variables=["triage_results", "telemetry_findings", "causal_chains"],
)


# --- 5. Impact ---

PromptConfig(
    name="impact_prompt",
    agent_name="impact_agent_azure",
    template=(
        "Assess the impact of the diagnosed fault.\n"
        "Root cause: {{root_cause}}\n"
        "Affected effects: {{effects}}\n"
        "Mitigation actions from KG: {{mitigations}}\n"
        "Corrective actions from KG: {{corrective_actions}}\n\n"
        "Evaluate: safety_risk, can_continue_driving, estimated_cost (currency band), "
        "recommended_action (driver-facing), compliance_notes (if any), reliability_impact."
    ),
    output_schema=ImpactOutput,
    langfuse_prompt_name="vda/impact",
    variables=["root_cause", "effects", "mitigations", "corrective_actions"],
)


# --- 6. Summary assembly (no LLM, but schema kept for symmetry) ---

PromptConfig(
    name="summary_prompt",
    agent_name="impact_agent_azure",
    template=(
        "Assemble a driver-facing diagnosis summary from:\n"
        "Triage: {{triage}}\n"
        "Root cause: {{root_cause}}\n"
        "Impact: {{impact}}\n\n"
        "Return the DiagnosisSummary JSON."
    ),
    output_schema=DiagnosisSummary,
    langfuse_prompt_name="vda/summary",
    variables=["triage", "root_cause", "impact"],
)


# --- 7. Test echo prompt ---
# Gated alongside the test_echo_agent in agents_config.py.

if settings.ENVIRONMENT != "prod":
    PromptConfig(
        name="test_echo_prompt",
        agent_name="test_echo_agent",
        template="Echo this input as JSON: {{input}}",
        output_schema=EchoOutput,
        variables=["input"],
    )
