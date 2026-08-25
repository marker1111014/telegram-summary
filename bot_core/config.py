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
