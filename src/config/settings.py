"""Application settings loaded from env files via Pydantic Settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("env/config.env", "env/credentials.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # --- Environment ---
    ENVIRONMENT: Literal["local", "dev", "staging", "prod"] = "local"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    DEBUG: bool = False

    # --- Concurrency limits ---
    MAX_CONCURRENT_DIAGNOSTICS: int = 10
    MAX_CONCURRENT_LLM_CALLS: int = 5

    # --- Neo4j ---
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: SecretStr = SecretStr("neo4j")
    NEO4J_DATABASE: str = "neo4j"

    # --- Azure OpenAI (multi-region support) ---
    AZURE_REGION_PRIMARY_ENDPOINT: Optional[str] = None
    AZURE_REGION_PRIMARY_API_KEY: Optional[SecretStr] = None
    AZURE_REGION_PRIMARY_DEPLOYMENT: str = "gpt-4o"
    AZURE_OPENAI_API_VERSION: str = "2024-08-01-preview"

    AZURE_REGION_SECONDARY_ENDPOINT: Optional[str] = None
    AZURE_REGION_SECONDARY_API_KEY: Optional[SecretStr] = None
    AZURE_REGION_SECONDARY_DEPLOYMENT: str = "gpt-4o"

    # --- Gemini ---
    GEMINI_API_KEY: Optional[SecretStr] = None
    GEMINI_PROJECT_ID: Optional[str] = None
    GEMINI_LOCATION: str = "us-central1"
    GEMINI_USE_VERTEX: bool = False
    GEMINI_DEFAULT_MODEL: str = "gemini-2.0-flash-001"

    # --- Langfuse ---
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[SecretStr] = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    # --- Auth ---
    USE_AUTH: bool = False
    AUTH_PROVIDER: Literal["none", "hardcoded", "keycloak"] = "none"
    HARD_CODED_TOKEN: Optional[SecretStr] = None
    KEYCLOAK_JWKS_URL: Optional[str] = None
    KEYCLOAK_ISSUER: Optional[str] = None
    KEYCLOAK_AUDIENCE: Optional[str] = None

    # --- LLM retry / timeout ---
    LLM_REQUEST_TIMEOUT_SECONDS: int = 60
    LLM_MAX_RETRIES: int = 3
    LLM_RETRY_INITIAL_DELAY: float = 1.0
    LLM_RETRY_MAX_DELAY: float = 10.0

    # --- API ---
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    CORS_ALLOW_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
