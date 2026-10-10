"""Command line: ``python -m bazaar.bench {validate,ping,run}``."""

from __future__ import annotations

import argparse
import asyncio
import json
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
from bazaar.llm import LLMClient
from bazaar.llm.openai_compat import OpenAICompatClient
from bazaar.llm.throttle import ThrottledClient

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


def _client(settings: LLMSettings, rpm: float | None) -> LLMClient:
    client: LLMClient = OpenAICompatClient(settings)
    return ThrottledClient(client, rpm) if rpm else client


def _load_previous(out_dir: Path, meta: dict[str, str]) -> list[TrialResult] | None:
    """Completed trials of a run being resumed, or None if it belongs to another setup."""
    saved = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    for key in ("agent_model", "simulator_model", "prompt_version", "task_file"):
        if saved.get(key) != meta[key]:
            print(f"Cannot resume: {key} was {saved.get(key)!r}, now {meta[key]!r}.")
            return None
    trials_file = out_dir / "trials.jsonl"
    if not trials_file.exists():
        return []
    lines = trials_file.read_text(encoding="utf-8").splitlines()
    results = [TrialResult.model_validate_json(line) for line in lines if line.strip()]
    return [r for r in results if r.error is None]  # infrastructure errors are retried


def cmd_run(args: argparse.Namespace) -> int:
    tasks = _select(load_tasks(args.tasks), args.ids)
    loaded = _load_settings()
    if loaded is None:
        return 2
    agent_settings, sim_settings = loaded
    meta = {
        "agent_model": agent_settings.model,
        "simulator_model": sim_settings.model,
        "prompt_version": args.prompt,
        "task_file": str(args.tasks),
    }

    previous: list[TrialResult] = []
    if args.resume:
        out_dir = args.resume
        if not (out_dir / "run.json").exists():
            print(f"Nothing to resume in {out_dir} (no run.json).")
            return 2
        found = _load_previous(out_dir, meta)
        if found is None:
            return 2
        previous = found
        run_id = out_dir.name
        print(f"Resuming {run_id}: {len(previous)} trial(s) already done.")
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", agent_settings.model).strip("-").lower()
        run_id = f"{stamp}-{slug}"
        out_dir = args.out / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "run.json").write_text(json.dumps({"run_id": run_id, **meta}, indent=2))

    trials_file = out_dir / "trials.jsonl"
    # Rewrite with only the kept trials, then append each new trial the moment it finishes,
    # so an interrupted run (rate limit, closed laptop, Ctrl+C) loses at most one conversation.
    trials_file.write_text("".join(r.model_dump_json() + "\n" for r in previous), encoding="utf-8")

    def record(r: TrialResult) -> None:
        with trials_file.open("a", encoding="utf-8") as fh:
            fh.write(r.model_dump_json() + "\n")
        mark = "PASS" if r.passed else "FAIL"
        print(f"[{mark}] {r.task_id} trial {r.trial} ({r.ended_by}, {r.turns} turns)", flush=True)

    try:
        new_results = asyncio.run(
            run_benchmark(
                tasks,
                trials=args.trials,
                agent_llm=_client(agent_settings, args.rpm),
                simulator_llm=_client(sim_settings, args.sim_rpm or args.rpm),
                prompt_version=args.prompt,
                max_turns=args.max_turns,
                concurrency=args.concurrency,
                on_result=record,
                skip={(r.task_id, r.trial) for r in previous},
            )
        )
    except KeyboardInterrupt:
        print(f"\nStopped. Finished trials are saved. Continue with:  --resume {out_dir}")
        return 130

    results = previous + new_results
    wanted = {t.id for t in tasks}
    summary = summarize([r for r in results if r.task_id in wanted], {"run_id": run_id, **meta})
    write_run(out_dir, results, summary)
    print()
    print(to_markdown(summary))
    print(f"Saved to {out_dir}")
    errors = summary["infrastructure_errors"]
    if errors:
        print(f"{errors} trial(s) hit provider errors. Retry just those with:  --resume {out_dir}")
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
    run.add_argument(
        "--rpm", type=float, help="max requests per minute per model (respect free-tier limits)"
    )
    run.add_argument("--sim-rpm", type=float, help="separate request limit for the simulator")
    run.add_argument("--resume", type=Path, help="continue an interrupted run: runs/<run-id>")
    run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    code: int = args.func(args)
    return code


if __name__ == "__main__":
    sys.exit(main())
