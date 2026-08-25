# Telegram 摘要機器人 Vercel 部署版 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將 polling 型 Telegram 群組摘要機器人改造成可部署到 Vercel 的純 webhook 版本(Upstash Redis 快取 + Gemini 摘要)。

**Architecture:** FastAPI 作為 Vercel serverless 進入點,驗證 Telegram secret token 後交給 PTB `Application.process_update()`。訊息快取存 Upstash Redis(HTTP client)。Gemini 呼叫包在 `asyncio.to_thread` + timeout。規格見 `docs/superpowers/specs/2026-08-26-vercel-deployment-design.md`。

**Tech Stack:** Python 3.11+、python-telegram-bot 21.2、FastAPI、upstash-redis、google-generativeai 0.8.5、pytest

**執行環境注意事項:** Windows PowerShell。所有命令用 `python -m pytest`;相依套件用 `pip install`。

---

### Task 1: 專案鷹架(requirements、vercel.json、.env.example、移除 bot.py)

**Files:**
- Modify: `requirements.txt`(整檔覆寫)
- Create: `requirements-dev.txt`
- Create: `vercel.json`
- Create: `.env.example`
- Delete: `bot.py`
- Create: `.gitignore`

- [ ] **Step 1: 覆寫 `requirements.txt`**

```
# Runtime dependencies
python-telegram-bot==21.2
google-generativeai==0.8.5
python-dotenv==1.0.1
upstash-redis==1.4.0
fastapi==0.115.6
```

- [ ] **Step 2: 建立 `requirements-dev.txt`**

```
pytest==8.3.4
pytest-asyncio==0.25.0
```

- [ ] **Step 3: 建立 `vercel.json`**

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "functions": {
    "api/webhook.py": { "maxDuration": 60 }
  }
}
```

- [ ] **Step 4: 建立 `.env.example`**

```
TELEGRAM_BOT_TOKEN=
GEMINI_API_KEY=
UPSTASH_REDIS_REST_URL=
UPSTASH_REDIS_REST_TOKEN=
WEBHOOK_SECRET=

# Optional
# GEMINI_MODEL_NAME=gemini-2.0-flash
# API_TIMEOUT_SECONDS=30
```

- [ ] **Step 5: 建立 `.gitignore`**

```
.env
__pycache__/
*.pyc
.vercel
.pytest_cache/
venv/
```

- [ ] **Step 6: 刪除舊的 `bot.py`**

Run: `git rm bot.py`
Expected: `rm 'bot.py'`

- [ ] **Step 7: 安裝依賴**

Run: `pip install -r requirements.txt -r requirements-dev.txt`
Expected: 安裝成功無錯誤

- [ ] **Step 8: Commit**

```bash
git add requirements.txt requirements-dev.txt vercel.json .env.example .gitignore
git commit -m "chore: scaffold Vercel serverless project structure"
```

---

### Task 2: bot_core/config.py(環境變數設定)

**Files:**
- Create: `bot_core/__init__.py`(空檔案)
- Create: `bot_core/config.py`
- Create: `tests/conftest.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: 建立 `tests/conftest.py`(在 import 任何 bot_core 模組前注入測試用環境變數)**

```python
import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456789:AaBbCcDdEeFfGgHhIiJjKkLmMmNnOoPpQq")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("UPSTASH_REDIS_REST_URL", "https://example.upstash.io")
os.environ.setdefault("UPSTASH_REDIS_REST_TOKEN", "test-upstash-token")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")
```

- [ ] **Step 2: 建立 `bot_core/__init__.py`(空檔案)**

- [ ] **Step 3: 寫失敗測試 `tests/test_config.py`**

```python
from bot_core import config


def test_required_values_loaded_from_env():
    assert config.TELEGRAM_BOT_TOKEN.startswith("123456789:")
    assert config.GEMINI_API_KEY == "test-gemini-key"
    assert config.UPSTASH_REDIS_REST_URL == "https://example.upstash.io"
    assert config.WEBHOOK_SECRET == "test-webhook-secret"


def test_defaults():
    assert config.GEMINI_MODEL_NAME == "gemini-2.0-flash"
    assert config.API_TIMEOUT_SECONDS == 30
    assert config.MESSAGE_CACHE_SIZE == 500
    assert config.DEFAULT_SUMMARY_MESSAGES == 25
    assert config.MAX_SUMMARY_MESSAGES == 200
    assert config.CACHE_TTL_SECONDS == 7 * 24 * 3600
```

