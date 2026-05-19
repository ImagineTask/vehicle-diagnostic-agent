"""Configuration package — settings, agent definitions, prompts, and KG schema."""

from src.config.settings import settings
from src.config.agents_config import AGENT_REGISTRY, AgentConfig, get_agent
from src.config.prompts_config import PROMPT_REGISTRY, PromptConfig, get_prompt
from src.config.kg_schema import KGSchema

__all__ = [
    "settings",
    "AGENT_REGISTRY",
    "AgentConfig",
    "get_agent",
    "PROMPT_REGISTRY",
    "PromptConfig",
    "get_prompt",
    "KGSchema",
]
