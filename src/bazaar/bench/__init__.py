"""BazaarBench: τ-bench-style evaluation for Indonesian commerce customer-service agents."""

from bazaar.bench.grader import Grade, InvalidTaskError, expected_state, extract_amounts, grade
from bazaar.bench.metrics import pass_hat_k
from bazaar.bench.runner import TrialResult, run_benchmark, run_trial
from bazaar.bench.task import Task, load_tasks

__all__ = [
    "Grade",
    "InvalidTaskError",
    "Task",
    "TrialResult",
    "expected_state",
    "extract_amounts",
    "grade",
    "load_tasks",
    "pass_hat_k",
    "run_benchmark",
    "run_trial",
]
