"""Pydantic schemas for each diagnostic pipeline stage's structured LLM output."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Urgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DataGatheringOutput(BaseModel):
    failure_modes: list[str] = Field(default_factory=list)
    known_causes: list[str] = Field(default_factory=list)
    known_effects: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class TriageItem(BaseModel):
    code: str
    description: Optional[str] = None
    severity: Severity
    urgency: Urgency
    reasoning: str


class TriageOutput(BaseModel):
    ranked_codes: list[TriageItem] = Field(default_factory=list)
    immediate_attention_required: bool = False
    overall_urgency: Urgency = Urgency.LOW


class TelemetryFinding(BaseModel):
    sensor: str
    observation: str
    severity: Severity
    correlated_dtc: Optional[str] = None


class TelemetryOutput(BaseModel):
    findings: list[TelemetryFinding] = Field(default_factory=list)
    overall_assessment: str = ""


class RootCauseOutput(BaseModel):
    root_cause: str
    confidence: Confidence
    reasoning: str
    causal_chain: list[str] = Field(default_factory=list)


class ImpactOutput(BaseModel):
    safety_risk: Severity
    can_continue_driving: bool
    estimated_cost: str = ""
    recommended_action: str
    compliance_notes: Optional[str] = None
    reliability_impact: Optional[str] = None
    mechanic_notes: Optional[str] = None


class DiagnosisSummary(BaseModel):
    """Final driver-facing summary assembled from all pipeline stages."""

    root_cause: str
    confidence: Confidence
    urgency: Urgency
    primary_dtc: str
    primary_dtc_description: Optional[str] = None
    estimated_cost: str
    recommended_action: str
    safety_risk: Severity
    can_continue_driving: bool
    mechanic_notes: Optional[str] = None


class EchoOutput(BaseModel):
    echo: str
