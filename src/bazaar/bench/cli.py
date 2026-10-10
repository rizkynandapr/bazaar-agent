"""Command line: ``python -m bazaar.bench {validate,ping,run}``."""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from bazaar.bench.doctor import ENV_HELP, config_problems, ping
from bazaar.bench.grader import InvalidTaskError, expected_state
from bazaar.bench.report import summarize, to_markdown, write_run
from bazaar.bench.runner import TrialResult, run_benchmark
from bazaar.bench.task import Task, load_tasks
from bazaar.config import LLMSettings, SimulatorOverrides, get_llm_settings, simulator_settings
from bazaar.llm.openai_compat import OpenAICompatClient

DEFAULT_TASKS = Path("benchmark/tasks/v0.yaml")


def _select(tasks: list[Task], ids: str | None) -> list[Task]:
    if not ids:
        return tasks
    wanted = {i.strip() for i in ids.split(",")}
    unknown = wanted - {t.id for t in tasks}
    if unknown:
        raise SystemExit(f"Unknown task ids: {sorted(unknown)}")
    return [t for t in tasks if t.id in wanted]


def cmd_validate(args: argparse.Namespace) -> int:
    tasks = load_tasks(args.tasks)
    broken = 0
    for task in tasks:
        try:
            expected_state(task)
        except InvalidTaskError as exc:
            broken += 1
            print(f"[BROKEN] {exc}")
    print(f"{len(tasks) - broken}/{len(tasks)} tasks replay cleanly")
    return 1 if broken else 0


def _load_settings() -> tuple[LLMSettings, LLMSettings] | None:
    """Agent and simulator settings, or None after printing how to fix the .env file."""
    agent_settings = get_llm_settings()
    problems = config_problems(agent_settings)
    if problems:
        print("Setup is incomplete: " + "; ".join(problems) + ".\n")
        if not Path(".env").exists():
            print("No .env file in this folder. Create one:  copy .env.example .env\n")
        print(ENV_HELP)
        return None
    return agent_settings, simulator_settings(agent_settings, SimulatorOverrides())


def cmd_ping(args: argparse.Namespace) -> int:
    loaded = _load_settings()
    if loaded is None:
        return 2
    failures = 0
    for role, settings in zip(("agent", "simulator"), loaded, strict=True):
        ok, detail = asyncio.run(ping(settings))
        failures += not ok
        print(
            f"[{'OK' if ok else 'FAIL'}] {role:<9} {settings.model} @ {settings.base_url}: {detail}"
        )
    return 1 if failures else 0


def cmd_run(args: argparse.Namespace) -> int:
    tasks = _select(load_tasks(args.tasks), args.ids)
    loaded = _load_settings()
    if loaded is None:
        return 2
    agent_settings, sim_settings = loaded
    agent_llm = OpenAICompatClient(agent_settings)
    sim_llm = OpenAICompatClient(sim_settings)

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", agent_settings.model).strip("-").lower()
    run_id = f"{stamp}-{slug}"

    def progress(r: TrialResult) -> None:
        mark = "PASS" if r.passed else "FAIL"
        print(f"[{mark}] {r.task_id} trial {r.trial} ({r.ended_by}, {r.turns} turns)", flush=True)

    results = asyncio.run(
        run_benchmark(
            tasks,
            trials=args.trials,
            agent_llm=agent_llm,
            simulator_llm=sim_llm,
            prompt_version=args.prompt,
            max_turns=args.max_turns,
            concurrency=args.concurrency,
            on_result=progress,
        )
    )
    summary = summarize(
        results,
        {
            "run_id": run_id,
            "agent_model": agent_settings.model,
            "simulator_model": sim_settings.model,
            "prompt_version": args.prompt,
            "task_file": str(args.tasks),
        },
    )
    out_dir = args.out / run_id
    write_run(out_dir, results, summary)
    print()
    print(to_markdown(summary))
    print(f"Saved to {out_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bazaar.bench")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="replay every task's answer key (no LLM calls)")
    validate.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    validate.set_defaults(func=cmd_validate)

    ping_cmd = sub.add_parser("ping", help="check that the agent and simulator models answer")
    ping_cmd.set_defaults(func=cmd_ping)

    run = sub.add_parser("run", help="run the benchmark against the configured models")
    run.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    run.add_argument("--ids", help="comma-separated task ids, e.g. T01,T05")
    run.add_argument("--trials", type=int, default=1)
    run.add_argument("--concurrency", type=int, default=1)
    run.add_argument("--max-turns", type=int, default=15)
    run.add_argument("--prompt", default="baseline_v0")
    run.add_argument("--out", type=Path, default=Path("runs"))
    run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    code: int = args.func(args)
    return code


if __name__ == "__main__":
    sys.exit(main())
