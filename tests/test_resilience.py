"""Long benchmark runs on free tiers must survive rate limits and interruptions."""

from __future__ import annotations

import json
import time
from pathlib import Path

from bazaar.bench import Task, run_benchmark
from bazaar.bench.cli import _load_previous
from bazaar.bench.runner import TrialResult
from bazaar.bench.simulator import STOP_TOKEN
from bazaar.bench.task import UserSpec
from bazaar.llm import Message, Usage
from bazaar.llm.fake import FakeLLM
from bazaar.llm.throttle import ThrottledClient

META = {
    "agent_model": "a",
    "simulator_model": "s",
    "prompt_version": "baseline_v0",
    "task_file": "benchmark/tasks/v0.yaml",
}


def make_task(task_id: str) -> Task:
    return Task(
        id=task_id, category="happy_path", title="t", user=UserSpec(persona="p", instruction="i")
    )


def make_result(task_id: str, trial: int, *, error: str | None = None) -> TrialResult:
    return TrialResult(
        task_id=task_id,
        category="happy_path",
        trial=trial,
        passed=error is None,
        ended_by="error" if error else "customer_stop",
        turns=1,
        agent_usage=Usage(),
        simulator_usage=Usage(),
        duration_s=0.1,
        error=error,
    )


async def test_throttle_spaces_requests() -> None:
    fake = FakeLLM([FakeLLM.says("a"), FakeLLM.says("b"), FakeLLM.says("c")])
    client = ThrottledClient(fake, rpm=600)  # one request every 0.1 s
    started = time.monotonic()
    for _ in range(3):
        await client.complete([Message.user("x")])
    assert time.monotonic() - started >= 0.19


async def test_run_benchmark_skips_completed_trials() -> None:
    tasks = [make_task("T01"), make_task("T02")]
    # Only T02 should run: the simulator stops immediately, so no agent call is needed.
    simulator = FakeLLM([FakeLLM.says(STOP_TOKEN)])
    results = await run_benchmark(
        tasks,
        trials=1,
        agent_llm=FakeLLM([]),
        simulator_llm=simulator,
        skip={("T01", 0)},
    )
    assert [r.task_id for r in results] == ["T02"]


def test_resume_keeps_good_trials_and_retries_errors(tmp_path: Path) -> None:
    (tmp_path / "run.json").write_text(json.dumps({"run_id": "r", **META}))
    lines = [make_result("T01", 0), make_result("T02", 0, error="RateLimitError from LLM provider")]
    (tmp_path / "trials.jsonl").write_text("".join(r.model_dump_json() + "\n" for r in lines))

    kept = _load_previous(tmp_path, META)

    assert kept is not None
    assert [(r.task_id, r.trial) for r in kept] == [("T01", 0)]


def test_resume_refuses_a_different_model(tmp_path: Path) -> None:
    (tmp_path / "run.json").write_text(json.dumps({"run_id": "r", **META}))
    assert _load_previous(tmp_path, {**META, "agent_model": "other"}) is None
