"""Environment configuration. Values are read once at import time."""
import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _first_env(*names: str) -> str:
    """Return the first non-empty value among the given variable names."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    raise ValueError(f"Missing required environment variable (one of): {', '.join(names)}")


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
# Upstash integration may inject either naming set depending on version.
UPSTASH_REDIS_REST_URL = _first_env("UPSTASH_REDIS_REST_URL", "KV_REST_API_URL")
UPSTASH_REDIS_REST_TOKEN = _first_env("UPSTASH_REDIS_REST_TOKEN", "KV_REST_API_TOKEN")
WEBHOOK_SECRET = _require("WEBHOOK_SECRET")

GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash")
API_TIMEOUT_SECONDS = _int_env("API_TIMEOUT_SECONDS", 30)

MESSAGE_CACHE_SIZE = 500
DEFAULT_SUMMARY_MESSAGES = 25
MAX_SUMMARY_MESSAGES = 200
CACHE_TTL_SECONDS = 7 * 24 * 3600
