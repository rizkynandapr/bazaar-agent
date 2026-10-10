"""BazaarBench task schema and loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

Category = Literal[
    "happy_path",
    "edge_case",
    "policy_refusal",
    "handover",
    "adversarial",
    "language",
]


class UserSpec(BaseModel):
    """What the simulated customer knows and wants. Written in Indonesian, like real customers."""

    persona: str
    instruction: str


class ExpectedAction(BaseModel):
    """A write the correct agent performs. Replayed on a fresh store to build the expected state."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Task(BaseModel):
    id: str = Field(pattern=r"^T\d{2,3}$")
    category: Category
    title: str
    user: UserSpec
    expected_actions: list[ExpectedAction] = Field(default_factory=list)
    required_amounts: list[int] = Field(default_factory=list)
    forbidden_amounts: list[int] = Field(default_factory=list)
    required_substrings: list[str] = Field(default_factory=list)
    forbidden_substrings: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(
        default_factory=list,
        description="Tools the agent must call successfully, e.g. get_order before refusing. "
        "Stops an agent that refuses everything without looking from passing refusal tasks.",
    )
    notes: str = ""


def load_tasks(path: Path) -> list[Task]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    tasks = [Task.model_validate(item) for item in raw["tasks"]]
    ids = [t.id for t in tasks]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"Duplicate task ids: {sorted(duplicates)}")
    return tasks
