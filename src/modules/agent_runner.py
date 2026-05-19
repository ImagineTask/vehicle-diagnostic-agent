"""LLM execution layer. Routes to Azure OpenAI or Gemini, handles retries + JSON parsing."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional, Type

from pydantic import BaseModel, ValidationError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config.agents_config import AgentConfig, LLMProvider, get_agent
from src.config.settings import settings
from src.modules.utils import parse_json_safe, strip_json_fences

logger = logging.getLogger(__name__)


class AgentRunError(Exception):
    pass


class AgentRunner:
    """Runs an agent against its configured LLM provider, returning a validated model."""

    def __init__(self) -> None:
        self._llm_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_LLM_CALLS)
        self._azure_clients: dict[str, Any] = {}
        self._gemini_client: Optional[Any] = None

    # ---- public API ------------------------------------------------------

    async def run(
        self,
        agent_name: str,
        user_prompt: str,
        output_schema: Type[BaseModel],
        trace: Optional[Any] = None,
    ) -> BaseModel:
        agent = get_agent(agent_name)
        async with self._llm_semaphore:
            return await self._run_with_retries(agent, user_prompt, output_schema, trace)

    # ---- retry + dispatch ------------------------------------------------

    async def _run_with_retries(
        self,
        agent: AgentConfig,
        user_prompt: str,
        output_schema: Type[BaseModel],
        trace: Optional[Any],
    ) -> BaseModel:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(settings.LLM_MAX_RETRIES),
            wait=wait_exponential(
                multiplier=settings.LLM_RETRY_INITIAL_DELAY,
                max=settings.LLM_RETRY_MAX_DELAY,
            ),
            retry=retry_if_exception_type((AgentRunError, ValidationError, json.JSONDecodeError)),
            reraise=True,
        ):
            with attempt:
                raw = await self._dispatch(agent, user_prompt, output_schema)
                return self._validate(raw, output_schema)
        raise AgentRunError("retry loop exhausted")  # pragma: no cover

    async def _dispatch(
        self, agent: AgentConfig, user_prompt: str, output_schema: Type[BaseModel]
    ) -> str:
        if agent.provider == LLMProvider.AZURE_OPENAI:
            return await self._execute_azure(agent, user_prompt, output_schema)
        if agent.provider == LLMProvider.GEMINI:
            return await self._execute_gemini(agent, user_prompt, output_schema)
        raise AgentRunError(f"Unknown provider: {agent.provider}")

    def _validate(self, raw_text: str, schema: Type[BaseModel]) -> BaseModel:
        try:
            data = parse_json_safe(raw_text)
        except json.JSONDecodeError as e:
            logger.warning("LLM output was not valid JSON: %s", raw_text[:200])
            raise AgentRunError(f"LLM output not valid JSON: {e}") from e
        return schema.model_validate(data)

    # ---- Azure OpenAI ----------------------------------------------------

    def _azure_client(self, region: str) -> Any:
        if region in self._azure_clients:
            return self._azure_clients[region]
        try:
            from openai import AsyncAzureOpenAI
        except ImportError as e:
            raise AgentRunError("openai package required for Azure OpenAI") from e

        if region == "primary":
            endpoint = settings.AZURE_REGION_PRIMARY_ENDPOINT
            api_key = settings.AZURE_REGION_PRIMARY_API_KEY
        else:
            endpoint = settings.AZURE_REGION_SECONDARY_ENDPOINT
            api_key = settings.AZURE_REGION_SECONDARY_API_KEY
        if not endpoint or not api_key:
            raise AgentRunError(
                f"Azure region '{region}' is not configured (endpoint/api_key missing)"
            )
        client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key.get_secret_value(),
            api_version=settings.AZURE_OPENAI_API_VERSION,
            timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS,
        )
        self._azure_clients[region] = client
        return client

    async def _execute_azure(
        self, agent: AgentConfig, user_prompt: str, output_schema: Type[BaseModel]
    ) -> str:
        client = self._azure_client(agent.azure_region or "primary")
        deployment = (
            settings.AZURE_REGION_PRIMARY_DEPLOYMENT
            if (agent.azure_region or "primary") == "primary"
            else settings.AZURE_REGION_SECONDARY_DEPLOYMENT
        )

        response_format: Any = {"type": "json_object"}
        if agent.response_format == "json_schema":
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": output_schema.__name__,
                    "schema": output_schema.model_json_schema(),
                    "strict": False,
                },
            }

        try:
            completion = await client.chat.completions.create(
                model=deployment,
                temperature=agent.temperature,
                max_tokens=agent.max_output_tokens,
                response_format=response_format,
                messages=[
                    {"role": "system", "content": agent.system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception as e:
            raise AgentRunError(f"Azure OpenAI call failed: {e}") from e

        content = completion.choices[0].message.content or ""
        return content

    # ---- Gemini ----------------------------------------------------------

    def _gemini(self) -> Any:
        if self._gemini_client is not None:
            return self._gemini_client
        if settings.GEMINI_USE_VERTEX:
            try:
                from vertexai.generative_models import GenerativeModel
                import vertexai
            except ImportError as e:
                raise AgentRunError("google-cloud-aiplatform required for Vertex") from e
            vertexai.init(
                project=settings.GEMINI_PROJECT_ID, location=settings.GEMINI_LOCATION
            )
            self._gemini_client = GenerativeModel
        else:
            try:
                import google.generativeai as genai  # type: ignore
            except ImportError as e:
                raise AgentRunError("google-generativeai required for Gemini AI Studio") from e
            if settings.GEMINI_API_KEY is None:
                raise AgentRunError("GEMINI_API_KEY not set")
            genai.configure(api_key=settings.GEMINI_API_KEY.get_secret_value())
            self._gemini_client = genai
        return self._gemini_client

    async def _execute_gemini(
        self, agent: AgentConfig, user_prompt: str, output_schema: Type[BaseModel]
    ) -> str:
        client = self._gemini()
        # No native json_schema mode — append schema as instruction text.
        schema_hint = (
            "\n\nReturn ONLY valid JSON matching this schema (no markdown fences):\n"
            f"{json.dumps(output_schema.model_json_schema(), indent=2)}"
        )
        full_prompt = f"{agent.system_prompt}\n\n{user_prompt}{schema_hint}"

        try:
            if settings.GEMINI_USE_VERTEX:
                model = client(agent.model)  # vertex: GenerativeModel(model_name)
                response = await asyncio.to_thread(model.generate_content, full_prompt)
                text = response.text
            else:
                model = client.GenerativeModel(agent.model)
                response = await asyncio.to_thread(model.generate_content, full_prompt)
                text = response.text
        except Exception as e:
            raise AgentRunError(f"Gemini call failed: {e}") from e

        return strip_json_fences(text or "")
