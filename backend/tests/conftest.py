"""Shared fixtures.

The provider boundary is mocked by wrapping ``litellm.acompletion`` so it injects
LiteLLM's own ``mock_response`` parameter. This keeps the REAL LiteLLM pipeline in
play, including the built-in Cache (get_cache_key, lookup, store, cache_hit flag),
while never touching the network.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

import litellm
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Avoid reading a developer's .env during tests and keep LiteLLM offline.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

TEST_KEYS = ["sk-test-AAAA-1111-secret", "sk-test-BBBB-2222-secret"]


class FakeProvider:
    """Records every call that reached LiteLLM and lets tests decide outcomes per key."""

    def __init__(self, real_acompletion: Callable):
        self.real = real_acompletion
        self.calls: list[dict[str, Any]] = []  # calls that reached the (mock) provider
        self.reply_for: Callable[[list[dict]], str] = (
            lambda messages: f"Echo: {messages[-1]['content']}"
        )
        self.fail_keys: dict[str, Exception] = {}  # api_key -> exception to raise

    async def __call__(self, **kwargs):
        api_key = kwargs.get("api_key")
        if api_key in self.fail_keys:
            self.calls.append(kwargs)
            raise self.fail_keys[api_key]
        # A failure on the real wire would also be raised before caching, so mimic via mock_response.
        kwargs["mock_response"] = self.reply_for(kwargs["messages"])
        response = await self.real(**kwargs)
        if not (response._hidden_params or {}).get("cache_hit"):
            self.calls.append(kwargs)
        return response

    @property
    def live_calls(self) -> list[dict[str, Any]]:
        return self.calls


def make_settings(tmp_path: Path, **overrides) -> Settings:
    base = dict(
        llm_api_keys=list(TEST_KEYS),
        llm_model="gemini/gemini-2.5-flash",
        llm_models=[],
        database_url=f"sqlite:///{(tmp_path / 'data' / 'app.db').as_posix()}",
        allowed_origins=["http://localhost:3000"],
        enable_failure_simulation=True,
        default_system_prompt="You are a test assistant.",
        cache_type="local",
        llm_timeout_seconds=5.0,
        log_level="INFO",
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture(autouse=True)
def _reset_litellm_cache():
    previous = litellm.cache
    litellm.cache = None
    yield
    litellm.cache = previous


@pytest.fixture
def provider(monkeypatch) -> FakeProvider:
    fake = FakeProvider(litellm.acompletion)
    monkeypatch.setattr(litellm, "acompletion", fake)
    return fake


@pytest.fixture
def app_factory(tmp_path, provider):
    clients: list[TestClient] = []

    def _make(**overrides) -> TestClient:
        settings = make_settings(tmp_path, **overrides)
        client = TestClient(create_app(settings), raise_server_exceptions=False)
        client.__enter__()  # run lifespan (DB init, gateway, cache)
        clients.append(client)
        return client

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(app_factory) -> TestClient:
    return app_factory()
