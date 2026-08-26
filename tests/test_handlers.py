from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import bot_core.handlers as handlers
import bot_core.summarizer as summarizer
from bot_core.summarizer import SummaryError


class FakeProcessingMessage:
    def __init__(self):
        self.edit_text = AsyncMock()
        self.message_id = 999


def make_update(chat_id=-100123, chat_type="supergroup", args=None):
    processing_holder = {}

    def _side(text=None, **kwargs):
        proc = FakeProcessingMessage()
        processing_holder["proc"] = proc
        return proc

    message = SimpleNamespace(
        message_id=1,
        text="hello group",
        from_user=SimpleNamespace(id=42, full_name="Alice", username="alice", first_name="Alice"),
        chat=SimpleNamespace(id=chat_id, type=chat_type),
        # AsyncMock: awaiting reply_text(...) returns the FakeProcessingMessage
        reply_text=AsyncMock(side_effect=_side),
    )
    update = SimpleNamespace(message=message, effective_user=message.from_user, effective_chat=message.chat)
    context = SimpleNamespace(args=list(args) if args else [], bot=AsyncMock())
    return update, context, processing_holder


# ---------- _parse_count ----------

def test_parse_count_default():
    assert handlers._parse_count(None) == 25
    assert handlers._parse_count([]) == 25


def test_parse_count_valid():
    assert handlers._parse_count(["50"]) == 50


def test_parse_count_invalid_falls_back_to_default():
    assert handlers._parse_count(["abc"]) == 25


def test_parse_count_clamped():
    assert handlers._parse_count(["0"]) == 1
    assert handlers._parse_count(["999999"]) == 200


# ---------- handle_message ----------

async def test_handle_message_caches_dict(monkeypatch):
    recorded = {}
    monkeypatch.setattr(handlers.cache, "cache_message",
                        lambda chat_id, msg: recorded.update({"chat_id": chat_id, "msg": msg}))
    update, context, _ = make_update()
    await handlers.handle_message(update, context)
    assert recorded["chat_id"] == -100123
    msg = recorded["msg"]
    assert msg["text"] == "hello group"
    assert msg["user_name"] == "Alice"
    assert msg["username"] == "alice"


async def test_handle_message_cache_failure_is_silent(monkeypatch):
    def boom(chat_id, msg):
        raise RuntimeError("redis down")
    monkeypatch.setattr(handlers.cache, "cache_message", boom)
    update, context, _ = make_update()
    await handlers.handle_message(update, context)  # must not raise


# ---------- auto summary on message threshold ----------

def _patch_counter(monkeypatch, count):
    monkeypatch.setattr(handlers.cache, "incr_auto_summary_counter", lambda chat_id: count)
    reset = Mock()
    monkeypatch.setattr(handlers.cache, "reset_auto_summary_counter", reset)
    return reset


async def test_handle_message_spawns_auto_summary_at_threshold(monkeypatch):
    reset = _patch_counter(monkeypatch, count=100)
    spawn = Mock()
    monkeypatch.setattr(handlers, "_spawn_auto_summary", spawn)
    update, context, _ = make_update()
    await handlers.handle_message(update, context)
    reset.assert_called_once_with(-100123)
    spawn.assert_called_once_with(-100123, 100, context.bot)


async def test_handle_message_no_spawn_below_threshold(monkeypatch):
    reset = _patch_counter(monkeypatch, count=99)
    spawn = Mock()
    monkeypatch.setattr(handlers, "_spawn_auto_summary", spawn)
    update, context, _ = make_update()
    await handlers.handle_message(update, context)
    reset.assert_not_called()
    spawn.assert_not_called()


async def test_handle_message_no_spawn_when_disabled(monkeypatch):
    monkeypatch.setattr(handlers.config, "AUTO_SUMMARY_THRESHOLD", 0)
    reset = _patch_counter(monkeypatch, count=100)
    spawn = Mock()
    monkeypatch.setattr(handlers, "_spawn_auto_summary", spawn)
    update, context, _ = make_update()
    await handlers.handle_message(update, context)
    reset.assert_not_called()
    spawn.assert_not_called()


