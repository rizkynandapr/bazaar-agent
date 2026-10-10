"""Quality gate for the benchmark itself: a broken answer key is a bug, not a hard task."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from bazaar.bench import Task, expected_state, load_tasks
from bazaar.store import TOOLS, Store

TASK_FILE = Path(__file__).parent.parent / "benchmark" / "tasks" / "v0.yaml"
TASKS = load_tasks(TASK_FILE)


def test_task_set_shape() -> None:
    assert len(TASKS) == 20
    counts = Counter(t.category for t in TASKS)
    assert set(counts) == {
        "happy_path",
        "edge_case",
        "policy_refusal",
        "handover",
        "adversarial",
        "language",
    }


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t.id)
def test_answer_key_replays_cleanly(task: Task) -> None:
    for action in task.expected_actions:
        assert action.name in TOOLS
        assert TOOLS[action.name].writes, f"{task.id}: expected actions must be writes"
    expected_state(task)  # raises InvalidTaskError on a broken key


@pytest.mark.parametrize(
    "task",
    [t for t in TASKS if any(a.name == "create_order" for a in t.expected_actions)],
    ids=lambda t: t.id,
)
def test_new_order_total_is_required_to_be_stated(task: Task) -> None:
    """Policy says the agent must tell the customer the total; the key must check for it."""
    seed_orders = set(Store.from_seed().state.orders)
    new_orders = [o for oid, o in expected_state(task).orders.items() if oid not in seed_orders]
    assert len(new_orders) == 1
    assert new_orders[0].total in task.required_amounts


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t.id)
def test_required_and_forbidden_do_not_overlap(task: Task) -> None:
    assert not set(task.required_amounts) & set(task.forbidden_amounts)
    lowered = {s.lower() for s in task.required_substrings}
    assert not lowered & {s.lower() for s in task.forbidden_substrings}
