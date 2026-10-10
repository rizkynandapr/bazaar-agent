"""Runs simulated conversations between the customer simulator and the agent."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Collection, Sequence
from typing import Literal

from pydantic import BaseModel, Field

from bazaar.agent import Agent
from bazaar.bench.grader import grade
from bazaar.bench.simulator import UserSimulator
from bazaar.bench.task import Category, Task
from bazaar.llm import LLMClient, LLMError, Usage
from bazaar.store import Store

EndReason = Literal["customer_stop", "handover", "max_turns", "error"]


class TranscriptEntry(BaseModel):
    role: Literal["customer", "agent", "tool"]
    text: str
    tool: str | None = None
    ok: bool | None = None


class TrialResult(BaseModel):
    task_id: str
    category: Category
    trial: int
    passed: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    ended_by: EndReason
    turns: int
    agent_usage: Usage
    simulator_usage: Usage
    duration_s: float
    error: str | None = None
    transcript: list[TranscriptEntry] = Field(default_factory=list)


async def run_trial(
    task: Task,
    trial: int,
    *,
    agent_llm: LLMClient,
    simulator_llm: LLMClient,
    prompt_version: str = "baseline_v0",
    max_turns: int = 15,
) -> TrialResult:
    started = time.perf_counter()
    store = Store.from_seed()
    agent = Agent(agent_llm, store, prompt_version=prompt_version)
    simulator = UserSimulator(simulator_llm, task.user, store_name=store.state.store_name)

    transcript: list[TranscriptEntry] = []
    agent_said: list[str] = []
    tools_ok: list[str] = []
    agent_usage, sim_usage = Usage(), Usage()
    ended_by: EndReason = "max_turns"
    error: str | None = None
    turns = 0

    try:
        customer_text, usage = await simulator.first_message()
        sim_usage += usage
        while turns < max_turns:
            if UserSimulator.is_done(customer_text):
                ended_by = "customer_stop"
                break
            transcript.append(TranscriptEntry(role="customer", text=customer_text))

            turn = await agent.respond(customer_text)
            turns += 1
            agent_usage += turn.usage
            tools_ok += [record.name for record in turn.tool_calls if record.ok]
            for record in turn.tool_calls:
                transcript.append(
                    TranscriptEntry(
                        role="tool",
                        text=f"{record.arguments} -> {record.output}",
                        tool=record.name,
                        ok=record.ok,
                    )
                )
            transcript.append(TranscriptEntry(role="agent", text=turn.reply))
            agent_said.append(turn.reply)

            if turn.handed_over:
                ended_by = "handover"
                break
            customer_text, usage = await simulator.reply(turn.reply)
            sim_usage += usage
    except LLMError as exc:
        ended_by, error = "error", str(exc)

    result = grade(task, store.state, agent_said, tools_ok)
    passed = result.passed and error is None
    reasons = result.reasons + ([f"infrastructure error: {error}"] if error else [])
    return TrialResult(
        task_id=task.id,
        category=task.category,
        trial=trial,
        passed=passed,
        checks=result.checks,
        reasons=reasons,
        ended_by=ended_by,
        turns=turns,
        agent_usage=agent_usage,
        simulator_usage=sim_usage,
        duration_s=round(time.perf_counter() - started, 2),
        error=error,
        transcript=transcript,
    )


async def run_benchmark(
    tasks: Sequence[Task],
    *,
    trials: int,
    agent_llm: LLMClient,
    simulator_llm: LLMClient,
    prompt_version: str = "baseline_v0",
    max_turns: int = 15,
    concurrency: int = 1,
    on_result: Callable[[TrialResult], None] | None = None,
    skip: Collection[tuple[str, int]] = (),
) -> list[TrialResult]:
    """Every (task, trial) pair runs on its own fresh store; order of results is stable.

    ``skip`` lists (task_id, trial) pairs already completed in an earlier, resumed run.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def one(task: Task, trial: int) -> TrialResult:
        async with semaphore:
            result = await run_trial(
                task,
                trial,
                agent_llm=agent_llm,
                simulator_llm=simulator_llm,
                prompt_version=prompt_version,
                max_turns=max_turns,
            )
        if on_result:
            on_result(result)
        return result

    jobs = [
        one(task, trial)
        for trial in range(trials)
        for task in tasks
        if (task.id, trial) not in skip
    ]
    return list(await asyncio.gather(*jobs))
