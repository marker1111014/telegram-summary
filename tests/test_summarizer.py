from types import SimpleNamespace

import pytest

import bot_core.config as config_module
import bot_core.summarizer as summarizer
from bot_core.summarizer import SummaryError


class FakeResponse:
    def __init__(self, text):
        self.text = text
        self.candidates = [object()]


@pytest.fixture
def patch_generate(monkeypatch):
    def _patch(fn):
        monkeypatch.setattr(summarizer._model, "generate_content", fn)
    return _patch


@pytest.mark.asyncio
async def test_generate_summary_happy_path(patch_generate):
    patch_generate(lambda prompt, generation_config=None: FakeResponse("*Summary* here"))
    msgs = [{"message_id": 1, "user_name": "Alice", "username": "alice",
             "text": "hello world", "ts": "2026-01-01T00:00:00Z"}]
    assert await summarizer.generate_summary(msgs) == "*Summary* here"


@pytest.mark.asyncio
async def test_generate_summary_blocked_when_no_candidates(patch_generate, monkeypatch):
    blocked = SimpleNamespace(candidates=[], prompt_feedback=SimpleNamespace(block_reason="SAFETY"))
    patch_generate(lambda prompt, generation_config=None: blocked)
    with pytest.raises(SummaryError, match="blocked"):
        await summarizer.generate_summary([])


@pytest.mark.asyncio
async def test_generate_summary_safety_finish_reason(patch_generate):
    resp = FakeResponse("")
    resp.candidates = [SimpleNamespace(finish_reason="SAFETY")]
    patch_generate(lambda prompt, generation_config=None: resp)
    with pytest.raises(SummaryError, match="[Ss]afety"):
        await summarizer.generate_summary([])


@pytest.mark.asyncio
async def test_generate_summary_timeout(patch_generate, monkeypatch):
    monkeypatch.setattr(config_module, "API_TIMEOUT_SECONDS", 0.05)

    def slow(prompt, generation_config=None):
        import time
        time.sleep(1)
        return FakeResponse("late")

    patch_generate(slow)
    with pytest.raises(SummaryError, match="timed out"):
        await summarizer.generate_summary([])


@pytest.mark.asyncio
async def test_generate_summary_api_error(patch_generate):
    import google.api_core.exceptions

    def boom(prompt, generation_config=None):
        raise google.api_core.exceptions.InternalServerError("down")

    patch_generate(boom)
    with pytest.raises(SummaryError, match="error"):
        await summarizer.generate_summary([])


def test_format_messages_with_username():
    msgs = [{"message_id": 1, "user_name": "Alice", "username": "alice",
             "text": "hi", "ts": "2026-01-01T00:00:00Z"}]
    out = summarizer.format_messages_for_prompt(msgs)
    assert out == "[2026-01-01T00:00:00Z - @alice (Alice)]: hi"


def test_format_messages_without_username():
    msgs = [{"message_id": 2, "user_name": "Bob", "username": None,
             "text": "yo", "ts": "2026-01-02T03:04:05Z"}]
    out = summarizer.format_messages_for_prompt(msgs)
    assert out == "[2026-01-02T03:04:05Z - Bob]: yo"
