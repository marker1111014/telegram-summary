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
