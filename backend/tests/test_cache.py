"""LiteLLM built-in cache behaviour (real litellm.Cache, provider mocked via mock_response)."""

from __future__ import annotations

import litellm
from litellm.caching.caching import Cache


def _chat(client, session_id, message, **extra):
    return client.post("/chat", json={"session_id": session_id, "message": message, **extra})


def test_same_first_message_new_session_is_cache_hit(client, provider):
    r1 = _chat(client, "sess-A", "What is the capital of France?")
    r2 = _chat(client, "sess-B", "What is the capital of France?")
    assert r1.status_code == r2.status_code == 200
    m1, m2 = r1.json()["metadata"], r2.json()["metadata"]
    assert m1["resolution_source"] == "LIVE_INFERENCE"
    assert m2["resolution_source"] == "LLM_CACHE"
    assert r2.json()["reply"] == r1.json()["reply"]
    assert m2["input_tokens"] == m1["input_tokens"]
    assert m2["output_tokens"] == m1["output_tokens"]
    assert m2["key_id"] is None
    assert m2["fallback_attempts"] == 0
    assert m2["model"] == m1["model"]
    assert len(provider.live_calls) == 1  # the provider was only called once
    # The cache hit is stored in the new session's history with its metadata.
    hist = client.get("/sessions/sess-B/messages").json()["messages"]
    assert hist[1]["metadata"]["resolution_source"] == "LLM_CACHE"


def test_different_message_is_not_cached(client, provider):
    _chat(client, "s1", "What is the capital of France?")
    r = _chat(client, "s2", "What is the capital of Spain?")
    assert r.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert r.json()["reply"] == "Echo: What is the capital of Spain?"
    assert len(provider.live_calls) == 2


def test_same_message_with_different_history_is_not_cached(client, provider):
    _chat(client, "s1", "hello")
    _chat(client, "s1", "again")          # history: hello/echo + again
    r = _chat(client, "s2", "again")      # no history -> different message list
    assert r.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"


def test_different_system_prompt_is_not_cached(client):
    _chat(client, "s1", "hi", system_prompt="You are A.")
    r = _chat(client, "s2", "hi", system_prompt="You are B.")
    assert r.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"


def test_cache_hit_survives_key1_failure(client, provider):
    """A cached answer is still served when key_1 is failing: the next key's lookup hits."""
    import litellm as _l

    _chat(client, "s1", "cache me")
    provider.fail_keys["sk-test-AAAA-1111-secret"] = _l.RateLimitError(message="x", llm_provider="gemini", model="m")
    r = _chat(client, "s2", "cache me")
    assert r.json()["metadata"]["resolution_source"] == "LLM_CACHE"


def test_cache_key_independent_of_api_key_and_call_options():
    cache = Cache(type="local")
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}]
    k1 = cache.get_cache_key(model="gemini/gemini-2.5-flash", messages=messages, api_key="KEY-ONE",
                             num_retries=0, timeout=30, caching=True)
    k2 = cache.get_cache_key(model="gemini/gemini-2.5-flash", messages=messages, api_key="KEY-TWO",
                             num_retries=0, timeout=5, caching=True)
    k3 = cache.get_cache_key(model="gemini/gemini-2.5-flash", messages=messages + [{"role": "user", "content": "x"}],
                             api_key="KEY-ONE")
    k4 = cache.get_cache_key(model="groq/llama-3.1-8b-instant", messages=messages, api_key="KEY-ONE")
    assert k1 == k2
    assert k1 != k3
    assert k1 != k4


def test_cache_hit_across_keys_end_to_end(client, provider):
    """Answer produced by key_2 (after simulated key_1 failure) is reused for a later normal request."""
    r1 = client.post("/chat", json={"session_id": "s1", "message": "shared q"},
                     headers={"X-Simulate-Failure": "key_1=429"})
    assert r1.json()["metadata"]["key_id"] == "key_2"
    r2 = _chat(client, "s2", "shared q")  # tried with key_1 -> api_key differs, still a hit
    assert r2.json()["metadata"]["resolution_source"] == "LLM_CACHE"
    assert r2.json()["reply"] == r1.json()["reply"]


def test_cache_hit_is_faster_than_live(client, provider):
    # Simulate provider latency inside LiteLLM's provider path (mock_delay), which a
    # cache hit never reaches.
    orig_real = provider.real

    async def real_with_delay(**kwargs):
        kwargs.setdefault("mock_delay", 0.2)
        return await orig_real(**kwargs)

    provider.real = real_with_delay
    r1 = _chat(client, "s1", "timing question")
    r2 = _chat(client, "s2", "timing question")
    assert r2.json()["metadata"]["resolution_source"] == "LLM_CACHE"
    assert r2.json()["metadata"]["latency_ms"] < r1.json()["metadata"]["latency_ms"]
    assert r1.json()["metadata"]["latency_ms"] >= 200


def test_disk_cache_type(app_factory, tmp_path, provider):
    import pytest

    pytest.importorskip("diskcache")
    c = app_factory(cache_type="disk", cache_dir=str(tmp_path / "cache"))
    assert type(litellm.cache.cache).__name__ == "DiskCache"
    _chat(c, "s1", "disk q")
    assert _chat(c, "s2", "disk q").json()["metadata"]["resolution_source"] == "LLM_CACHE"
