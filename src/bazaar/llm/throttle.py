"""Client-side request pacing, so free-tier rate limits are respected instead of hit."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence

from bazaar.llm.base import LLMClient, LLMResponse, Message, ToolSpec


class ThrottledClient:
    """Wraps any ``LLMClient`` and spaces requests at most ``rpm`` per minute.

    Concurrent callers share one schedule, so the limit holds across parallel trials.
    """

    def __init__(self, inner: LLMClient, rpm: float) -> None:
        if rpm <= 0:
            raise ValueError("rpm must be positive")
        self._inner = inner
        self._interval = 60.0 / rpm
        self._lock = asyncio.Lock()
        self._next_slot = 0.0

    async def _wait_for_slot(self) -> None:
        async with self._lock:
            now = time.monotonic()
            start = max(now, self._next_slot)
            self._next_slot = start + self._interval
        delay = start - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ToolSpec] = (),
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        await self._wait_for_slot()
        return await self._inner.complete(
            messages, tools=tools, temperature=temperature, max_tokens=max_tokens
        )
