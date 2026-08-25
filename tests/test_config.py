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
