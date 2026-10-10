"""Setup diagnostics: friendly config errors and a connection check with actionable hints."""

from __future__ import annotations

from bazaar.config import LLMSettings
from bazaar.llm import LLMError, Message
from bazaar.llm.openai_compat import OpenAICompatClient

ENV_HELP = """\
Open the .env file in the project folder (Windows: `notepad .env`) and set:

  BAZAAR_LLM_BASE_URL=<your OpenAI-compatible endpoint, usually ending in /v1>
  BAZAAR_LLM_API_KEY=<your API key>
  BAZAAR_LLM_MODEL=<model name exactly as your provider lists it>

Then run:  uv run python -m bazaar.bench ping
"""

# Map the SDK's exception class name (the cause of an LLMError) to a fix the user can act on.
HINTS = {
    "APIConnectionError": "Cannot reach BAZAAR_LLM_BASE_URL. Is the server/proxy running? "
    "Does the URL end in /v1?",
    "APITimeoutError": "The endpoint did not answer in time. Is the server/proxy running?",
    "AuthenticationError": "The API key was rejected. Check BAZAAR_LLM_API_KEY.",
    "PermissionDeniedError": "The API key is not allowed to use this model.",
    "NotFoundError": "Model or URL not found. Check BAZAAR_LLM_MODEL spelling and that "
    "BAZAAR_LLM_BASE_URL ends in /v1.",
    "RateLimitError": "Rate limited by the provider. Wait a minute or use another model.",
    "BadRequestError": "The provider rejected the request. The model may not support tool calling.",
}


def config_problems(settings: LLMSettings, *, prefix: str = "BAZAAR_LLM") -> list[str]:
    problems = []
    if not settings.model.strip():
        problems.append(f"{prefix}_MODEL is empty")
    if not settings.base_url.strip():
        problems.append(f"{prefix}_BASE_URL is empty")
    return problems


def hint_for(exc: LLMError) -> str:
    cause = exc.__cause__
    name = type(cause).__name__ if cause else ""
    return HINTS.get(name, "Unexpected error. Check the endpoint, key and model name.")


async def ping(settings: LLMSettings) -> tuple[bool, str]:
    """One tiny request. Returns (ok, human-readable line). Never includes the API key."""
    client = OpenAICompatClient(settings)
    try:
        response = await client.complete([Message.user("Reply with one word: halo")], max_tokens=20)
    except LLMError as exc:
        return False, f"{exc}. {hint_for(exc)}"
    reply = (response.message.content or "").strip().replace("\n", " ")[:40]
    return True, f"{response.latency_ms:.0f} ms, replied: {reply!r}"
