from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import api.webhook as webhook


@pytest.fixture
def client(monkeypatch):
    # Skip PTB initialize/start (would hit Telegram API).
    monkeypatch.setattr(webhook, "_initialized", True)
    process_update = AsyncMock()
    # PTB >= 22 Application uses __slots__ (no instance __dict__), so patch
    # process_update on the class rather than the singleton instance.
    monkeypatch.setattr(webhook.Application, "process_update", process_update)
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
    assert client.process_update_mock.await_args.args[0].update_id == 1


def test_process_error_still_returns_ok(client):
    client.process_update_mock.side_effect = RuntimeError("handler blew up")
    resp = client.post("/api/webhook", json=UPDATE_PAYLOAD,
                       headers={"X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret"})
    assert resp.status_code == 200
