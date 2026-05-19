"""Pydantic models representing entities returned from Neo4j FMEA KG queries."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class KGFailureMode(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    component: Optional[str] = None
    severity_hint: Optional[str] = None


class KGCause(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    occurrence: Optional[str] = None


class KGEffect(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    observable: bool = True


class KGAction(BaseModel):
    id: str
    name: str
    kind: str  # "mitigation" | "corrective"
    description: Optional[str] = None
    target: Optional[str] = None


class KGCausalChain(BaseModel):
    nodes: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)


class KGQueryResult(BaseModel):
    dtc_codes: list[str] = Field(default_factory=list)
    failure_modes: list[KGFailureMode] = Field(default_factory=list)
    causes: list[KGCause] = Field(default_factory=list)
    effects: list[KGEffect] = Field(default_factory=list)
    mitigations: list[KGAction] = Field(default_factory=list)
    corrective_actions: list[KGAction] = Field(default_factory=list)
    causal_chains: list[KGCausalChain] = Field(default_factory=list)

    def to_prompt_context(self) -> str:
        """Render the KG result as a compact text block for LLM prompts."""
        parts: list[str] = []
        if self.failure_modes:
            parts.append("Failure modes:")
            parts.extend(f"  - {fm.name}: {fm.description or ''}" for fm in self.failure_modes)
        if self.causes:
            parts.append("Causes:")
            parts.extend(f"  - {c.name}: {c.description or ''}" for c in self.causes)
        if self.effects:
            parts.append("Effects:")
            parts.extend(f"  - {e.name}: {e.description or ''}" for e in self.effects)
        if self.mitigations:
            parts.append("Mitigations:")
            parts.extend(f"  - {a.name}" for a in self.mitigations)
        if self.corrective_actions:
            parts.append("Corrective actions:")
            parts.extend(f"  - {a.name}" for a in self.corrective_actions)
        return "\n".join(parts) if parts else "(no KG data available)"
