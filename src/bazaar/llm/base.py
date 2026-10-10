"""Core types for talking to a chat model with tool calling.

These are our own types, not a provider's. Every provider adapter converts to and from them,
so swapping providers never touches agent or benchmark code (see docs/adr/0002).
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    """A model's request to run one tool.

    ``arguments_error`` is set (and ``arguments`` left empty) when the model produced
    arguments that are not a valid JSON object. Weak models do this; the agent must be able
    to report it back to the model instead of crashing.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    arguments_error: str | None = None


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Role
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None  # set on Role.TOOL messages

    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role=Role.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role=Role.USER, content=content)

    @classmethod
    def tool_result(cls, tool_call_id: str, content: str) -> Message:
        return cls(role=Role.TOOL, content=content, tool_call_id=tool_call_id)


class ToolSpec(BaseModel):
    """A tool the model may call. ``parameters`` is a JSON Schema object."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    description: str
    parameters: dict[str, Any]


class Usage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


class LLMResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    message: Message
    usage: Usage
    model: str
    latency_ms: float
    finish_reason: str | None = None


class LLMError(RuntimeError):
    """Raised when the provider fails after retries. Callers decide the fallback."""


@runtime_checkable
class LLMClient(Protocol):
    """Anything that can complete a conversation. Real providers and test fakes both fit."""

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ToolSpec] = (),
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse: ...