async def test_run_auto_summary_happy_path(monkeypatch):
    msgs = [{"message_id": i, "user_name": "A", "username": None, "text": f"m{i}", "ts": "t"}
            for i in range(1, 101)]
    monkeypatch.setattr(handlers.cache, "get_recent_messages", lambda chat_id, n: msgs)
    monkeypatch.setattr(summarizer, "generate_summary", AsyncMock(return_value="*Auto* summary"))
    release = _patch_slot(monkeypatch)
    sleep_mock = AsyncMock()
    monkeypatch.setattr(handlers.asyncio, "sleep", sleep_mock)
    bot = AsyncMock()
    sent = SimpleNamespace(message_id=555)
    bot.send_message = AsyncMock(return_value=sent)
    await handlers.run_auto_summary(-100123, 100, bot)
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == -100123
    assert kwargs["text"].startswith("🤖")
    assert "*Auto* summary" in kwargs["text"]
    assert "自動摘要" in kwargs["text"]
    assert "30 秒後自動刪除" in kwargs["text"]
    sleep_mock.assert_awaited_once_with(30)
    bot.delete_message.assert_awaited_once_with(chat_id=-100123, message_id=555)
    release.assert_not_called()  # success keeps cooldown


async def test_run_auto_summary_slot_blocked(monkeypatch):
    _patch_slot(monkeypatch, remaining=42)
    generate = AsyncMock()
    monkeypatch.setattr(summarizer, "generate_summary", generate)
    bot = AsyncMock()
    await handlers.run_auto_summary(-100123, 100, bot)
    generate.assert_not_awaited()
    bot.send_message.assert_not_awaited()


async def test_run_auto_summary_failure_releases_slot(monkeypatch):
    monkeypatch.setattr(handlers.cache, "get_recent_messages", lambda chat_id, n: [{"text": "x"}])
    monkeypatch.setattr(summarizer, "generate_summary",
                        AsyncMock(side_effect=SummaryError("⏱️ timed out")))
    release = _patch_slot(monkeypatch)
    bot = AsyncMock()
    await handlers.run_auto_summary(-100123, 100, bot)
    release.assert_called_once_with(-100123)
    bot.send_message.assert_not_awaited()


async def test_spawn_auto_summary_creates_background_task(monkeypatch):
    started = AsyncMock()
    monkeypatch.setattr(handlers, "run_auto_summary", started)
    captured = {}
    def fake_create_task(coro):
        captured["coro"] = coro
        return Mock()
    monkeypatch.setattr(handlers.asyncio, "create_task", fake_create_task)
    handlers._spawn_auto_summary(-100123, 100, "bot")
    started.assert_called_once_with(-100123, 100, "bot")
    captured["coro"].close()  # avoid un-awaited coroutine warning


# ---------- summarize_command ----------

def _patch_slot(monkeypatch, remaining=0):
    """Patch the cooldown slot: acquire succeeds by default; track release calls."""
    monkeypatch.setattr(handlers.cache, "try_acquire_summary_slot",
                        lambda chat_id, cooldown: remaining)
    release = Mock()
    monkeypatch.setattr(handlers.cache, "release_summary_slot", release)
    return release


async def test_summarize_happy_path(monkeypatch):
    msgs = [{"message_id": 1, "user_name": "A", "username": None, "text": "x", "ts": "t"}]
    monkeypatch.setattr(handlers.cache, "get_recent_messages", lambda chat_id, n: msgs)
    monkeypatch.setattr(summarizer, "generate_summary", AsyncMock(return_value="*Topic* summary"))
    release = _patch_slot(monkeypatch)
    sleep_mock = AsyncMock()
    monkeypatch.setattr(handlers.asyncio, "sleep", sleep_mock)
    update, context, holder = make_update(args=["10"])
    await handlers.summarize_command(update, context)
    holder["proc"].edit_text.assert_awaited_once()
    expected = "*Topic* summary\n\n⏳ 此總結將在 30 秒後自動刪除。"
    assert holder["proc"].edit_text.await_args.kwargs["text"] == expected
    sleep_mock.assert_awaited_once_with(30)
    context.bot.delete_message.assert_awaited_once_with(chat_id=-100123, message_id=999)
    release.assert_not_called()  # success keeps the cooldown


