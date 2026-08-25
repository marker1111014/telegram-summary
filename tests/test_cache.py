import json

import bot_core.cache as cache


class FakePipeline:
    """Queues commands like upstash_redis Pipeline, applied on exec()."""

    def __init__(self, fake):
        self._fake = fake
        self._ops = []

    def rpush(self, key, *values):
        self._ops.append(("rpush", key, values))
        return self

    def ltrim(self, key, start, end):
        self._ops.append(("ltrim", key, start, end))
        return self

    def expire(self, key, seconds):
        self._ops.append(("expire", key, seconds))
        return self

    def exec(self):
        for op in self._ops:
            if op[0] == "rpush":
                self._fake.rpush(op[1], *op[2])
            elif op[0] == "ltrim":
                self._fake.ltrim(op[1], op[2], op[3])
            else:
                self._fake.expire(op[1], op[2])


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

    def pipeline(self):
        return FakePipeline(self)


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


def test_cache_message_preserves_non_ascii(monkeypatch):
    _install_fake(monkeypatch)
    msg = _msg(1)
    msg["text"] = "中文測試"
    cache.cache_message(-100, msg)
    got = cache.get_recent_messages(-100, 1)
    assert got[0]["text"] == "中文測試"
