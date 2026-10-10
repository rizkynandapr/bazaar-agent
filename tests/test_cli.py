from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx2 as httpx
import openai
import pytest

from bazaar.bench.cli import main
from bazaar.bench.doctor import config_problems, hint_for
from bazaar.config import LLMSettings, get_llm_settings
from bazaar.llm import LLMError

REPO = Path(__file__).parent.parent


@pytest.fixture
def empty_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """No .env file and no BAZAAR_* variables, like a fresh clone."""
    for key in ("BAZAAR_LLM_MODEL", "BAZAAR_LLM_API_KEY", "BAZAAR_LLM_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    get_llm_settings.cache_clear()
    yield tmp_path
    get_llm_settings.cache_clear()


def test_run_without_config_prints_help_instead_of_traceback(
    empty_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["run", "--tasks", str(REPO / "benchmark/tasks/v0.yaml"), "--ids", "T01"])
    out = capsys.readouterr().out
    assert code == 2
    assert "BAZAAR_LLM_MODEL is empty" in out
    assert "copy .env.example .env" in out
    assert "notepad .env" in out


def test_ping_without_config_prints_help(
    empty_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["ping"]) == 2
    assert "BAZAAR_LLM_MODEL is empty" in capsys.readouterr().out


def test_validate_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", "--tasks", str(REPO / "benchmark/tasks/v0.yaml")]) == 0
    assert "20/20" in capsys.readouterr().out


def test_config_problems() -> None:
    assert config_problems(LLMSettings(model="", _env_file=None)) == ["BAZAAR_LLM_MODEL is empty"]
    assert config_problems(LLMSettings(model="m", _env_file=None)) == []


def test_hints_name_the_likely_fix() -> None:
    def wrapped(cause: Exception) -> LLMError:
        err = LLMError("x")
        err.__cause__ = cause
        return err

    request = httpx.Request("POST", "http://localhost/v1/chat/completions")
    assert "running" in hint_for(wrapped(openai.APIConnectionError(request=request)))
    assert "Unexpected" in hint_for(wrapped(RuntimeError()))
