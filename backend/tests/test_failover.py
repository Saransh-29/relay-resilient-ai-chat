"""Key-pool failover, X-Simulate-Failure and the all-keys-failed 503."""

from __future__ import annotations

import logging
import sqlite3

import httpx
import litellm
import pytest

from app.simulation import SimulationHeaderError, parse_simulation_header
from tests.conftest import TEST_KEYS

SIM = "X-Simulate-Failure"


def _chat(client, session_id="s-f", message="hello failover", headers=None):
    return client.post("/chat", json={"session_id": session_id, "message": message}, headers=headers or {})


def _count(client, table):
    with sqlite3.connect(client.app.state.db.path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_simulated_key1_failure_falls_over_to_key2(client, provider, status):
    r = _chat(client, headers={SIM: f"key_1={status}"})
    assert r.status_code == 200, r.text
    md = r.json()["metadata"]
    assert md["key_id"] == "key_2"
    assert md["fallback_attempts"] == 1
    assert md["resolution_source"] == "LIVE_INFERENCE"
    assert r.json()["reply"] == "Echo: hello failover"  # a real answer, not an error text
    # key_1 never reached the provider; key_2 did.
    assert [c["api_key"] for c in provider.live_calls] == [TEST_KEYS[1]]


def test_simulate_all_keys_503_and_nothing_stored(client, provider):
    r = _chat(client, headers={SIM: "*=429"})
    assert r.status_code == 503
    assert r.json() == {"detail": "all providers unavailable"}
    assert provider.live_calls == []
    assert _count(client, "messages") == 0 and _count(client, "sessions") == 0
    assert client.get("/sessions/s-f/messages").status_code == 404


def test_simulate_both_keys_listed_503(client):
    r = _chat(client, headers={SIM: " key_1 = 429 , key_2=500 "})
    assert r.status_code == 503
    assert r.json() == {"detail": "all providers unavailable"}


def test_specific_entry_overrides_wildcard(client):
    # key_2 is explicitly set... to a failing status as well; '*' covers key_1.
    r = _chat(client, headers={SIM: "*=503,key_2=429"})
    assert r.status_code == 503


def test_simulation_ignored_when_disabled(app_factory, provider):
    c = app_factory(enable_failure_simulation=False)
    r = _chat(c, headers={SIM: "*=429"})
    assert r.status_code == 200
    assert r.json()["metadata"]["key_id"] == "key_1"
    # Even a malformed header is ignored when the switch is off.
    assert _chat(c, message="other", headers={SIM: "garbage"}).status_code == 200


@pytest.mark.parametrize("header", ["garbage", "key_1=404", "key_1=abc", "foo=429", "key_1=429,", "key_0=429"])
def test_malformed_simulation_header_422(client, provider, header):
    r = _chat(client, headers={SIM: header})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str) and r.json()["detail"]
    assert provider.live_calls == []
    assert _count(client, "messages") == 0


def test_parse_simulation_header():
    assert parse_simulation_header("key_1=429") == {"key_1": 429}
    assert parse_simulation_header(" key_1 = 429 , key_2=500 ") == {"key_1": 429, "key_2": 500}
    assert parse_simulation_header("*=502") == {"*": 502}
    assert parse_simulation_header("") == {}
    with pytest.raises(SimulationHeaderError):
        parse_simulation_header("key_1=418")


def test_simulated_request_bypasses_cache_read(client, provider):
    first = _chat(client, session_id="c1", message="cached question")
    assert first.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    # Same prompt would be a cache hit, but simulation forces real failover.
    r = _chat(client, session_id="c2", message="cached question", headers={SIM: "key_1=429"})
    md = r.json()["metadata"]
    assert md["resolution_source"] == "LIVE_INFERENCE"
    assert md["key_id"] == "key_2" and md["fallback_attempts"] == 1
    assert provider.live_calls[-1].get("cache") == {"no-cache": True}


