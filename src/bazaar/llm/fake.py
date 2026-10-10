"""A scripted, deterministic ``LLMClient`` for tests and offline CI runs."""

from __future__ import annotations

from collections.abc import Sequence

from bazaar.llm.base import LLMError, LLMResponse, Message, Role, ToolCall, ToolSpec, Usage


class FakeLLM:
    """Returns pre-scripted responses in order and records every request it receives."""

    def __init__(self, script: Sequence[Message], *, model: str = "fake-llm") -> None:
        self._script = list(script)
        self._model = model
        self.requests: list[tuple[tuple[Message, ...], tuple[ToolSpec, ...]]] = []

    @staticmethod
    def says(text: str) -> Message:
        return Message(role=Role.ASSISTANT, content=text)

    @staticmethod
    def calls(*calls: ToolCall) -> Message:
        return Message(role=Role.ASSISTANT, tool_calls=tuple(calls))

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ToolSpec] = (),
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.requests.append((tuple(messages), tuple(tools)))
        if not self._script:
            raise LLMError("FakeLLM script exhausted")
        reply = self._script.pop(0)
        return LLMResponse(
            message=reply,
            usage=Usage(
                input_tokens=sum(len(m.content or "") for m in messages) // 4,
                output_tokens=len(reply.content or "") // 4,
            ),
            model=self._model,
            latency_ms=0.0,
            finish_reason="tool_calls" if reply.tool_calls else "stop",
        )
