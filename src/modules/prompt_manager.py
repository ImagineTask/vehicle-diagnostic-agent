"""Prompt manager — handles template substitution + optional Langfuse fetch/cache."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from src.config.prompts_config import PromptConfig, get_prompt
from src.config.settings import settings

logger = logging.getLogger(__name__)


class PromptManager:
    """Compiles prompts: optionally fetches the latest version from Langfuse,
    then substitutes {{variable}} placeholders.
    """

    def __init__(self) -> None:
        self._langfuse: Optional[Any] = None
        self._template_cache: dict[str, str] = {}

    def attach_langfuse(self, langfuse_client: Any) -> None:
        self._langfuse = langfuse_client

    def _fetch_template(self, prompt: PromptConfig) -> str:
        if prompt.name in self._template_cache:
            return self._template_cache[prompt.name]
        template = prompt.template
        if self._langfuse and prompt.langfuse_prompt_name:
            try:
                lf_prompt = self._langfuse.get_prompt(prompt.langfuse_prompt_name)
                if lf_prompt and getattr(lf_prompt, "prompt", None):
                    template = lf_prompt.prompt
            except Exception as e:
                logger.warning(
                    "Langfuse prompt fetch failed for %s, falling back to local: %s",
                    prompt.langfuse_prompt_name,
                    e,
                )
        self._template_cache[prompt.name] = template
        return template

    def compile(self, prompt_name: str, variables: dict[str, Any]) -> str:
        prompt = get_prompt(prompt_name)
        template = self._fetch_template(prompt)
        missing = [v for v in prompt.variables if v not in variables]
        if missing:
            logger.warning("Prompt '%s' missing variables: %s", prompt_name, missing)
        return _substitute(template, variables)

    def schema_for(self, prompt_name: str):
        return get_prompt(prompt_name).output_schema

    def agent_for(self, prompt_name: str) -> str:
        return get_prompt(prompt_name).agent_name


_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def _substitute(template: str, variables: dict[str, Any]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in variables:
            return match.group(0)
        return str(variables[key])

    return _VAR_RE.sub(repl, template)
