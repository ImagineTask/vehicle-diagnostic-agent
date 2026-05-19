"""Diagnostic HTTP endpoints.

NOTE: The /run-case handler inlines its own 5-stage pipeline rather than
calling pipeline.workflow.DiagnosticWorkflow. This matches the documented
behaviour in the architecture handover ("Router != workflow.py"). If you add
new stages, update BOTH this file and workflow.py until they're consolidated.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from src.config.settings import settings
from src.models.diagnostic_models import (
    DiagnosisSummary,
    ImpactOutput,
    RootCauseOutput,
    Severity,
    TelemetryOutput,
    TriageOutput,
    Urgency,
)
from src.models.request_response import (
    DiagnosticRequest,
    DiagnosticResponse,
    ResponseFormat,
)
from src.modules.utils import to_yaml
from src.auth.auth import bearer_dependency

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnostic", tags=["diagnostic"])


# Pipeline-wide semaphore — gates total in-flight pipelines.
_pipeline_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_DIAGNOSTICS)


async def _validate_token(request: Request, auth_payload: dict[str, Any]) -> None:
    validator = getattr(request.app.state, "token_validator", None)
    if validator is None:
        return
    token = auth_payload.get("_raw_token")
    await validator.validate(token)


@router.post("/run-case", response_model=None)
async def run_case(
    payload: DiagnosticRequest,
    request: Request,
    auth: dict[str, Any] = Depends(bearer_dependency),
) -> Response:
    await _validate_token(request, auth)

    kg = request.app.state.kg
    prompts = request.app.state.prompts
    runner = request.app.state.runner

    async with _pipeline_semaphore:
        try:
            dtc_codes = [d.code for d in payload.dtc_codes]

            # --- Stage 1: Data Gathering -----------------------------------
            kg_data = await kg.gather_for_dtcs(dtc_codes)

            # --- Stage 2: Triage -------------------------------------------
            triage_prompt = prompts.compile(
                "triage_prompt",
                {
                    "vehicle_info": payload.vehicle.model_dump_json(),
                    "dtc_codes": ", ".join(dtc_codes),
                    "kg_context": kg_data.to_prompt_context(),
                },
            )
            triage: TriageOutput = await runner.run(  # type: ignore[assignment]
                prompts.agent_for("triage_prompt"),
                triage_prompt,
                prompts.schema_for("triage_prompt"),
            )

            # --- Stage 3: Telemetry (optional) ------------------------------
            telemetry: Optional[TelemetryOutput] = None
            if payload.telemetry:
                telemetry_prompt = prompts.compile(
                    "telemetry_prompt",
                    {
                        "dtc_codes": ", ".join(dtc_codes),
                        "telemetry": _summarise_telemetry(payload.telemetry),
                        "kg_sensor_links": ", ".join(
                            fm.component or "" for fm in kg_data.failure_modes
                        ),
                    },
                )
                telemetry = await runner.run(  # type: ignore[assignment]
                    prompts.agent_for("telemetry_prompt"),
                    telemetry_prompt,
                    prompts.schema_for("telemetry_prompt"),
                )

            # --- Stage 4: Root Cause ---------------------------------------
            root_cause_prompt = prompts.compile(
                "root_cause_prompt",
                {
                    "triage_results": triage.model_dump_json(),
                    "telemetry_findings": telemetry.model_dump_json() if telemetry else "(none)",
                    "causal_chains": "\n".join(
                        " -> ".join(ch.nodes) for ch in kg_data.causal_chains
                    ) or "(none)",
                },
            )
            root_cause: RootCauseOutput = await runner.run(  # type: ignore[assignment]
                prompts.agent_for("root_cause_prompt"),
                root_cause_prompt,
                prompts.schema_for("root_cause_prompt"),
            )

            # --- Stage 5: Impact -------------------------------------------
            impact_prompt = prompts.compile(
                "impact_prompt",
                {
                    "root_cause": root_cause.root_cause,
                    "effects": ", ".join(e.name for e in kg_data.effects) or "(none)",
                    "mitigations": ", ".join(m.name for m in kg_data.mitigations) or "(none)",
                    "corrective_actions": ", ".join(
                        a.name for a in kg_data.corrective_actions
                    ) or "(none)",
                },
            )
            impact: ImpactOutput = await runner.run(  # type: ignore[assignment]
                prompts.agent_for("impact_prompt"),
                impact_prompt,
                prompts.schema_for("impact_prompt"),
            )

            summary = _assemble_summary(triage, root_cause, impact, dtc_codes)

            response = DiagnosticResponse(
                case_id=payload.case_id,
                summary=summary,
                stage_outputs={
                    "data_gathering": kg_data.model_dump(),
                    "triage": triage.model_dump(),
                    "telemetry": telemetry.model_dump() if telemetry else None,
                    "root_cause": root_cause.model_dump(),
                    "impact": impact.model_dump(),
                },
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Pipeline failed for case %s", payload.case_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Diagnostic pipeline failed: {e}",
            ) from e

    return _render(response, payload.response_format)


# ---- helpers ----------------------------------------------------------------


def _assemble_summary(
    triage: TriageOutput,
    root_cause: RootCauseOutput,
    impact: ImpactOutput,
    dtc_codes: list[str],
) -> DiagnosisSummary:
    primary = triage.ranked_codes[0] if triage.ranked_codes else None
    return DiagnosisSummary(
        root_cause=root_cause.root_cause,
        confidence=root_cause.confidence,
        urgency=triage.overall_urgency or Urgency.LOW,
        primary_dtc=primary.code if primary else (dtc_codes[0] if dtc_codes else "UNKNOWN"),
        primary_dtc_description=primary.description if primary else None,
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
        samples = r.samples[:5]
        rendered = ", ".join(f"{ts.isoformat()}={v}" for ts, v in samples)
        parts.append(f"{r.sensor} ({r.unit or '?'}): {rendered}")
    return "\n".join(parts)


def _render(response: DiagnosticResponse, fmt: ResponseFormat) -> Response:
    if fmt == ResponseFormat.YAML:
        body = to_yaml(response.model_dump(mode="json"))
        return Response(content=body, media_type="application/x-yaml")
    return Response(
        content=response.model_dump_json(),
        media_type="application/json",
    )
