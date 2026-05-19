"""Neo4j FMEA knowledge graph schema definitions."""

from __future__ import annotations

from enum import Enum


class NodeLabel(str, Enum):
    ASSET = "Asset"
    COMPONENT = "Component"
    SUBSYSTEM = "Subsystem"
    FAILURE_MODE = "FailureMode"
    CAUSE = "Cause"
    EFFECT = "Effect"
    DETECTION_METHOD = "DetectionMethod"
    DTC = "DTC"
    MITIGATION_ACTION = "MitigationAction"
    CORRECTIVE_ACTION = "CorrectiveAction"
    SEVERITY = "Severity"
    OCCURRENCE = "Occurrence"
    SENSOR = "Sensor"


class Relationship(str, Enum):
    ASSERTS = "ASSERTS"
    PRODUCES_EFFECT = "PRODUCES_EFFECT"
    CAUSES = "CAUSES"
    MITIGATES = "MITIGATES"
    REPAIRS = "REPAIRS"
    PART_OF = "PART_OF"
    HAS_DTC = "HAS_DTC"
    MEASURED_BY = "MEASURED_BY"
    AFFECTS = "AFFECTS"


class KGSchema:
    """Static schema reference used by Cypher query builders."""

    NODES = [label.value for label in NodeLabel]
    RELATIONSHIPS = [rel.value for rel in Relationship]

    ENTRY_POINTS = {
        "dtc_code": NodeLabel.DTC.value,
        "detection_method": NodeLabel.DETECTION_METHOD.value,
        "symptom": NodeLabel.EFFECT.value,
    }
