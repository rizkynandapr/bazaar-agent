"""The agent loop (ADR-0001): model → tool calls → results → model, until it answers in text."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from importlib.resources import files
from typing import Any

from bazaar.llm import LLMClient, Message, Usage
from bazaar.store import HANDOVER_TOOL, Store, execute, policy_text, tool_specs

STEP_LIMIT_REPLY = "Mohon maaf kak, ada kendala di sistem kami. Admin akan segera membantu ya."


@lru_cache(maxsize=8)
def load_prompt(version: str) -> str:
    return files("bazaar.agent").joinpath("prompts", f"{version}.md").read_text(encoding="utf-8")


def render_system_prompt(version: str, store: Store) -> str:
    # str.replace, not str.format: the policy text may legitimately contain braces.
    return (
        load_prompt(version)
        .replace("{store_name}", store.state.store_name)
        .replace("{today}", store.state.today.isoformat())
        .replace("{policy}", policy_text())
    )


@dataclass(frozen=True)
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    ok: bool
    output: str


@dataclass
class AgentTurn:
    reply: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    handed_over: bool = False
    hit_step_limit: bool = False


class Agent:
    def __init__(
        self,
        llm: LLMClient,
        store: Store,
        *,
        prompt_version: str = "baseline_v0",
        max_steps: int = 8,
        temperature: float = 0.0,
    ) -> None:
        self._llm = llm
        self._store = store
        self._tools = tool_specs()
        self._max_steps = max_steps
        self._temperature = temperature
        self.prompt_version = prompt_version
        self.messages: list[Message] = [Message.system(render_system_prompt(prompt_version, store))]
        self.handed_over = False

    async def respond(self, user_text: str) -> AgentTurn:
        if self.handed_over:
            raise RuntimeError("Conversation was handed over to a human")
        self.messages.append(Message.user(user_text))
        turn = AgentTurn(reply="")

        for _ in range(self._max_steps):
            response = await self._llm.complete(
                self.messages, tools=self._tools, temperature=self._temperature
            )
            turn.usage = turn.usage + response.usage
            self.messages.append(response.message)

            if not response.message.tool_calls:
                turn.reply = (response.message.content or "").strip()
                return turn

            for call in response.message.tool_calls:
                outcome = execute(self._store, call)
                turn.tool_calls.append(
                    ToolCallRecord(call.name, dict(call.arguments), outcome.ok, outcome.content)
                )
                self.messages.append(Message.tool_result(call.id, outcome.content))
                if call.name == HANDOVER_TOOL and outcome.ok:
                    turn.handed_over = self.handed_over = True

        turn.reply = STEP_LIMIT_REPLY
        turn.hit_step_limit = True
        return turn