async def test_summarize_cooldown_active_blocks_request(monkeypatch):
    acquire = Mock(return_value=42)
    monkeypatch.setattr(handlers.cache, "try_acquire_summary_slot", acquire)
    generate = AsyncMock()
    monkeypatch.setattr(summarizer, "generate_summary", generate)
    update, context, holder = make_update(args=["10"])
    await handlers.summarize_command(update, context)
    acquire.assert_called_once_with(-100123, handlers.config.SUMMARIZE_COOLDOWN_SECONDS)
    reply_text = update.message.reply_text
    reply_text.assert_awaited_once()
    assert "42" in reply_text.await_args.args[0]
    generate.assert_not_awaited()
    context.bot.delete_message.assert_not_awaited()


async def test_summarize_delete_failure_is_silent(monkeypatch):
    msgs = [{"message_id": 1, "user_name": "A", "username": None, "text": "x", "ts": "t"}]
    monkeypatch.setattr(handlers.cache, "get_recent_messages", lambda chat_id, n: msgs)
    monkeypatch.setattr(summarizer, "generate_summary", AsyncMock(return_value="s"))
    release = _patch_slot(monkeypatch)
    monkeypatch.setattr(handlers.asyncio, "sleep", AsyncMock())
    update, context, holder = make_update(args=["10"])
    context.bot.delete_message.side_effect = RuntimeError("already gone")
    await handlers.summarize_command(update, context)  # must not raise
    release.assert_not_called()  # delivery succeeded; cooldown stands


async def test_summarize_error_path_no_autodelete(monkeypatch):
    monkeypatch.setattr(handlers.cache, "get_recent_messages", lambda chat_id, n: [{"text": "x"}])
    monkeypatch.setattr(summarizer, "generate_summary",
                        AsyncMock(side_effect=SummaryError("⏱️ timed out")))
    release = _patch_slot(monkeypatch)
    sleep_mock = AsyncMock()
    monkeypatch.setattr(handlers.asyncio, "sleep", sleep_mock)
    update, context, holder = make_update(args=["5"])
    await handlers.summarize_command(update, context)
    assert "timed out" in holder["proc"].edit_text.await_args.kwargs["text"]
    assert "自動刪除" not in holder["proc"].edit_text.await_args.kwargs["text"]
    sleep_mock.assert_not_awaited()
    context.bot.delete_message.assert_not_awaited()
    release.assert_called_once_with(-100123)  # failure frees the slot for retry


async def test_summarize_empty_cache(monkeypatch):
    monkeypatch.setattr(handlers.cache, "get_recent_messages", lambda chat_id, n: [])
    release = _patch_slot(monkeypatch)
    sleep_mock = AsyncMock()
    monkeypatch.setattr(handlers.asyncio, "sleep", sleep_mock)
    update, context, holder = make_update(args=[])
    await handlers.summarize_command(update, context)
    assert "cached" in holder["proc"].edit_text.await_args.kwargs["text"].lower()
    sleep_mock.assert_not_awaited()
    release.assert_called_once_with(-100123)  # nothing consumed; free the slot


async def test_summarize_summary_error_shown_to_user(monkeypatch):
    monkeypatch.setattr(handlers.cache, "get_recent_messages", lambda chat_id, n: [{"text": "x"}])
    monkeypatch.setattr(summarizer, "generate_summary",
                        AsyncMock(side_effect=SummaryError("⏱️ timed out")))
    _patch_slot(monkeypatch)
    update, context, holder = make_update(args=["5"])
    await handlers.summarize_command(update, context)
    assert "timed out" in holder["proc"].edit_text.await_args.kwargs["text"]


async def test_summarize_ignores_private_chats(monkeypatch):
    called = Mock()
    monkeypatch.setattr(handlers.cache, "get_recent_messages", called)
    update, context, holder = make_update(chat_type="private")
    await handlers.summarize_command(update, context)
    called.assert_not_called()
    assert "proc" not in holder


async def test_error_handler_logs_without_raising():
    context = SimpleNamespace(error=RuntimeError("boom"))
    await handlers.error_handler("update-obj", context)  # must not raise
