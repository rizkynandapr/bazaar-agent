"""pass^k (τ-bench): the chance that ALL of k independent trials of a task succeed.

pass^1 is plain accuracy. pass^k drops when an agent is inconsistent, which is what a business
cares about: a bot that is right 80% of the time is wrong for 1 in 5 customers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import comb


def pass_hat_k(outcomes: Mapping[str, Sequence[bool]], k: int) -> float:
    """Unbiased estimator averaged over tasks: mean of C(c, k) / C(n, k)."""
    if not outcomes:
        return 0.0
    total = 0.0
    for task_id, trials in outcomes.items():
        n, c = len(trials), sum(trials)
        if n < k:
            raise ValueError(f"task {task_id} has {n} trials, need at least k={k}")
        total += comb(c, k) / comb(n, k)
    return total / len(outcomes)