@pytest.mark.parametrize(
    "exc",
    [
        litellm.RateLimitError(message="RESOURCE_EXHAUSTED quota", llm_provider="gemini", model="m"),
        litellm.InternalServerError(message="boom", llm_provider="gemini", model="m"),
        litellm.ServiceUnavailableError(message="down", llm_provider="gemini", model="m"),
        litellm.Timeout(message="timed out", model="m", llm_provider="gemini"),
        litellm.APIConnectionError(message="conn reset", llm_provider="gemini", model="m"),
        litellm.AuthenticationError(message="bad key", llm_provider="gemini", model="m"),
        RuntimeError("unexpected"),
    ],
)
def test_real_provider_errors_fail_over(client, provider, exc):
    provider.fail_keys[TEST_KEYS[0]] = exc
    r = _chat(client)
    assert r.status_code == 200
    assert r.json()["metadata"]["key_id"] == "key_2"
    assert r.json()["metadata"]["fallback_attempts"] == 1


def test_real_provider_all_fail_503(client, provider):
    provider.fail_keys[TEST_KEYS[0]] = litellm.RateLimitError(message="429", llm_provider="gemini", model="m")
    provider.fail_keys[TEST_KEYS[1]] = litellm.InternalServerError(message="500", llm_provider="gemini", model="m")
    r = _chat(client)
    assert r.status_code == 503
    assert r.json() == {"detail": "all providers unavailable"}
    assert _count(client, "messages") == 0


def test_mixed_provider_pool_uses_per_key_model(app_factory, provider):
    c = app_factory(llm_models=["gemini/gemini-2.5-flash", "groq/llama-3.1-8b-instant"])
    r = _chat(c, headers={SIM: "key_1=429"})
    assert r.status_code == 200
    assert r.json()["metadata"]["model"] == "groq/llama-3.1-8b-instant"
    assert provider.live_calls[-1]["model"] == "groq/llama-3.1-8b-instant"


def test_no_key_leakage_in_responses_or_logs(client, provider, caplog):
    caplog.set_level(logging.DEBUG)
    secret_exc = litellm.AuthenticationError(
        message=f"invalid api key {TEST_KEYS[0]}", llm_provider="gemini", model="m"
    )
    provider.fail_keys[TEST_KEYS[0]] = secret_exc
    responses = [
        _chat(client),
        _chat(client, headers={SIM: "key_1=429"}),
        _chat(client, headers={SIM: "*=429"}),
        client.get("/health"),
        client.get("/sessions/s-f/messages"),
    ]
    for r in responses:
        for key in TEST_KEYS:
            assert key not in r.text
    for key in TEST_KEYS:
        assert key not in caplog.text
    assert "key_1" in caplog.text  # failures are logged by key id
    with sqlite3.connect(client.app.state.db.path) as conn:
        dump = "\n".join(str(row) for row in conn.execute("SELECT * FROM messages"))
    for key in TEST_KEYS:
        assert key not in dump


def test_redaction_filter_masks_keys():
    from app.logging_utils import SecretRedactingFilter

    f = SecretRedactingFilter(TEST_KEYS)
    record = logging.LogRecord("x", logging.ERROR, __file__, 1, "leak %s here", (TEST_KEYS[1],), None)
    f.filter(record)
    assert TEST_KEYS[1] not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()


def test_httpx_status_error_also_fails_over(client, provider):
    req = httpx.Request("POST", "https://example.invalid")
    provider.fail_keys[TEST_KEYS[0]] = httpx.HTTPStatusError(
        "502", request=req, response=httpx.Response(502, request=req)
    )
    r = _chat(client)
    assert r.status_code == 200 and r.json()["metadata"]["key_id"] == "key_2"


def test_empty_reply_fails_over_and_does_not_poison_cache(client, provider):
    # First provider call (key_1) returns whitespace only -> treated as a failure.
    # LiteLLM caches that blank answer, so key_2 must bypass the cache read.
    replies = iter([" "])
    provider.reply_for = lambda messages: next(replies, f"Echo: {messages[-1]['content']}")
    r = _chat(client, session_id="s-empty-1", message="blank first")
    assert r.status_code == 200, r.text
    md = r.json()["metadata"]
    assert (md["key_id"], md["fallback_attempts"]) == ("key_2", 1)
    assert r.json()["reply"] == "Echo: blank first"
    # The good answer replaced the blank one in the cache.
    r2 = _chat(client, session_id="s-empty-2", message="blank first")
    assert r2.status_code == 200
    assert r2.json()["metadata"]["resolution_source"] == "LLM_CACHE"
    assert r2.json()["reply"] == "Echo: blank first"
