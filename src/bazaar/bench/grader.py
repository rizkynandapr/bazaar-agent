"""Deterministic grading: final store state vs expected state, plus checks on what was said.

No LLM is involved in grading, so a score never depends on a judge model's mood.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from bazaar.bench.task import Task
from bazaar.llm import ToolCall
from bazaar.store import Store, execute
from bazaar.store.models import StoreState


class InvalidTaskError(Exception):
    """A task's own answer key does not replay cleanly. The task is broken, not the agent."""


def expected_state(task: Task) -> StoreState:
    store = Store.from_seed()
    for index, action in enumerate(task.expected_actions):
        outcome = execute(
            store, ToolCall(id=f"expected-{index}", name=action.name, arguments=action.arguments)
        )
        if not outcome.ok:
            raise InvalidTaskError(f"{task.id}: expected action #{index} failed: {outcome.content}")
    return store.state


def canonical_state(state: StoreState) -> dict[str, Any]:
    """Drop free-text fields an agent may legitimately phrase differently."""
    data = state.model_dump(mode="json")
    for order in data["orders"].values():
        order.pop("address", None)
        order.pop("customer_name", None)
    data["handovers"] = len(data["handovers"])
    return data


def state_diff(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    diffs: list[str] = []
    if expected["handovers"] != actual["handovers"]:
        diffs.append(f"handovers: expected {expected['handovers']}, got {actual['handovers']}")
    exp_orders, act_orders = expected["orders"], actual["orders"]
    for oid in sorted(set(exp_orders) | set(act_orders)):
        if oid not in act_orders:
            diffs.append(f"order {oid}: missing")
        elif oid not in exp_orders:
            diffs.append(f"order {oid}: unexpected")
        elif exp_orders[oid] != act_orders[oid]:
            fields = sorted(
                k for k in exp_orders[oid] if exp_orders[oid].get(k) != act_orders[oid].get(k)
            )
            diffs.append(f"order {oid}: differs in {', '.join(fields)}")
    if expected["products"] != actual["products"]:
        diffs.append("product stock differs")
    return diffs


_AMOUNT = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:[.,]\d{3})+|\d+)(?:[.,]00)?\s*(rb|ribu|k|jt|juta)?(?![\w])",
    re.IGNORECASE,
)
_MULTIPLIER = {"rb": 1_000, "ribu": 1_000, "k": 1_000, "jt": 1_000_000, "juta": 1_000_000}
_DECIMAL_MILLION = re.compile(r"(?<![\d.,])(\d+)[.,](\d{1,2})\s*(?:jt|juta)(?!\w)", re.IGNORECASE)


def extract_amounts(text: str) -> set[int]:
    """'Rp259.000', 'Rp 259,000', '259rb', '259k' -> {259000}; '1,5 jt' -> {1500000}."""
    found: set[int] = set()

    def take_decimal_million(match: re.Match[str]) -> str:
        whole, fraction = match.group(1), match.group(2).ljust(2, "0")
        found.add(int(whole) * 1_000_000 + int(fraction) * 10_000)
        return " "

    text = _DECIMAL_MILLION.sub(take_decimal_million, text)
    for number, suffix in _AMOUNT.findall(text):
        value = int(re.sub(r"[.,]", "", number))
        if suffix:
            value *= _MULTIPLIER[suffix.lower()]
        found.add(value)
    return found


@dataclass
class Grade:
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


def grade(
    task: Task,
    final_state: StoreState,
    agent_messages: Iterable[str],
    tools_called: Iterable[str] = (),
) -> Grade:
    """``tools_called`` holds the names of tool calls that succeeded during the conversation."""
    said = "\n".join(agent_messages)
    amounts = extract_amounts(said)
    lowered = said.lower()
    result = Grade(passed=True)

    expected = canonical_state(expected_state(task))
    actual = canonical_state(final_state)
    diffs = state_diff(expected, actual)
    result.checks["state"] = not diffs
    result.reasons += diffs

    missing = [a for a in task.required_amounts if a not in amounts]
    result.checks["required_amounts"] = not missing
    result.reasons += [f"did not state amount {a}" for a in missing]

    leaked = [a for a in task.forbidden_amounts if a in amounts]
    result.checks["forbidden_amounts"] = not leaked
    result.reasons += [f"stated forbidden amount {a}" for a in leaked]

    absent = [s for s in task.required_substrings if s.lower() not in lowered]
    result.checks["required_substrings"] = not absent
    result.reasons += [f"did not mention '{s}'" for s in absent]

    present = [s for s in task.forbidden_substrings if s.lower() in lowered]
    result.checks["forbidden_substrings"] = not present
    result.reasons += [f"mentioned forbidden '{s}'" for s in present]

    called = set(tools_called)
    skipped = [t for t in task.required_tools if t not in called]
    result.checks["required_tools"] = not skipped
    result.reasons += [f"never called {t}" for t in skipped]

    result.passed = all(result.checks.values())
    return result
