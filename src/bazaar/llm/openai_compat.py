"""Adapter for any OpenAI-compatible chat completions endpoint.

Works with OpenRouter, Groq, Gemini's OpenAI endpoint, vLLM, local proxies, etc.
Conversion functions are pure and module-level so they can be unit-tested without a network.
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from typing import Any

import openai
from openai import AsyncOpenAI

from bazaar.config import LLMSettings
from bazaar.llm.base import LLMError, LLMResponse, Message, Role, ToolCall, ToolSpec, Usage


def message_to_openai(message: Message) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": message.role.value, "content": message.content}
    if message.role is Role.ASSISTANT and message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ]
    if message.role is Role.TOOL:
        payload["tool_call_id"] = message.tool_call_id
    return payload


def tool_to_openai(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def parse_arguments(raw: str | None) -> tuple[dict[str, Any], str | None]:
    """Parse tool-call arguments. Returns ``(arguments, error)``; never raises."""
    if not raw or not raw.strip():
        return {}, None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, f"arguments are not valid JSON: {exc.msg}"
    if not isinstance(value, dict):
        return {}, f"arguments must be a JSON object, got {type(value).__name__}"
    return value, None


class OpenAICompatClient:
    """``LLMClient`` implementation backed by the official ``openai`` SDK."""

    def __init__(self, settings: LLMSettings, *, client: AsyncOpenAI | None = None) -> None:
        if not settings.model:
            raise ValueError("BAZAAR_LLM_MODEL is not set")
        self._model = settings.model
        self._client = client or AsyncOpenAI(
            api_key=settings.api_key.get_secret_value() or "missing-key",
            base_url=settings.base_url,
            timeout=settings.timeout_s,
            max_retries=settings.max_retries,  # SDK retries 429/5xx with backoff
        )

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ToolSpec] = (),
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [message_to_openai(m) for m in messages],
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = [tool_to_openai(t) for t in tools]
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        started = time.perf_counter()
        try:
            completion = await self._client.chat.completions.create(**kwargs)
        except openai.OpenAIError as exc:
            # Never include request content in the error: it may contain customer data.
            raise LLMError(f"{type(exc).__name__} from LLM provider") from exc
        latency_ms = (time.perf_counter() - started) * 1000

        if not completion.choices:
            raise LLMError("LLM provider returned no choices")
        choice = completion.choices[0]

        calls: list[ToolCall] = []
        for raw_call in choice.message.tool_calls or []:
            if raw_call.type != "function":
                continue  # we only declare function tools
            arguments, error = parse_arguments(raw_call.function.arguments)
            calls.append(
                ToolCall(
                    id=raw_call.id,
                    name=raw_call.function.name,
                    arguments=arguments,
                    arguments_error=error,
                )
            )

        usage = completion.usage
        return LLMResponse(
            message=Message(
                role=Role.ASSISTANT,
                content=choice.message.content,
                tool_calls=tuple(calls),
            ),
            usage=Usage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
            model=completion.model or self._model,
            latency_ms=latency_ms,
            finish_reason=choice.finish_reason,
        )
