"""Adapter tests run the real openai SDK against a mocked HTTP transport (no network)."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

import httpx2 as httpx
import pytest
from openai import AsyncOpenAI
from pydantic import SecretStr

from bazaar.config import LLMSettings
from bazaar.llm import LLMError, Message, Role, ToolCall, ToolSpec
from bazaar.llm.openai_compat import (
    OpenAICompatClient,
    message_to_openai,
    parse_arguments,
)

SETTINGS = LLMSettings(base_url="https://llm.test/v1", api_key=SecretStr("k"), model="m-1")

CEK_STOK = ToolSpec(
    name="cek_stok",
    description="Cek stok produk per varian.",
    parameters={
        "type": "object",
        "properties": {"sku": {"type": "string"}},
        "required": ["sku"],
    },
)


def completion(message: dict[str, Any], finish_reason: str = "stop") -> dict[str, Any]:
    return {
        "id": "cmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "m-1",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
    }


Handler = Callable[[httpx.Request], httpx.Response]


def make_client(
    handler: Handler, captured: list[dict[str, Any]] | None = None
) -> OpenAICompatClient:
    def wrapped(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(json.loads(request.content))
        return handler(request)

    sdk = AsyncOpenAI(
        api_key="k",
        base_url="https://llm.test/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(wrapped)),
    )
    return OpenAICompatClient(SETTINGS, client=sdk)


async def test_plain_text_reply() -> None:
    client = make_client(
        lambda _: httpx.Response(
            200, json=completion({"role": "assistant", "content": "Halo kak!"})
        )
    )
    resp = await client.complete([Message.user("halo")])

    assert resp.message.role is Role.ASSISTANT
    assert resp.message.content == "Halo kak!"
    assert resp.message.tool_calls == ()
    assert resp.usage.input_tokens == 12
    assert resp.usage.output_tokens == 5
    assert resp.finish_reason == "stop"


async def test_tool_call_is_parsed_and_tools_are_sent() -> None:
    captured: list[dict[str, Any]] = []
    tool_message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "cek_stok", "arguments": '{"sku": "KMJ-01-M"}'},
            }
        ],
    }
    client = make_client(
        lambda _: httpx.Response(200, json=completion(tool_message, "tool_calls")),
        captured,
    )
    resp = await client.complete([Message.user("kemeja M ready?")], tools=[CEK_STOK])

    assert resp.message.tool_calls == (
        ToolCall(id="call_1", name="cek_stok", arguments={"sku": "KMJ-01-M"}),
    )
    assert captured[0]["tools"][0]["function"]["name"] == "cek_stok"
    assert captured[0]["temperature"] == 0.0


async def test_malformed_tool_arguments_do_not_crash() -> None:
    tool_message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "cek_stok", "arguments": "{sku: KMJ"},
            }
        ],
    }
    client = make_client(lambda _: httpx.Response(200, json=completion(tool_message, "tool_calls")))
    resp = await client.complete([Message.user("x")], tools=[CEK_STOK])

    call = resp.message.tool_calls[0]
    assert call.arguments == {}
    assert call.arguments_error is not None


async def test_provider_error_becomes_llm_error_without_leaking_content() -> None:
    client = make_client(lambda _: httpx.Response(500, json={"error": {"message": "boom"}}))
    with pytest.raises(LLMError) as excinfo:
        await client.complete([Message.user("rahasia pelanggan: 0812xxxx")])
    assert "0812" not in str(excinfo.value)


def test_missing_model_is_rejected_early() -> None:
    with pytest.raises(ValueError, match="BAZAAR_LLM_MODEL"):
        OpenAICompatClient(LLMSettings(model=""))


@pytest.mark.parametrize(
    ("raw", "expected_args", "has_error"),
    [
        ('{"a": 1}', {"a": 1}, False),
        ("", {}, False),
        (None, {}, False),
        ("[1, 2]", {}, True),
        ("not json", {}, True),
    ],
)
def test_parse_arguments(raw: str | None, expected_args: dict[str, Any], has_error: bool) -> None:
    args, error = parse_arguments(raw)
    assert args == expected_args
    assert (error is not None) is has_error


def test_assistant_tool_call_round_trips_to_openai_format() -> None:
    msg = Message(
        role=Role.ASSISTANT,
        tool_calls=(ToolCall(id="c1", name="cek_stok", arguments={"sku": "A"}),),
    )
    payload = message_to_openai(msg)
    assert payload["tool_calls"][0]["function"]["arguments"] == '{"sku": "A"}'

    tool_payload = message_to_openai(Message.tool_result("c1", '{"stok": 3}'))
    assert tool_payload["tool_call_id"] == "c1"


@pytest.mark.live
@pytest.mark.skipif(os.getenv("BAZAAR_RUN_LIVE") != "1", reason="set BAZAAR_RUN_LIVE=1 to run")
async def test_live_smoke() -> None:
    """Hits the configured endpoint once. Uses your .env settings."""
    from bazaar.config import get_llm_settings

    client = OpenAICompatClient(get_llm_settings())
    resp = await client.complete(
        [Message.user("Balas hanya dengan satu kata: halo")], max_tokens=10
    )
    assert resp.message.content
