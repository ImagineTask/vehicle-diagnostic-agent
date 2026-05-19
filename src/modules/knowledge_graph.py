"""Neo4j FMEA knowledge graph client with 15 Cypher query helpers."""

from __future__ import annotations

import logging
from typing import Any, Optional

try:
    from neo4j import AsyncGraphDatabase, AsyncDriver
except ImportError:  # pragma: no cover - optional dep guard
    AsyncGraphDatabase = None  # type: ignore
    AsyncDriver = None  # type: ignore

from src.config.settings import settings
from src.models.kg_models import (
    KGAction,
    KGCausalChain,
    KGCause,
    KGEffect,
    KGFailureMode,
    KGQueryResult,
)

logger = logging.getLogger(__name__)


class KnowledgeGraphClient:
    """Async Neo4j client. Methods return Pydantic KG models or raw dicts."""

    def __init__(self) -> None:
        self._driver: Optional[AsyncDriver] = None  # type: ignore[valid-type]

    # --- lifecycle -------------------------------------------------------

    async def connect(self) -> None:
        if AsyncGraphDatabase is None:
            logger.warning("neo4j driver not installed — KG client is a no-op")
            return
        if self._driver is not None:
            return
        self._driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD.get_secret_value()),
        )
        await self.verify_connectivity()

    async def close(self) -> None:
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    async def verify_connectivity(self) -> bool:
        if self._driver is None:
            return False
        try:
            await self._driver.verify_connectivity()
            return True
        except Exception as e:
            logger.error("Neo4j connectivity check failed: %s", e)
            return False

    # --- low-level helper -----------------------------------------------

    async def _run(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        if self._driver is None:
            logger.debug("Neo4j driver not connected; returning empty result for: %s", cypher.splitlines()[0])
            return []
        async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            result = await session.run(cypher, **params)
            return [record.data() async for record in result]

    # --- 15 query methods ------------------------------------------------

    async def get_failure_modes_for_dtc(self, dtc_code: str) -> list[KGFailureMode]:
        cypher = """
        MATCH (d:DTC {code: $code})-[:ASSERTS]->(fm:FailureMode)
        OPTIONAL MATCH (fm)-[:PART_OF]->(c:Component)
        RETURN fm.id AS id, fm.name AS name, fm.description AS description,
               c.name AS component, fm.severity_hint AS severity_hint
        """
        rows = await self._run(cypher, code=dtc_code)
        return [KGFailureMode(**r) for r in rows]

    async def get_causes_for_failure_mode(self, failure_mode_id: str) -> list[KGCause]:
        cypher = """
        MATCH (c:Cause)-[:CAUSES]->(fm:FailureMode {id: $id})
        RETURN c.id AS id, c.name AS name, c.description AS description,
               c.occurrence AS occurrence
        """
        rows = await self._run(cypher, id=failure_mode_id)
        return [KGCause(**r) for r in rows]

    async def get_effects_for_failure_mode(self, failure_mode_id: str) -> list[KGEffect]:
        cypher = """
        MATCH (fm:FailureMode {id: $id})-[:PRODUCES_EFFECT]->(e:Effect)
        RETURN e.id AS id, e.name AS name, e.description AS description,
               coalesce(e.observable, true) AS observable
        """
        rows = await self._run(cypher, id=failure_mode_id)
        return [KGEffect(**r) for r in rows]

    async def get_mitigations_for_effect(self, effect_id: str) -> list[KGAction]:
        cypher = """
        MATCH (a:MitigationAction)-[:MITIGATES]->(e:Effect {id: $id})
        RETURN a.id AS id, a.name AS name, 'mitigation' AS kind,
               a.description AS description, e.name AS target
        """
        rows = await self._run(cypher, id=effect_id)
        return [KGAction(**r) for r in rows]

    async def get_corrective_actions_for_cause(self, cause_id: str) -> list[KGAction]:
        cypher = """
        MATCH (a:CorrectiveAction)-[:REPAIRS]->(c:Cause {id: $id})
        RETURN a.id AS id, a.name AS name, 'corrective' AS kind,
               a.description AS description, c.name AS target
        """
        rows = await self._run(cypher, id=cause_id)
        return [KGAction(**r) for r in rows]

    async def get_causal_chain(self, dtc_code: str, max_depth: int = 4) -> list[KGCausalChain]:
        cypher = """
        MATCH path = (d:DTC {code: $code})-[:ASSERTS]->(fm:FailureMode)
                    <-[:CAUSES]-(c:Cause)
        OPTIONAL MATCH (fm)-[:PRODUCES_EFFECT]->(e:Effect)
        RETURN [c.name, fm.name, coalesce(e.name, '')] AS nodes,
               ['CAUSES', 'PRODUCES_EFFECT'] AS relationships
        LIMIT $max_depth
        """
        rows = await self._run(cypher, code=dtc_code, max_depth=max_depth)
        return [KGCausalChain(**r) for r in rows]

    async def get_component_for_dtc(self, dtc_code: str) -> Optional[str]:
        cypher = """
        MATCH (d:DTC {code: $code})-[:ASSERTS]->(:FailureMode)-[:PART_OF]->(c:Component)
        RETURN c.name AS name LIMIT 1
        """
        rows = await self._run(cypher, code=dtc_code)
        return rows[0]["name"] if rows else None

    async def get_sensors_for_dtc(self, dtc_code: str) -> list[str]:
        cypher = """
        MATCH (d:DTC {code: $code})-[:ASSERTS]->(:FailureMode)-[:MEASURED_BY]->(s:Sensor)
        RETURN DISTINCT s.name AS name
        """
        rows = await self._run(cypher, code=dtc_code)
        return [r["name"] for r in rows]

    async def search_failure_modes_by_symptom(self, symptom: str) -> list[KGFailureMode]:
        cypher = """
        MATCH (e:Effect)-[:PRODUCES_EFFECT]-(fm:FailureMode)
        WHERE toLower(e.name) CONTAINS toLower($symptom)
        RETURN fm.id AS id, fm.name AS name, fm.description AS description,
               null AS component, fm.severity_hint AS severity_hint
        LIMIT 25
        """
        rows = await self._run(cypher, symptom=symptom)
        return [KGFailureMode(**r) for r in rows]

    async def get_dtc_description(self, dtc_code: str) -> Optional[str]:
        cypher = "MATCH (d:DTC {code: $code}) RETURN d.description AS description"
        rows = await self._run(cypher, code=dtc_code)
        return rows[0]["description"] if rows else None

    async def get_related_dtcs(self, dtc_code: str) -> list[str]:
        cypher = """
        MATCH (d:DTC {code: $code})-[:ASSERTS]->(fm:FailureMode)<-[:ASSERTS]-(other:DTC)
        WHERE other.code <> $code
        RETURN DISTINCT other.code AS code LIMIT 10
        """
        rows = await self._run(cypher, code=dtc_code)
        return [r["code"] for r in rows]

    async def get_subsystem_for_component(self, component: str) -> Optional[str]:
        cypher = """
        MATCH (c:Component {name: $name})-[:PART_OF]->(s:Subsystem)
        RETURN s.name AS name LIMIT 1
        """
        rows = await self._run(cypher, name=component)
        return rows[0]["name"] if rows else None

    async def list_all_dtcs(self, limit: int = 100) -> list[str]:
        cypher = "MATCH (d:DTC) RETURN d.code AS code LIMIT $limit"
        rows = await self._run(cypher, limit=limit)
        return [r["code"] for r in rows]

    async def count_nodes(self) -> dict[str, int]:
        cypher = """
        MATCH (n)
        RETURN labels(n)[0] AS label, count(*) AS count
        """
        rows = await self._run(cypher)
        return {r["label"]: r["count"] for r in rows if r.get("label")}

    async def gather_for_dtcs(self, dtc_codes: list[str]) -> KGQueryResult:
        """High-level helper: gathers everything relevant for a list of DTCs."""
        result = KGQueryResult(dtc_codes=list(dtc_codes))
        for code in dtc_codes:
            fms = await self.get_failure_modes_for_dtc(code)
            result.failure_modes.extend(fms)
            for fm in fms:
                result.causes.extend(await self.get_causes_for_failure_mode(fm.id))
                effects = await self.get_effects_for_failure_mode(fm.id)
                result.effects.extend(effects)
                for e in effects:
                    result.mitigations.extend(await self.get_mitigations_for_effect(e.id))
            for cause in result.causes:
                result.corrective_actions.extend(
                    await self.get_corrective_actions_for_cause(cause.id)
                )
            result.causal_chains.extend(await self.get_causal_chain(code))
        # de-dupe by id
        result.failure_modes = list({fm.id: fm for fm in result.failure_modes}.values())
        result.causes = list({c.id: c for c in result.causes}.values())
        result.effects = list({e.id: e for e in result.effects}.values())
        result.mitigations = list({m.id: m for m in result.mitigations}.values())
        result.corrective_actions = list({a.id: a for a in result.corrective_actions}.values())
        return result
