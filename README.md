# Vehicle Diagnostic Agent

FMEA-grounded vehicle diagnostic pipeline. FastAPI service that takes DTC codes + optional telemetry, queries a Neo4j FMEA knowledge graph, runs a 5-stage LLM pipeline (data gathering → triage → telemetry → root cause → impact), and returns a driver-facing diagnosis summary.


## Architecture

Six logical components, 17 source files:

| Component   | Files |
|-------------|-------|
| API Layer   | [src/api.py](src/api.py), [src/lifespan.py](src/lifespan.py) |
| Router      | [src/routers/diagnostic_router.py](src/routers/diagnostic_router.py) |
| Pipeline    | [src/pipeline/workflow.py](src/pipeline/workflow.py) |
| Modules     | [agent_runner.py](src/modules/agent_runner.py), [knowledge_graph.py](src/modules/knowledge_graph.py), [prompt_manager.py](src/modules/prompt_manager.py), [utils.py](src/modules/utils.py) |
| Config      | [settings.py](src/config/settings.py), [agents_config.py](src/config/agents_config.py), [prompts_config.py](src/config/prompts_config.py), [kg_schema.py](src/config/kg_schema.py) |
| Models+Auth | [diagnostic_models.py](src/models/diagnostic_models.py), [kg_models.py](src/models/kg_models.py), [request_response.py](src/models/request_response.py), [auth/auth.py](src/auth/auth.py) (+ `__init__.py` for the auth package) |

## Quick start

```bash
# 1. Create venv and install
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure env
cp env/config.env.example env/config.env
cp env/credentials.env.example env/credentials.env
# edit env/credentials.env with at least one LLM provider key + NEO4J_PASSWORD

# 3. Run
python main.py
# or: uvicorn src.api:app --reload
```

Open <http://localhost:8000/docs> for the OpenAPI UI.

## Minimum to run locally

- Neo4j running at `NEO4J_URI` **plus** one LLM provider (Azure OpenAI **or** Gemini)
- Without Neo4j the pipeline still runs but the KG context will be empty
- Without an LLM the pipeline cannot complete — provide at least Azure or Gemini credentials

## Example request

```bash
curl -X POST http://localhost:8000/diagnostic/run-case \
  -H "Content-Type: application/json" \
  -d '{
    "case_id": "case-001",
    "vehicle": {"make": "Ford", "model": "Focus", "year": 2019},
    "dtc_codes": [{"code": "P0131"}],
    "response_format": "json"
  }'
```

## Pipeline

```
HTTP → Auth → Data Gathering (KG) → Triage → Telemetry* → Root Cause → Impact → Summary
                                                  ↑
                                          *optional — only if request includes telemetry
```

Each LLM stage:
1. Queries Neo4j for relevant FMEA data
2. Compiles a prompt with `{{variables}}` (optionally fetched from Langfuse)
3. Calls the agent via `AgentRunner` (Azure GPT-4o or Gemini), with retries
4. Validates the response against a Pydantic schema

Two semaphores gate concurrency: `MAX_CONCURRENT_DIAGNOSTICS` (default 10) for whole pipelines, `MAX_CONCURRENT_LLM_CALLS` (default 5) for individual LLM calls.

## Gotchas

- **Router inlines the pipeline.** [diagnostic_router.py](src/routers/diagnostic_router.py) does NOT call [workflow.py](src/pipeline/workflow.py). If you add a stage you must update both — or migrate the router to call `DiagnosticWorkflow.run()`.
- **Gemini JSON parsing is fragile.** No native `json_schema` mode — the schema is appended to the prompt text and markdown fences are stripped manually in `AgentRunner._execute_gemini`.
- **Agent/prompt registration is import-time.** `AgentConfig` and `PromptConfig` self-register via `__post_init__`. Tests must call `clear_agent_registry()` / `clear_prompt_registry()` between cases to avoid state leaks.
- **CORS is wide open** (`allow_origins=["*"]`) — tighten for production.
- **No tests yet.** Add under `tests/`.

## KG schema (FMEA, 13 node types)

Entry: `DetectionMethod -ASSERTS-> FailureMode` (DTC codes wrap this), then:

```
Cause -CAUSES-> FailureMode -PRODUCES_EFFECT-> Effect
       ↑                                         ↑
CorrectiveAction -REPAIRS-                       -MITIGATES- MitigationAction
```

See [src/config/kg_schema.py](src/config/kg_schema.py) for the full node/relationship list, and [src/modules/knowledge_graph.py](src/modules/knowledge_graph.py) for the 15 Cypher query helpers.

## Adding things

| Task | How |
|------|-----|
| New agent | Define `AgentConfig(...)` in [agents_config.py](src/config/agents_config.py) — auto-registers |
| New pipeline stage | Add output schema in [diagnostic_models.py](src/models/diagnostic_models.py), create `PromptConfig` in [prompts_config.py](src/config/prompts_config.py), wire it in [diagnostic_router.py](src/routers/diagnostic_router.py) **and** [workflow.py](src/pipeline/workflow.py) |
| New LLM provider | Add `_execute_xxx()` to [agent_runner.py](src/modules/agent_runner.py), extend `LLMProvider` enum, add routing in `_dispatch`, add settings |
