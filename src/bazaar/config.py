"""Runtime configuration, loaded from environment variables (and an optional .env file).

Secrets are typed as ``SecretStr`` so they never show up in logs, reprs or tracebacks.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """Connection settings for any OpenAI-compatible chat completions endpoint."""

    model_config = SettingsConfigDict(
        env_prefix="BAZAAR_LLM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenAI-compatible base URL (OpenRouter, Groq, Gemini, a local proxy, ...).",
    )
    api_key: SecretStr = Field(default=SecretStr(""), description="API key for the endpoint.")
    model: str = Field(default="", description="Model identifier as the provider names it.")
    timeout_s: float = Field(default=60.0, gt=0, le=600)
    max_retries: int = Field(default=3, ge=0, le=10)


class SimulatorOverrides(BaseSettings):
    """Optional ``BAZAAR_SIM_*`` overrides for the BazaarBench customer simulator.

    Anything left empty falls back to the agent's ``BAZAAR_LLM_*`` value, so a single endpoint
    is enough to run the benchmark, while a stronger simulator model can be configured separately.
    """

    model_config = SettingsConfigDict(
        env_prefix="BAZAAR_SIM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = ""
    api_key: SecretStr = SecretStr("")
    model: str = ""


@lru_cache(maxsize=1)
def get_llm_settings() -> LLMSettings:
    """Return process-wide LLM settings (cached; call ``cache_clear()`` in tests)."""
    return LLMSettings()


def simulator_settings(agent: LLMSettings, overrides: SimulatorOverrides) -> LLMSettings:
    update: dict[str, object] = {}
    if overrides.base_url:
        update["base_url"] = overrides.base_url
    if overrides.api_key.get_secret_value():
        update["api_key"] = overrides.api_key
    if overrides.model:
        update["model"] = overrides.model
    return agent.model_copy(update=update)
