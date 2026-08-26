import importlib

from bot_core import config


def test_required_values_loaded_from_env():
    assert config.TELEGRAM_BOT_TOKEN.startswith("123456789:")
    assert config.GEMINI_API_KEY == "test-gemini-key"
    assert config.UPSTASH_REDIS_REST_URL == "https://example.upstash.io"
    assert config.UPSTASH_REDIS_REST_TOKEN == "test-upstash-token"
    assert config.WEBHOOK_SECRET == "test-webhook-secret"


def test_upstash_vars_fall_back_to_kv_names(monkeypatch):
    """Vercel's Upstash integration may inject only the legacy KV_* names."""
    monkeypatch.setenv("KV_REST_API_URL", "https://kv-fallback.example")
    monkeypatch.setenv("KV_REST_API_TOKEN", "kv-fallback-token")
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)
    try:
        reloaded = importlib.reload(config)
        assert reloaded.UPSTASH_REDIS_REST_URL == "https://kv-fallback.example"
        assert reloaded.UPSTASH_REDIS_REST_TOKEN == "kv-fallback-token"
    finally:
        importlib.reload(config)  # restore primary-path values for other tests


def test_defaults():
    assert config.GEMINI_MODEL_NAME == "gemini-3.6-flash"
    assert config.API_TIMEOUT_SECONDS == 30
    assert config.MESSAGE_CACHE_SIZE == 500
    assert config.DEFAULT_SUMMARY_MESSAGES == 25
    assert config.MAX_SUMMARY_MESSAGES == 200
    assert config.CACHE_TTL_SECONDS == 7 * 24 * 3600