- [ ] **Step 4: 執行測試確認失敗**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'bot_core'`)

- [ ] **Step 5: 實作 `bot_core/config.py`**

```python
"""Environment configuration. Values are read once at import time."""
import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


TELEGRAM_BOT_TOKEN = _require("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = _require("GEMINI_API_KEY")
UPSTASH_REDIS_REST_URL = _require("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = _require("UPSTASH_REDIS_REST_TOKEN")
WEBHOOK_SECRET = _require("WEBHOOK_SECRET")

GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash")
API_TIMEOUT_SECONDS = _int_env("API_TIMEOUT_SECONDS", 30)

MESSAGE_CACHE_SIZE = 500
DEFAULT_SUMMARY_MESSAGES = 25
MAX_SUMMARY_MESSAGES = 200
CACHE_TTL_SECONDS = 7 * 24 * 3600
```

- [ ] **Step 6: 執行測試確認通過**

Run: `python -m pytest tests/test_config.py -v`
Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add bot_core/ tests/conftest.py tests/test_config.py
git commit -m "feat: add environment configuration module"
```

---

### Task 3: bot_core/cache.py(Redis 訊息快取)

**Files:**
- Create: `bot_core/cache.py`
- Test: `tests/test_cache.py`

Redis 資料模型:`chat:{chat_id}:messages` LIST,值為 JSON 字串,RPUSH + LTRIM(-500,-1)+ EXPIRE 7 天。

- [ ] **Step 1: 寫失敗測試 `tests/test_cache.py`**

```python
import json

import bot_core.cache as cache


class FakeRedis:
    """Minimal in-memory stand-in with Redis-style negative indexing."""

    def __init__(self):
        self.store = {}
        self.ttls = {}

    def _slice(self, lst, start, end):
        n = len(lst)
        s = n + start if start < 0 else start
        e = n + end if end < 0 else end
        return lst[max(s, 0):e + 1]

    def rpush(self, key, *values):
        self.store.setdefault(key, []).extend(values)

    def ltrim(self, key, start, end):
        self.store[key] = self._slice(self.store[key], start, end)

    def expire(self, key, seconds):
        self.ttls[key] = seconds

    def lrange(self, key, start, end):
        return self._slice(list(self.store.get(key, [])), start, end)


def _msg(i):
    return {"message_id": i, "user_id": 1, "user_name": "A", "username": "a",
            "text": f"m{i}", "ts": "2026-01-01T00:00:00Z"}


def _install_fake(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "get_client", lambda: fake)
    return fake


def test_cache_message_trims_to_limit_and_sets_ttl(monkeypatch):
    fake = _install_fake(monkeypatch)
    for i in range(cache.config.MESSAGE_CACHE_SIZE + 10):
        cache.cache_message(-100, _msg(i))
    key = "chat:-100:messages"
    stored = fake.store[key]
    assert len(stored) == cache.config.MESSAGE_CACHE_SIZE
    assert json.loads(stored[-1])["message_id"] == cache.config.MESSAGE_CACHE_SIZE + 9
    assert fake.ttls[key] == cache.config.CACHE_TTL_SECONDS


def test_get_recent_messages_returns_last_n_in_order(monkeypatch):
    _install_fake(monkeypatch)
    for i in range(30):
        cache.cache_message(-100, _msg(i))
    got = cache.get_recent_messages(-100, 5)
    assert [m["message_id"] for m in got] == [25, 26, 27, 28, 29]


def test_get_recent_messages_empty_chat(monkeypatch):
    _install_fake(monkeypatch)
    assert cache.get_recent_messages(-999, 10) == []


def test_get_recent_messages_skips_corrupt_entries(monkeypatch):
    fake = _install_fake(monkeypatch)
    fake.rpush("chat:-100:messages", "{not json}", json.dumps(_msg(1)))
    got = cache.get_recent_messages(-100, 10)
    assert [m["message_id"] for m in got] == [1]
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python -m pytest tests/test_cache.py -v`
Expected: FAIL(`ModuleNotFoundError` 或 `AttributeError: ... has no attribute 'cache_message'`)

- [ ] **Step 3: 實作 `bot_core/cache.py`**

```python
"""Message cache backed by Upstash Redis (HTTP client, serverless-friendly)."""
import json
import logging
from typing import Optional

from upstash_redis import Redis

from bot_core import config

logger = logging.getLogger(__name__)

_client: Optional[Redis] = None


def get_client() -> Redis:
    global _client
    if _client is None:
        _client = Redis(url=config.UPSTASH_REDIS_REST_URL, token=config.UPSTASH_REDIS_REST_TOKEN)
    return _client


def message_key(chat_id: int) -> str:
    return f"chat:{chat_id}:messages"


def cache_message(chat_id: int, msg: dict) -> None:
    redis = get_client()
    key = message_key(chat_id)
    redis.rpush(key, json.dumps(msg, ensure_ascii=False))
    redis.ltrim(key, -config.MESSAGE_CACHE_SIZE, -1)
    redis.expire(key, config.CACHE_TTL_SECONDS)


def get_recent_messages(chat_id: int, n: int) -> list:
    redis = get_client()
    raw_items = redis.lrange(message_key(chat_id), -n, -1)
    messages = []
    for item in raw_items:
        try:
            messages.append(json.loads(item))
        except (TypeError, ValueError):
            logger.warning("Skipping corrupt cache entry in %s", message_key(chat_id))
    return messages
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python -m pytest tests/test_cache.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add bot_core/cache.py tests/test_cache.py
git commit -m "feat: add Upstash Redis message cache module"
```

---

### Task 4: bot_core/summarizer.py(Gemini 摘要)

**Files:**
- Create: `bot_core/summarizer.py`
- Test: `tests/test_summarizer.py`

- [ ] **Step 1: 寫失敗測試 `tests/test_summarizer.py`**

```python
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
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python -m pytest tests/test_summarizer.py -v`
Expected: FAIL(模組不存在)

- [ ] **Step 3: 在 `pytest.ini` 或 `pyproject.toml` 啟用 asyncio 模式**

建立專案根目錄 `pytest.ini`:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 4: 實作 `bot_core/summarizer.py`**

```python
"""Gemini-powered conversation summarization."""
import asyncio
import logging
from typing import List

import google.api_core.exceptions
import google.generativeai as genai
from google.generativeai.types import (
    BlockedPromptException,
    GenerationConfig,
    HarmBlockThreshold,
    HarmCategory,
)

from bot_core import config

logger = logging.getLogger(__name__)

genai.configure(api_key=config.GEMINI_API_KEY)

_SAFETY_SETTINGS = [
    {"category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
     "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE},
    {"category": HarmCategory.HARM_CATEGORY_HATE_SPEECH,
     "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE},
    {"category": HarmCategory.HARM_CATEGORY_HARASSMENT,
     "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE},
    {"category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
     "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE},
]

_model = genai.GenerativeModel(model_name=config.GEMINI_MODEL_NAME, safety_settings=_SAFETY_SETTINGS)

PROMPT_TEMPLATE = """You are a helpful assistant that summarizes Telegram group conversations.
Write the summary in the dominant language of the conversation.
Provide a concise, topic-based summary of the following messages.
Focus on key discussion points, decisions made, questions asked, and action items.

Formatting rules:
- Organize content under bold topic headings prefixed with emoji
- Reference contributors by their Telegram username (@username) when mentioning what they said
- Emphasize important names and numbers with bold (*) or italic (_) markers
- Do not include message IDs

--- Conversation Start ---
{conversation}
--- Conversation End ---

Topic-based summary:"""


class SummaryError(Exception):
    """Summary generation failed. `user_message` is safe to show users."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


def format_messages_for_prompt(messages: List[dict]) -> str:
    lines = []
    for msg in messages:
        timestamp = msg.get("ts", "")
        name = msg.get("user_name") or "?"
        username = msg.get("username")
        text = msg.get("text") or ""
        label = f"@{username} ({name})" if username else name
        lines.append(f"[{timestamp} - {label}]: {text}")
    return "\n".join(lines)


def _raise_from_response(response) -> str:
    """Validate a Gemini response; return the extracted text or raise SummaryError."""
    candidates = getattr(response, "candidates", None)
    if not candidates:
        feedback = getattr(response, "prompt_feedback", None)
        block_reason = getattr(feedback, "block_reason", None)
        reason = getattr(block_reason, "name", str(block_reason))
        logger.warning("Summary blocked by API. Reason: %s", reason)
        raise SummaryError(f"❌ Summary generation was blocked ({reason}). Please try again later.")

    candidate = candidates[0]
    finish_reason = getattr(candidate, "finish_reason", None)
    if finish_reason == "SAFETY":
        raise SummaryError("❌ Summary generation stopped due to safety concerns about the conversation content.")

    try:
        text = response.text.strip()
    except (ValueError, AttributeError):
        raise SummaryError("❌ The AI returned empty content. Please try again later.")
    if not text:
        raise SummaryError("❌ The AI returned an empty summary.")
    return text


async def generate_summary(messages: List[dict]) -> str:
    conversation = format_messages_for_prompt(messages)
    if len(conversation) > 32000:
        logger.warning("Conversation prompt is %d chars; may exceed model limits.", len(conversation))
    prompt = PROMPT_TEMPLATE.format(conversation=conversation)

    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(_model.generate_content, prompt, generation_config=GenerationConfig()),
            timeout=config.API_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        raise SummaryError(
            f"⏱️ The summarization request timed out after {config.API_TIMEOUT_SECONDS} seconds. Please try again later."
        )
    except google.api_core.exceptions.ResourceExhausted:
        raise SummaryError("❌ Rate limit reached on the AI service. Please try again later.")
    except BlockedPromptException as e:
        raise SummaryError(f"❌ Summary generation was blocked ({e}).")
    except google.api_core.exceptions.GoogleAPIError as e:
        logger.error("Gemini API error: %s", e, exc_info=True)
        raise SummaryError("❌ The AI service reported an error. Please try again later.")

    return _raise_from_response(response)
```

- [ ] **Step 5: 執行測試確認通過**

Run: `python -m pytest tests/test_summarizer.py -v`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add bot_core/summarizer.py tests/test_summarizer.py pytest.ini
git commit -m "feat: add Gemini summarizer module"
```

---

### Task 5: bot_core/handlers.py(PTB handlers)

**Files:**
- Create: `bot_core/handlers.py`
- Test: `tests/test_handlers.py`

- [ ] **Step 1: 寫失敗測試 `tests/test_handlers.py`**

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import bot_core.handlers as handlers
import bot_core.summarizer as summarizer
from bot_core.summarizer import SummaryError


class FakeProcessingMessage:
    def __init__(self):
        self.edit_text = AsyncMock()


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
    update.message.text = "hello group"
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


# ---------- summarize_command ----------

async def test_summarize_happy_path(monkeypatch):
    msgs = [{"message_id": 1, "user_name": "A", "username": None, "text": "x", "ts": "t"}]
    monkeypatch.setattr(handlers.cache, "get_recent_messages", lambda chat_id, n: msgs)
    monkeypatch.setattr(summarizer, "generate_summary", AsyncMock(return_value="*Topic* summary"))
    update, context, holder = make_update(args=["10"])
    await handlers.summarize_command(update, context)
    holder["proc"].edit_text.assert_awaited_once()
    assert holder["proc"].edit_text.await_args.kwargs["text"] == "*Topic* summary"


async def test_summarize_empty_cache(monkeypatch):
    monkeypatch.setattr(handlers.cache, "get_recent_messages", lambda chat_id, n: [])
    update, context, holder = make_update(args=[])
    await handlers.summarize_command(update, context)
    assert "cached" in holder["proc"].edit_text.await_args.kwargs["text"].lower()


async def test_summarize_summary_error_shown_to_user(monkeypatch):
    monkeypatch.setattr(handlers.cache, "get_recent_messages", lambda chat_id, n: [{"text": "x"}])
    monkeypatch.setattr(summarizer, "generate_summary",
                        AsyncMock(side_effect=SummaryError("⏱️ timed out")))
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
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python -m pytest tests/test_handlers.py -v`
Expected: FAIL(模組不存在)

- [ ] **Step 3: 實作 `bot_core/handlers.py`**

```python
"""PTB command/message handlers."""
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional

from telegram import Update, constants
from telegram.ext import ContextTypes

# NOTE: import modules (not symbols) so tests can monkeypatch
# summarizer.generate_summary on the source module.
from bot_core import cache, config, summarizer

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "Hi! I summarize recent messages in this group.\n\n"
    f"Use `/summarize [N]` to summarize the last N messages "
    f"(default {config.DEFAULT_SUMMARY_MESSAGES}, max {config.MAX_SUMMARY_MESSAGES}).\n"
    "Example: `/summarize 50`\n\n"
    f"I only remember messages sent while I'm running (up to {config.MESSAGE_CACHE_SIZE} per chat)."
)

ERROR_TEXT = "❌ Something went wrong while generating the summary."


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(
        HELP_TEXT,
        parse_mode=constants.ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None or message.from_user is None or message.chat is None:
        return
    user = message.from_user
    msg = {
        "message_id": message.message_id,
        "user_id": user.id,
        "user_name": user.full_name or user.first_name or str(user.id),
        "username": user.username,
        "text": message.text or "",
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        cache.cache_message(message.chat.id, msg)
    except Exception:
        logger.error("Failed to cache message for chat %s", message.chat.id, exc_info=True)


def _parse_count(args: Optional[List[str]]) -> int:
    if not args:
        return config.DEFAULT_SUMMARY_MESSAGES
    arg = args[0].strip()
    if not arg.isdigit():
        return config.DEFAULT_SUMMARY_MESSAGES
    return min(max(int(arg), 1), config.MAX_SUMMARY_MESSAGES)


async def _deliver(target_message, source_message, text: str) -> None:
    """Edit the processing message (or reply fresh), falling back to plain text."""
    try:
        if target_message is not None:
            await target_message.edit_text(text, parse_mode=constants.ParseMode.MARKDOWN,
                                           disable_web_page_preview=True)
        else:
            await source_message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN,
                                            disable_web_page_preview=True)
    except Exception:
        plain = re.sub(r"[*_\[\]()`]", "", text)
        try:
            if target_message is not None:
                await target_message.edit_text(plain, disable_web_page_preview=True)
            else:
                await source_message.reply_text(plain, disable_web_page_preview=True)
        except Exception:
            logger.error("Failed to deliver summary message", exc_info=True)


async def summarize_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None or message.chat is None:
        return
    chat = message.chat
    if chat.type not in (constants.ChatType.GROUP, constants.ChatType.SUPERGROUP):
        return

    num = _parse_count(context.args)

    processing = None
    try:
        processing = await message.reply_text(
            f"⏳ Summarizing the last {num} cached messages… please wait.",
            disable_notification=True,
        )
    except Exception:
        logger.error("Failed to send processing message in chat %s", chat.id, exc_info=True)
        return

    try:
        messages = cache.get_recent_messages(chat.id, num)
        if not messages:
            await _deliver(processing, message,
                           "I don't have any cached messages for this chat yet. "
                           "Send some messages first, then try again!")
            return
        summary = await summarizer.generate_summary(messages)
        if len(summary) > 4096:
            summary = summary[:4093] + "..."
        await _deliver(processing, message, summary)
    except summarizer.SummaryError as e:
        await _deliver(processing, message, e.user_message)
    except Exception:
        logger.error("Unexpected error during /summarize in chat %s", chat.id, exc_info=True)
        await _deliver(processing, message, ERROR_TEXT)
```

- [ ] **Step 4: 執行全部測試確認通過**

Run: `python -m pytest tests -v`
Expected: 23 passed(test_config 2 + test_cache 4 + test_summarizer 7 + test_handlers 10)

- [ ] **Step 5: Commit**

```bash
git add bot_core/handlers.py tests/test_handlers.py
git commit -m "feat: add PTB handlers for caching and summarization"
```

---

### Task 6: api/webhook.py(Vercel 進入點)

**Files:**
- Create: `api/__init__.py`(空檔案)
- Create: `api/webhook.py`
- Test: `tests/test_webhook.py`

- [ ] **Step 1: 寫失敗測試 `tests/test_webhook.py`**

```python
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import api.webhook as webhook


@pytest.fixture
def client(monkeypatch):
    # Skip PTB initialize/start (would hit Telegram API).
    monkeypatch.setattr(webhook, "_initialized", True)
    process_update = AsyncMock()
    monkeypatch.setattr(webhook.application, "process_update", process_update)
    with TestClient(webhook.app) as c:
        c.process_update_mock = process_update
        yield c


UPDATE_PAYLOAD = {
    "update_id": 1,
    "message": {
        "message_id": 1,
        "date": 1767000000,
        "text": "hello",
        "chat": {"id": -100123, "type": "supergroup", "title": "G"},
        "from": {"id": 42, "is_bot": False, "first_name": "A"},
    },
}


def test_rejects_wrong_secret(client):
    resp = client.post("/api/webhook", json=UPDATE_PAYLOAD,
                       headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"})
    assert resp.status_code == 403
    client.process_update_mock.assert_not_awaited()


def test_rejects_missing_secret(client):
    resp = client.post("/api/webhook", json=UPDATE_PAYLOAD)
    assert resp.status_code == 403


def test_processes_valid_update(client):
    resp = client.post("/api/webhook", json=UPDATE_PAYLOAD,
                       headers={"X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    client.process_update_mock.assert_awaited_once()


def test_process_error_still_returns_ok(client):
    client.process_update_mock.side_effect = RuntimeError("handler blew up")
    resp = client.post("/api/webhook", json=UPDATE_PAYLOAD,
                       headers={"X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret"})
    assert resp.status_code == 200
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python -m pytest tests/test_webhook.py -v`
Expected: FAIL(模組不存在)

- [ ] **Step 3: 建立 `api/__init__.py`(空檔案)**

Run: `New-Item -ItemType File -Path api\__init__.py`
Expected: 檔案建立成功

- [ ] **Step 4: 實作 `api/webhook.py`**

```python
"""Vercel serverless entry point: Telegram webhook receiver."""
import logging
import os
import sys

# Ensure project root is importable when Vercel bundles api/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot_core import config, handlers

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

application: Application = (
    ApplicationBuilder()
    .token(config.TELEGRAM_BOT_TOKEN)
    .updater(None)
    .build()
)
application.add_handler(CommandHandler(["start", "help"], handlers.start_command))
application.add_handler(CommandHandler("summarize", handlers.summarize_command))
application.add_handler(MessageHandler(
    filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS & ~filters.VIA_BOT,
    handlers.handle_message,
))

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

_initialized = False


async def _ensure_started() -> None:
    global _initialized
    if not _initialized:
        await application.initialize()
        await application.start()
        _initialized = True
        logger.info("Telegram application initialized")


@app.post("/api/webhook")
async def telegram_webhook(request: Request) -> JSONResponse:
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret != config.WEBHOOK_SECRET:
        return JSONResponse(status_code=403, content={"ok": False})

    payload = await request.json()
    await _ensure_started()
    update = Update.de_json(payload, application.bot)
    if update is not None:
        try:
            await application.process_update(update)
        except Exception:
            logger.error("Error processing update %s", payload.get("update_id"), exc_info=True)
    return JSONResponse(content={"ok": True})
```

- [ ] **Step 5: 執行全部測試確認通過**

Run: `python -m pytest tests -v`
Expected: 27 passed(23 + test_webhook 4)

- [ ] **Step 6: Commit**

```bash
git add api/ tests/test_webhook.py
git commit -m "feat: add FastAPI webhook entry point for Vercel"
```

---

### Task 7: 新 README(部署指南)與最終驗證

**Files:**
- Modify: `README.md`(整檔覆寫)

- [ ] **Step 1: 覆寫 `README.md`**

````markdown
# Telegram Group Summarizer Bot(Vercel 版)

使用 Google Gemini AI 摘要 Telegram 群組最近訊息的機器人,部署於 Vercel serverless,快取存於 Upstash Redis。

## 功能

- `/summarize [N]`:摘要最近 N 則訊息(預設 25,上限 200)
- `/start` / `/help`:使用說明
- 自動快取群組文字訊息(每群最多 500 則,保留 7 天)
- 以對話主要語言產生主題式摘要

## 架構

```
Telegram ──webhook──▶ Vercel Function (api/webhook.py, FastAPI)
                          ▼
                      PTB process_update()
              ┌───────────┼────────────┐
        文字訊息 → Redis  /start     /summarize N → Gemini → 回覆
```

## 部署步驟

### 1. 推上 GitHub

```bash
git push origin main
```

### 2. Vercel 匯入專案

1. 到 [Vercel Dashboard](https://vercel.com/dashboard) → **Add New... → Project**
2. 匯入你的 repo(Python 會自動偵測)

### 3. 加入 Upstash Redis

1. 專案的 **Storage** 分頁 → **Marketplace** → 選 **Upstash Redis**
2. 選方案(Free 即可)並連結到本專案
3. 完成後 `UPSTASH_REDIS_REST_URL` 與 `UPSTASH_REDIS_REST_TOKEN` 會自動注入

### 4. 設定環境變數

Settings → Environment Variables 加入:

| 變數 | 說明 |
|------|------|
| `TELEGRAM_BOT_TOKEN` | 向 [@BotFather](https://t.me/BotFather) 取得 |
| `GEMINI_API_KEY` | 向 [Google AI Studio](https://aistudio.google.com/app/apikey) 取得 |
| `WEBHOOK_SECRET` | 自行產生的隨機字串,例如 `openssl rand -hex 32` |

選填:`GEMINI_MODEL_NAME`(預設 `gemini-2.0-flash`)、`API_TIMEOUT_SECONDS`(預設 30)。

加完後執行一次 **Redeploy**。

### 5. 註冊 Telegram Webhook

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<your-project>.vercel.app/api/webhook&secret_token=<WEBHOOK_SECRET>&allowed_updates=%5B%22message%22%5D"
```

成功的回應:`{"ok":true,"result":true,"description":"Webhook was set"}`

### 6. BotFather 設定

向 [@BotFather](https://t.me/BotFather):`/mybots` → 選你的 bot → **Bot Settings → Group Privacy → Turn off**(必須,否則收不到群組訊息)。

### 7. 測試

1. 把 bot 加進群組
2. 讓大家發幾則訊息
3. 送出 `/summarize`(或 `/summarize 100`)

## 本地開發

```bash
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env   # 填入實際值
python -m pytest       # 單元測試
vercel dev             # 本地跑 serverless(curl 打 http://localhost:3000/api/webhook 測試)
```

## 限制

- 只能摘要 bot 上線期間收到的訊息(快取存 Redis,保留 7 天)
- Hobby plan 函式上限 60 秒;Gemini 呼叫限時 30 秒
- 冷啟動時首次回應可能延遲數秒
````

- [ ] **Step 2: 最終驗證 —— 完整測試套件**

Run: `python -m pytest tests -v`
Expected: 27 passed, 0 failed

- [ ] **Step 3: 最終驗證 —— 確認 bot.py 已移除且結構正確**

Run: `Get-ChildItem -Recurse -File -Name | Where-Object { $_ -notmatch '\.git\\|__pycache__|\.pytest_cache' }`
Expected: 只包含 `api/`、`bot_core/`、`tests/`、`docs/`、設定檔與 README,沒有 `bot.py`

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: replace README with Vercel deployment guide"
```

---

## 部署後手動驗證(需要使用者操作,不在自動化範圍)

1. `git push` 到 GitHub → Vercel 匯入 → 依新 README 步驟 3-5 操作
2. 用真實 token/key 部署後,呼叫 setWebhook
3. 群組內發訊息後執行 `/summarize`,確認收到摘要
