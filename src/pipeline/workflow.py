"""Alternate 5-stage pipeline orchestrator.

NOTE: per the architecture handover, the production /run-case route in
diagnostic_router.py currently inlines its own pipeline. This module exposes the
same logic in a reusable class; new endpoints should prefer this over
duplicating the inline version. Eventually the router should be consolidated to
call DiagnosticWorkflow.run().
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from opentelemetry import trace

from src.config.settings import settings
from src.models.diagnostic_models import (
    Confidence,
    DiagnosisSummary,
    ImpactOutput,
    RootCauseOutput,
    Severity,
    TelemetryOutput,
    TriageOutput,
    Urgency,
)
from src.models.kg_models import KGQueryResult
from src.models.request_response import DiagnosticRequest
from src.modules.agent_runner import AgentRunner
from src.modules.knowledge_graph import KnowledgeGraphClient
from src.modules.prompt_manager import PromptManager

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)


class DiagnosticWorkflow:
    def __init__(
        self,
        kg: KnowledgeGraphClient,
        prompts: PromptManager,
        runner: AgentRunner,
    ) -> None:
        self.kg = kg
        self.prompts = prompts
        self.runner = runner
        self._pipeline_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_DIAGNOSTICS)

    async def run(self, request: DiagnosticRequest) -> tuple[DiagnosisSummary, dict[str, Any]]:
        with _tracer.start_as_current_span("workflow.run") as span:
            span.set_attribute("case_id", request.case_id)
            span.set_attribute("dtc_count", len(request.dtc_codes))
            span.set_attribute("has_telemetry", bool(request.telemetry))
            async with self._pipeline_semaphore:
                return await self._run_unguarded(request)

    async def _run_unguarded(
        self, request: DiagnosticRequest
    ) -> tuple[DiagnosisSummary, dict[str, Any]]:
        dtc_codes = [d.code for d in request.dtc_codes]
        stages: dict[str, Any] = {}

        # Stage 1: data gathering
        with _tracer.start_as_current_span("stage.data_gathering"):
            kg_data = await self.kg.gather_for_dtcs(dtc_codes)
            stages["data_gathering"] = kg_data.model_dump()

        # Stage 2: triage
        with _tracer.start_as_current_span("stage.triage"):
            triage = await self._run_triage(request, kg_data)
            stages["triage"] = triage.model_dump()

        # Stage 3: telemetry (optional)
        telemetry: Optional[TelemetryOutput] = None
        if request.telemetry:
            with _tracer.start_as_current_span("stage.telemetry"):
                telemetry = await self._run_telemetry(request, kg_data)
                stages["telemetry"] = telemetry.model_dump()

        # Stage 4: root cause
        with _tracer.start_as_current_span("stage.root_cause"):
            root_cause = await self._run_root_cause(triage, telemetry, kg_data)
            stages["root_cause"] = root_cause.model_dump()

        # Stage 5: impact
        with _tracer.start_as_current_span("stage.impact"):
            impact = await self._run_impact(root_cause, kg_data)
            stages["impact"] = impact.model_dump()

        summary = self._assemble_summary(triage, root_cause, impact, kg_data)
        return summary, stages

    # ---- stage helpers --------------------------------------------------

    async def _run_triage(
        self, request: DiagnosticRequest, kg_data: KGQueryResult
    ) -> TriageOutput:
        prompt_text = self.prompts.compile(
            "triage_prompt",
            {
                "vehicle_info": request.vehicle.model_dump_json(),
                "dtc_codes": ", ".join(d.code for d in request.dtc_codes),
                "kg_context": kg_data.to_prompt_context(),
            },
        )
        agent_name = self.prompts.agent_for("triage_prompt")
        schema = self.prompts.schema_for("triage_prompt")
        result = await self.runner.run(agent_name, prompt_text, schema)
        return result  # type: ignore[return-value]

    async def _run_telemetry(
        self, request: DiagnosticRequest, kg_data: KGQueryResult
    ) -> TelemetryOutput:
        prompt_text = self.prompts.compile(
            "telemetry_prompt",
            {
                "dtc_codes": ", ".join(d.code for d in request.dtc_codes),
                "telemetry": _summarise_telemetry(request.telemetry),
                "kg_sensor_links": ", ".join(fm.component or "" for fm in kg_data.failure_modes),
            },
        )
        agent_name = self.prompts.agent_for("telemetry_prompt")
        schema = self.prompts.schema_for("telemetry_prompt")
        result = await self.runner.run(agent_name, prompt_text, schema)
        return result  # type: ignore[return-value]

    async def _run_root_cause(
        self,
        triage: TriageOutput,
        telemetry: Optional[TelemetryOutput],
        kg_data: KGQueryResult,
    ) -> RootCauseOutput:
        prompt_text = self.prompts.compile(
            "root_cause_prompt",
            {
                "triage_results": triage.model_dump_json(),
                "telemetry_findings": telemetry.model_dump_json() if telemetry else "(none)",
                "causal_chains": "\n".join(
                    " -> ".join(ch.nodes) for ch in kg_data.causal_chains
                ) or "(none)",
            },
        )
        agent_name = self.prompts.agent_for("root_cause_prompt")
        schema = self.prompts.schema_for("root_cause_prompt")
        result = await self.runner.run(agent_name, prompt_text, schema)
        return result  # type: ignore[return-value]

    async def _run_impact(
        self, root_cause: RootCauseOutput, kg_data: KGQueryResult
    ) -> ImpactOutput:
        prompt_text = self.prompts.compile(
            "impact_prompt",
            {
                "root_cause": root_cause.root_cause,
                "effects": ", ".join(e.name for e in kg_data.effects) or "(none)",
                "mitigations": ", ".join(m.name for m in kg_data.mitigations) or "(none)",
                "corrective_actions": ", ".join(a.name for a in kg_data.corrective_actions)
                or "(none)",
            },
        )
        agent_name = self.prompts.agent_for("impact_prompt")
        schema = self.prompts.schema_for("impact_prompt")
        result = await self.runner.run(agent_name, prompt_text, schema)
        return result  # type: ignore[return-value]

    def _assemble_summary(
        self,
        triage: TriageOutput,
        root_cause: RootCauseOutput,
        impact: ImpactOutput,
        kg_data: KGQueryResult,
    ) -> DiagnosisSummary:
        primary = triage.ranked_codes[0] if triage.ranked_codes else None
        primary_code = primary.code if primary else (kg_data.dtc_codes[0] if kg_data.dtc_codes else "UNKNOWN")
        primary_desc = primary.description if primary else None

        return DiagnosisSummary(
            root_cause=root_cause.root_cause,
            confidence=root_cause.confidence,
            urgency=triage.overall_urgency or Urgency.LOW,
            primary_dtc=primary_code,
            primary_dtc_description=primary_desc,
            estimated_cost=impact.estimated_cost or "unknown",
            recommended_action=impact.recommended_action,
            safety_risk=impact.safety_risk or Severity.LOW,
            can_continue_driving=impact.can_continue_driving,
            mechanic_notes=impact.mechanic_notes,
        )


def _summarise_telemetry(readings: list) -> str:
    if not readings:
        return "(none)"
    parts: list[str] = []
    for r in readings:
        samples = getattr(r, "samples", None) or []
        rendered_samples: list[str] = []
        for sample in samples[:5]:
            # Tolerate either tuples or sequences from upstream parsers; skip
            # any malformed entries rather than letting them blow up the request.
            if not isinstance(sample, (tuple, list)) or len(sample) != 2:
                continue
            ts, v = sample
            ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            rendered_samples.append(f"{ts_str}={v}")
        rendered = ", ".join(rendered_samples) if rendered_samples else "(no samples)"
        parts.append(f"{r.sensor} ({r.unit or '?'}): {rendered}")
    return "\n".join(parts)
