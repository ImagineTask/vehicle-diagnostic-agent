"""Diagnostic HTTP endpoints. Thin wrapper around DiagnosticWorkflow."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from src.auth.auth import bearer_dependency
from src.models.request_response import (
    DiagnosticRequest,
    DiagnosticResponse,
    ResponseFormat,
)
from src.modules.utils import to_yaml

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnostic", tags=["diagnostic"])


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

    # KG is required for grounded diagnostics; refuse rather than silently
    # returning empty results when the graph is down.
    if not getattr(request.app.state, "kg_healthy", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge graph is unavailable",
        )

    workflow = request.app.state.workflow

    try:
        summary, stages = await workflow.run(payload)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Pipeline failed for case %s", payload.case_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Diagnostic pipeline failed: {e}",
        ) from e

    response = DiagnosticResponse(
        case_id=payload.case_id,
        summary=summary,
        stage_outputs=stages,
    )
    return _render(response, payload.response_format)


def _render(response: DiagnosticResponse, fmt: ResponseFormat) -> Response:
    if fmt == ResponseFormat.YAML:
        body = to_yaml(response.model_dump(mode="json"))
        return Response(content=body, media_type="application/x-yaml")
    return Response(
        content=response.model_dump_json(),
        media_type="application/json",
    )
