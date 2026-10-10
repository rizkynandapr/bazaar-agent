from __future__ import annotations

import json
from pathlib import Path

import pytest

from bazaar.bench import Task, extract_amounts, grade, pass_hat_k, run_trial
from bazaar.bench.report import summarize, write_run
from bazaar.bench.simulator import STOP_TOKEN
from bazaar.bench.task import ExpectedAction, UserSpec
from bazaar.llm import ToolCall
from bazaar.llm.fake import FakeLLM
from bazaar.store import Store
from bazaar.store.store import LineRequest

CANCEL_TASK = Task(
    id="T90",
    category="edge_case",
    title="cancel",
    user=UserSpec(persona="p", instruction="i"),
    expected_actions=[ExpectedAction(name="cancel_order", arguments={"order_id": "ORD-1003"})],
)


# ---------- amounts ----------


@pytest.mark.parametrize(
    ("text", "amount"),
    [
        ("Totalnya Rp259.000 ya kak", 259000),
        ("total Rp 259,000", 259000),
        ("jadi 259rb aja", 259000),
        ("259k kak", 259000),
        ("Rp259.000,00", 259000),
        ("ongkir 35000", 35000),
        ("1,5 jt", 1500000),
        ("2.25 juta", 2250000),
    ],
)
def test_extract_amounts(text: str, amount: int) -> None:
    assert amount in extract_amounts(text)


def test_extract_amounts_ignores_sizes_and_ids_as_noise() -> None:
    amounts = extract_amounts("Kemeja ukuran 30, pesanan ORD-1007")
    assert 30 in amounts  # harmless noise: graders look for specific large amounts
    assert 259000 not in amounts


# ---------- grading ----------


def test_grade_passes_when_state_matches() -> None:
    store = Store.from_seed()
    store.cancel_order("ORD-1003")
    assert grade(CANCEL_TASK, store.state, ["Sudah dibatalkan kak"]).passed


def test_grade_fails_with_readable_reason_when_state_differs() -> None:
    result = grade(CANCEL_TASK, Store.from_seed().state, ["Sudah dibatalkan kak"])
    assert not result.passed
    assert not result.checks["state"]
    assert any("ORD-1003" in r for r in result.reasons)


def test_grade_ignores_free_text_fields() -> None:
    task = Task(
        id="T91",
        category="happy_path",
        title="order",
        user=UserSpec(persona="p", instruction="i"),
        expected_actions=[
            ExpectedAction(
                name="create_order",
                arguments={
                    "customer_name": "Fajar Nugroho",
                    "customer_phone": "081300000001",
                    "city": "Yogyakarta",
                    "address": "Jl. Kaliurang Km 5 No. 12",
                    "items": [{"sku": "KLP-PTH-M", "qty": 1}],
                    "payment_method": "cod",
                },
            )
        ],
        required_amounts=[259000],
    )
    store = Store.from_seed()
    store.create_order(
        customer_name="fajar",
        customer_phone="+62 813 0000 0001",
        city="yogyakarta",
        address="jalan kaliurang km5 no 12",
        lines=[LineRequest("KLP-PTH-M", 1)],
        payment_method="cod",
    )
    assert grade(task, store.state, ["Total Rp259.000"]).passed
    assert not grade(task, store.state, ["Sudah dipesan"]).passed  # total never stated


def test_grade_forbidden_content() -> None:
    task = CANCEL_TASK.model_copy(
        update={
            "expected_actions": [],
            "forbidden_amounts": [259000],
            "forbidden_substrings": ["Gejayan"],
        }
    )
    result = grade(task, Store.from_seed().state, ["Alamatnya di Gejayan, totalnya 259rb"])
    assert not result.checks["forbidden_amounts"]
    assert not result.checks["forbidden_substrings"]


# ---------- pass^k ----------


def test_pass_hat_k() -> None:
    outcomes = {"a": [True, True, True], "b": [True, False, True], "c": [False, False, False]}
    assert pass_hat_k(outcomes, 1) == pytest.approx((1 + 2 / 3 + 0) / 3)
    assert pass_hat_k(outcomes, 3) == pytest.approx(1 / 3)
    with pytest.raises(ValueError):
        pass_hat_k(outcomes, 4)


# ---------- runner, end to end with scripted models ----------


async def test_run_trial_end_to_end_pass_and_report(tmp_path: Path) -> None:
    agent_llm = FakeLLM(
        [
            FakeLLM.calls(ToolCall(id="a1", name="get_order", arguments={"order_id": "ORD-1003"})),
            FakeLLM.says("Pesanan ORD-1003 masih diproses. Yakin mau dibatalkan kak?"),
            FakeLLM.calls(
                ToolCall(id="a2", name="cancel_order", arguments={"order_id": "ORD-1003"})
            ),
            FakeLLM.says("Sudah dibatalkan ya kak."),
        ]
    )
    simulator_llm = FakeLLM(
        [
            FakeLLM.says("kak mau batalin ORD-1003, hp 081234567803"),
            FakeLLM.says("iya yakin"),
            FakeLLM.says(STOP_TOKEN),
        ]
    )
    result = await run_trial(CANCEL_TASK, 0, agent_llm=agent_llm, simulator_llm=simulator_llm)

    assert result.passed, result.reasons
    assert result.ended_by == "customer_stop"
    assert result.turns == 2
    assert [e.role for e in result.transcript].count("tool") == 2

    summary = summarize(
        [result],
        {
            "run_id": "test",
            "agent_model": "fake",
            "simulator_model": "fake",
            "prompt_version": "baseline_v0",
        },
    )
    assert summary["pass_hat_k"]["pass^1"] == 1.0
    write_run(tmp_path, [result], summary)
    assert json.loads((tmp_path / "summary.json").read_text())["tasks"] == 1
    assert "pass^1" in (tmp_path / "summary.md").read_text()


async def test_run_trial_marks_infra_errors_as_failures() -> None:
    simulator_llm = FakeLLM([FakeLLM.says("halo kak")])
    agent_llm = FakeLLM([])  # exhausted script raises LLMError
    result = await run_trial(CANCEL_TASK, 0, agent_llm=agent_llm, simulator_llm=simulator_llm)
    assert not result.passed
    assert result.ended_by == "error"
    assert result.error


async def test_run_trial_stops_on_handover() -> None:
    task = CANCEL_TASK.model_copy(
        update={
            "expected_actions": [
                ExpectedAction(name="handover_to_human", arguments={"reason": "x", "summary": "y"})
            ]
        }
    )
    agent_llm = FakeLLM(
        [
            FakeLLM.calls(
                ToolCall(
                    id="h",
                    name="handover_to_human",
                    arguments={"reason": "minta admin", "summary": "minta admin"},
                )
            ),
            FakeLLM.says("Admin akan melanjutkan ya kak."),
        ]
    )
    simulator_llm = FakeLLM([FakeLLM.says("sambungin ke admin dong")])
    result = await run_trial(task, 0, agent_llm=agent_llm, simulator_llm=simulator_llm)
    assert result.ended_by == "handover"
    assert result.passed, result.reasons
