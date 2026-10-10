from __future__ import annotations

from bazaar.agent import Agent
from bazaar.agent.loop import STEP_LIMIT_REPLY
from bazaar.llm import Role, ToolCall
from bazaar.llm.fake import FakeLLM
from bazaar.store import Store


async def test_tool_call_then_answer() -> None:
    llm = FakeLLM(
        [
            FakeLLM.calls(ToolCall(id="c1", name="get_product", arguments={"product_id": "P02"})),
            FakeLLM.says("Ready kak, harganya Rp129.000."),
        ]
    )
    agent = Agent(llm, Store.from_seed())

    turn = await agent.respond("kaos oversize ready?")

    assert turn.reply == "Ready kak, harganya Rp129.000."
    assert [c.name for c in turn.tool_calls] == ["get_product"]
    assert turn.tool_calls[0].ok
    # The tool result was fed back to the model on the second request.
    second_request_messages = llm.requests[1][0]
    assert second_request_messages[-1].role is Role.TOOL
    assert '"P02"' in (second_request_messages[-1].content or "")


async def test_tool_errors_are_fed_back_not_raised() -> None:
    llm = FakeLLM(
        [
            FakeLLM.calls(ToolCall(id="c1", name="get_order", arguments={"order_id": "ORD-9"})),
            FakeLLM.says("Maaf kak, pesanannya tidak ditemukan."),
        ]
    )
    turn = await Agent(llm, Store.from_seed()).respond("cek ORD-9")
    assert not turn.tool_calls[0].ok
    assert "not found" in turn.tool_calls[0].output


async def test_handover_marks_conversation_ended() -> None:
    llm = FakeLLM(
        [
            FakeLLM.calls(
                ToolCall(
                    id="c1",
                    name="handover_to_human",
                    arguments={"reason": "minta admin", "summary": "Pelanggan minta admin."},
                )
            ),
            FakeLLM.says("Baik kak, admin kami akan melanjutkan."),
        ]
    )
    store = Store.from_seed()
    agent = Agent(llm, store)
    turn = await agent.respond("mau ngomong sama admin")
    assert turn.handed_over
    assert len(store.state.handovers) == 1


async def test_step_limit_stops_runaway_tool_loops() -> None:
    looping = [
        FakeLLM.calls(ToolCall(id=f"c{i}", name="search_products", arguments={"query": "kaos"}))
        for i in range(3)
    ]
    turn = await Agent(FakeLLM(looping), Store.from_seed(), max_steps=3).respond("kaos")
    assert turn.hit_step_limit
    assert turn.reply == STEP_LIMIT_REPLY


def test_system_prompt_contains_policy_and_date() -> None:
    agent = Agent(FakeLLM([]), Store.from_seed())
    system = agent.messages[0].content or ""
    assert "Senja Wear" in system
    assert "2026-10-12" in system
    assert "FINAL SALE" in system
