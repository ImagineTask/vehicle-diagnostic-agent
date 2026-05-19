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
    code: str = Field(min_length=1, max_length=16)
    description: Optional[str] = Field(default=None, max_length=512)
    timestamp: Optional[datetime] = None

    @field_validator("code")
    @classmethod
    def normalise_code(cls, v: str) -> str:
        return v.strip().upper()


class VehicleInfo(BaseModel):
    make: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=64)
    # Earliest mass-produced vehicles ~1900; cap above current year to allow pre-orders.
    year: int = Field(ge=1900, le=2100)
    vin: Optional[str] = Field(default=None, min_length=11, max_length=17)
    mileage_km: Optional[int] = Field(default=None, ge=0, le=10_000_000)


class SensorReading(BaseModel):
    sensor: str = Field(min_length=1, max_length=128)
    unit: Optional[str] = Field(default=None, max_length=32)
    # Capping samples bounds prompt size and protects the summariser.
    samples: list[tuple[datetime, float]] = Field(default_factory=list, max_length=10_000)


class DiagnosticRequest(BaseModel):
    case_id: str = Field(min_length=1, max_length=256)
    vehicle: VehicleInfo
    dtc_codes: list[DTCCode] = Field(min_length=1, max_length=64)
    telemetry: list[SensorReading] = Field(default_factory=list, max_length=64)
    driver_notes: Optional[str] = Field(default=None, max_length=4096)
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


class ReadinessCheck(BaseModel):
    name: str
    ok: bool
    detail: Optional[str] = None


class ReadinessResponse(BaseModel):
    ready: bool
    checks: list[ReadinessCheck]
    version: str
