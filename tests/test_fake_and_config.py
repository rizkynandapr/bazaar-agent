from __future__ import annotations

import pytest

from bazaar.config import LLMSettings
from bazaar.llm import LLMClient, LLMError, Message, ToolCall, Usage
from bazaar.llm.fake import FakeLLM


async def test_fake_llm_replays_script_and_records_requests() -> None:
    fake = FakeLLM(
        [
            FakeLLM.calls(ToolCall(id="c1", name="cek_stok", arguments={"sku": "A"})),
            FakeLLM.says("Stoknya ada 3, kak."),
        ]
    )
    assert isinstance(fake, LLMClient)

    first = await fake.complete([Message.user("ready?")])
    second = await fake.complete([Message.user("ready?")])

    assert first.message.tool_calls[0].name == "cek_stok"
    assert second.message.content == "Stoknya ada 3, kak."
    assert len(fake.requests) == 2
    with pytest.raises(LLMError):
        await fake.complete([Message.user("lagi")])


def test_usage_adds_up() -> None:
    assert Usage(input_tokens=1, output_tokens=2) + Usage(input_tokens=3, output_tokens=4) == Usage(
        input_tokens=4, output_tokens=6
    )


def test_settings_read_env_and_hide_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BAZAAR_LLM_MODEL", "some/model:free")
    monkeypatch.setenv("BAZAAR_LLM_API_KEY", "sk-very-secret")
    settings = LLMSettings(_env_file=None)

    assert settings.model == "some/model:free"
    assert settings.api_key.get_secret_value() == "sk-very-secret"
    assert "sk-very-secret" not in repr(settings)


def test_settings_reject_absurd_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BAZAAR_LLM_TIMEOUT_S", "0")
    with pytest.raises(ValueError):
        LLMSettings(_env_file=None)
