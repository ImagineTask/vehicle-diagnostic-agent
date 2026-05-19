"""API request/response schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from src.models.diagnostic_models import DiagnosisSummary


class ResponseFormat(str, Enum):
    JSON = "json"
    YAML = "yaml"


class DTCCode(BaseModel):
    code: str
    description: Optional[str] = None
    timestamp: Optional[datetime] = None

    @field_validator("code")
    @classmethod
    def normalise_code(cls, v: str) -> str:
        return v.strip().upper()


class VehicleInfo(BaseModel):
    make: str
    model: str
    year: int
    vin: Optional[str] = None
    mileage_km: Optional[int] = None


class SensorReading(BaseModel):
    sensor: str
    unit: Optional[str] = None
    samples: list[tuple[datetime, float]] = Field(default_factory=list)


class DiagnosticRequest(BaseModel):
    case_id: str
    vehicle: VehicleInfo
    dtc_codes: list[DTCCode]
    telemetry: list[SensorReading] = Field(default_factory=list)
    driver_notes: Optional[str] = None
    response_format: ResponseFormat = ResponseFormat.JSON


class DiagnosticResponse(BaseModel):
    case_id: str
    summary: DiagnosisSummary
    stage_outputs: dict[str, Any] = Field(default_factory=dict)
    trace_id: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    neo4j: str
    auth: str
    langfuse: str
    version: str
