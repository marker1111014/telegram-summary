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
    redis.pipeline().rpush(key, json.dumps(msg, ensure_ascii=False)).ltrim(
        key, -config.MESSAGE_CACHE_SIZE, -1
    ).expire(key, config.CACHE_TTL_SECONDS).exec()


def get_recent_messages(chat_id: int, n: int) -> list:
    if n <= 0:
        return []
    redis = get_client()
    raw_items = redis.lrange(message_key(chat_id), -n, -1)
    messages = []
    for item in raw_items:
        try:
            messages.append(json.loads(item))
        except (TypeError, ValueError):
            logger.warning("Skipping corrupt cache entry in %s", message_key(chat_id))
    return messages


def try_acquire_summary_slot(chat_id: int, cooldown_seconds: int) -> int:
    """Acquire the per-chat summarize slot (in-flight mutex + cooldown).

    Returns 0 when acquired; otherwise the remaining cooldown seconds.
    """
    redis = get_client()
    key = f"chat:{chat_id}:summarize_slot"
    acquired = redis.set(key, "1", nx=True, ex=cooldown_seconds)
    if acquired:
        return 0
    remaining = redis.ttl(key)
    return remaining if isinstance(remaining, int) and remaining > 0 else cooldown_seconds


def release_summary_slot(chat_id: int) -> None:
    """Free the per-chat summarize slot (used when a request failed early)."""
    get_client().delete(f"chat:{chat_id}:summarize_slot")


def incr_auto_summary_counter(chat_id: int) -> int:
    """Count messages toward the next automatic summary; refresh TTL."""
    redis = get_client()
    key = f"chat:{chat_id}:auto_count"
    count = redis.incr(key)
    redis.expire(key, config.CACHE_TTL_SECONDS)
    return count


def reset_auto_summary_counter(chat_id: int) -> None:
    get_client().set(f"chat:{chat_id}:auto_count", 0)
