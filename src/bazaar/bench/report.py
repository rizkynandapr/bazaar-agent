"""Turns trial results into summary.json, summary.md and trials.jsonl."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from bazaar.bench.metrics import pass_hat_k
from bazaar.bench.runner import TrialResult


def summarize(results: Sequence[TrialResult], meta: dict[str, Any]) -> dict[str, Any]:
    by_task: dict[str, list[bool]] = defaultdict(list)
    by_category: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        by_task[r.task_id].append(r.passed)
        by_category[r.category].append(r.passed)

    trials = min((len(v) for v in by_task.values()), default=0)
    failures = [
        {"task_id": r.task_id, "trial": r.trial, "ended_by": r.ended_by, "reasons": r.reasons}
        for r in results
        if not r.passed
    ]
    agent_in = sum(r.agent_usage.input_tokens for r in results)
    agent_out = sum(r.agent_usage.output_tokens for r in results)

    return {
        **meta,
        "tasks": len(by_task),
        "trials_per_task": trials,
        "pass_hat_k": {f"pass^{k}": round(pass_hat_k(by_task, k), 4) for k in range(1, trials + 1)},
        "by_category": {
            cat: {"pass_rate": round(sum(v) / len(v), 4), "n": len(v)}
            for cat, v in sorted(by_category.items())
        },
        "ended_by": dict(Counter(r.ended_by for r in results)),
        "infrastructure_errors": sum(1 for r in results if r.error),
        "mean_turns": round(sum(r.turns for r in results) / max(len(results), 1), 2),
        "agent_tokens": {"input": agent_in, "output": agent_out},
        "agent_tokens_per_conversation": round((agent_in + agent_out) / max(len(results), 1)),
        "failures": failures,
    }


def to_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# BazaarBench run `{summary['run_id']}`",
        "",
        f"- Agent model: `{summary['agent_model']}`",
        f"- Simulator model: `{summary['simulator_model']}`",
        f"- Prompt: `{summary['prompt_version']}`",
        f"- Tasks: {summary['tasks']} x {summary['trials_per_task']} trial(s)",
        f"- Infrastructure errors: {summary['infrastructure_errors']}",
        f"- Agent tokens per conversation: {summary['agent_tokens_per_conversation']}",
        "",
        "| Metric | Score |",
        "|---|---|",
    ]
    lines += [f"| {k} | {v:.1%} |" for k, v in summary["pass_hat_k"].items()]
    lines += ["", "| Category | Pass rate | Trials |", "|---|---|---|"]
    lines += [
        f"| {cat} | {v['pass_rate']:.1%} | {v['n']} |" for cat, v in summary["by_category"].items()
    ]
    if summary["failures"]:
        lines += ["", "## Failures", ""]
        for f in summary["failures"]:
            lines.append(
                f"- **{f['task_id']}** (trial {f['trial']}, {f['ended_by']}): "
                + "; ".join(f["reasons"])
            )
    return "\n".join(lines) + "\n"


def write_run(out_dir: Path, results: Sequence[TrialResult], summary: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "trials.jsonl").open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(r.model_dump_json() + "\n")
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "summary.md").write_text(to_markdown(summary), encoding="utf-8")
