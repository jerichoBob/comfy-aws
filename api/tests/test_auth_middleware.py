"""Unit tests for ApiKeyMiddleware — real middleware, real settings, no mocks."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse

from app.middleware.auth import ApiKeyMiddleware


def _make_app(api_keys: str = "") -> FastAPI:
    """Build a minimal test app with auth middleware and a couple of routes."""
    import os
    os.environ["API_KEYS"] = api_keys
    # Re-import settings so it picks up the new env var
    import importlib
    import app.config as config_mod
    importlib.reload(config_mod)
    import app.middleware.auth as auth_mod
    importlib.reload(auth_mod)

    test_app = FastAPI()
    test_app.add_middleware(auth_mod.ApiKeyMiddleware)

    @test_app.get("/health")
    def health():
        return {"status": "ok"}

    @test_app.get("/jobs")
    def jobs():
        return {"jobs": []}

    return test_app


@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    """Ensure API_KEYS env is cleaned up after each test."""
    yield
    monkeypatch.delenv("API_KEYS", raising=False)


def test_no_key_auth_enabled(monkeypatch):
    monkeypatch.setenv("API_KEYS", "secret123")
    client = TestClient(_make_app("secret123"), raise_server_exceptions=True)
    resp = client.get("/jobs")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or missing API key"


def test_wrong_key_auth_enabled(monkeypatch):
    monkeypatch.setenv("API_KEYS", "secret123")
    client = TestClient(_make_app("secret123"))
    resp = client.get("/jobs", headers={"X-API-Key": "wrongkey"})
    assert resp.status_code == 401


def test_valid_key_auth_enabled(monkeypatch):
    monkeypatch.setenv("API_KEYS", "secret123")
    client = TestClient(_make_app("secret123"))
    resp = client.get("/jobs", headers={"X-API-Key": "secret123"})
    assert resp.status_code == 200


def test_no_key_auth_disabled(monkeypatch):
    monkeypatch.setenv("API_KEYS", "")
    client = TestClient(_make_app(""))
    resp = client.get("/jobs")
    assert resp.status_code == 200


def test_health_exempt_when_auth_enabled(monkeypatch):
    monkeypatch.setenv("API_KEYS", "secret123")
    client = TestClient(_make_app("secret123"))
    resp = client.get("/health")
    assert resp.status_code == 200


def test_multiple_keys_each_accepted(monkeypatch):
    monkeypatch.setenv("API_KEYS", "key-one,key-two,key-three")
    client = TestClient(_make_app("key-one,key-two,key-three"))
    for key in ("key-one", "key-two", "key-three"):
        resp = client.get("/jobs", headers={"X-API-Key": key})
        assert resp.status_code == 200, f"Key {key!r} was rejected"
