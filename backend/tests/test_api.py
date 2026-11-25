"""Contract, validation, history and storage tests."""

from __future__ import annotations

import sqlite3

import pytest

from app.config import Settings, sqlite_path_from_url


def _chat(client, session_id="s-1", message="What is the capital of France?", headers=None, **extra):
    body = {"session_id": session_id, "message": message, **extra}
    return client.post("/chat", json=body, headers=headers or {})


def _rows(client, sql, params=()):
    path = client.app.state.db.path
    with sqlite3.connect(path) as conn:
        return conn.execute(sql, params).fetchall()


# ---------------- health ----------------

def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}


def test_health_503_without_keys(app_factory):
    c = app_factory(llm_api_keys=[])
    r = c.get("/health")
    assert r.status_code == 503
    assert r.json()["status"] != "ok"
    assert "detail" in r.json()


# ---------------- chat happy path / contract ----------------

def test_chat_contract(client, provider):
    r = _chat(client)
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"session_id", "reply", "metadata"}
    assert body["session_id"] == "s-1"
    assert isinstance(body["reply"], str) and body["reply"]
    md = body["metadata"]
    assert set(md) >= {
        "resolution_source", "model", "latency_ms", "input_tokens",
        "output_tokens", "key_id", "fallback_attempts",
    }
    assert md["resolution_source"] == "LIVE_INFERENCE"
    assert md["model"] == "gemini/gemini-2.5-flash"
    assert isinstance(md["latency_ms"], int) and md["latency_ms"] >= 0
    assert isinstance(md["input_tokens"], int) and md["input_tokens"] > 0
    assert isinstance(md["output_tokens"], int) and md["output_tokens"] > 0
    assert md["key_id"] == "key_1"
    assert md["fallback_attempts"] == 0
    assert len(provider.live_calls) == 1
    call = provider.live_calls[0]
    assert call["num_retries"] == 0
    assert call["api_key"] == "sk-test-AAAA-1111-secret"


def test_message_is_trimmed_and_stored_trimmed(client, provider):
    r = _chat(client, message="   hello there   ")
    assert r.status_code == 200
    assert provider.live_calls[0]["messages"][-1] == {"role": "user", "content": "hello there"}
    hist = client.get("/sessions/s-1/messages").json()["messages"]
    assert hist[0] == {"role": "user", "content": "hello there"}


def test_message_4000_chars_after_trim_ok(client):
    r = _chat(client, message="  " + "a" * 4000 + "  ")
    assert r.status_code == 200


# ---------------- validation (422) ----------------

@pytest.mark.parametrize(
    "body",
    [
        {"message": "hi"},                                  # missing session_id
        {"session_id": "s"},                                # missing message
        {"session_id": "s", "message": ""},                 # empty message
        {"session_id": "s", "message": "   \n\t "},         # whitespace-only message
        {"session_id": "s", "message": "a" * 4001},         # too long
        {"session_id": "", "message": "hi"},                # empty session_id
        {"session_id": "   ", "message": "hi"},             # whitespace-only session_id
        {"session_id": "x" * 129, "message": "hi"},         # session_id too long
        {"session_id": 123, "message": "hi"},               # wrong type
        {"session_id": "s", "message": 42},                 # wrong type
        {"session_id": "s", "message": None},               # null
        {"session_id": "s", "message": "hi", "system_prompt": "p" * 4001},
    ],
)
def test_validation_422(client, provider, body):
    r = client.post("/chat", json=body)
    assert r.status_code == 422
    assert "detail" in r.json()
    assert provider.live_calls == []
    assert _rows(client, "SELECT COUNT(*) FROM messages")[0][0] == 0
    assert _rows(client, "SELECT COUNT(*) FROM sessions")[0][0] == 0


def test_session_id_128_chars_ok(client):
    assert _chat(client, session_id="x" * 128).status_code == 200


@pytest.mark.parametrize("raw", ['{"session_id": "s", "message": ', "not json", "[]", '"str"'])
def test_malformed_json_422(client, raw):
    r = client.post("/chat", content=raw, headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert "detail" in r.json()


def test_empty_system_prompt_treated_as_absent(client, provider):
    r = _chat(client, system_prompt="   ")
    assert r.status_code == 200
    assert provider.live_calls[0]["messages"][0] == {"role": "system", "content": "You are a test assistant."}


# ---------------- history ----------------

def test_history_shape_and_order(client):
    r1 = _chat(client, message="first")
    r2 = _chat(client, message="second")
    r = client.get("/sessions/s-1/messages")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "s-1"
    msgs = body["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[0] == {"role": "user", "content": "first"}
    assert "metadata" not in msgs[0] and "metadata" not in msgs[2]
    assert msgs[1]["content"] == r1.json()["reply"]
    assert msgs[1]["metadata"] == r1.json()["metadata"]
    assert msgs[3]["metadata"]["resolution_source"] == r2.json()["metadata"]["resolution_source"]
    assert all(m["role"] != "system" for m in msgs)


def test_history_unknown_session_404(client):
    r = client.get("/sessions/nope/messages")
    assert r.status_code == 404
    assert r.json() == {"detail": "session not found"}


def test_multi_turn_history_sent_to_llm(client, provider):
    _chat(client, message="My name is Ada.")
    _chat(client, message="What is my name?")
    sent = provider.live_calls[1]["messages"]
    assert sent[0]["role"] == "system"
    assert sent[1] == {"role": "user", "content": "My name is Ada."}
    assert sent[2] == {"role": "assistant", "content": "Echo: My name is Ada."}
    assert sent[3] == {"role": "user", "content": "What is my name?"}
    # Only role/content go to the provider, never metadata.
    assert all(set(m) == {"role", "content"} for m in sent)


def test_session_isolation(client, provider):
    _chat(client, session_id="a", message="alpha secret")
    _chat(client, session_id="b", message="beta question")
    sent_b = provider.live_calls[1]["messages"]
    assert all("alpha" not in m["content"] for m in sent_b)
    assert len(client.get("/sessions/a/messages").json()["messages"]) == 2
    assert len(client.get("/sessions/b/messages").json()["messages"]) == 2


def test_system_prompt_persists_and_is_excluded_from_history(client, provider):
    _chat(client, message="one", system_prompt="You are a pirate.")
    _chat(client, message="two")  # no override -> stored prompt is reused
    assert provider.live_calls[0]["messages"][0] == {"role": "system", "content": "You are a pirate."}
    assert provider.live_calls[1]["messages"][0] == {"role": "system", "content": "You are a pirate."}
    _chat(client, message="three", system_prompt="You are a poet.")  # explicit override persists
    _chat(client, message="four")
    assert provider.live_calls[3]["messages"][0] == {"role": "system", "content": "You are a poet."}
    msgs = client.get("/sessions/s-1/messages").json()["messages"]
    assert all(m["role"] in ("user", "assistant") for m in msgs)
    assert all("pirate" not in m["content"] and "poet" not in m["content"] for m in msgs)


def test_pair_stored_atomically_with_timestamps(client):
    _chat(client)
    rows = _rows(client, "SELECT role, metadata, created_at FROM messages ORDER BY id")
    assert [r[0] for r in rows] == ["user", "assistant"]
    assert rows[0][1] is None and rows[1][1] is not None
    assert all(r[2].endswith("Z") and "T" in r[2] for r in rows)


def test_save_exchange_is_atomic(client):
    db = client.app.state.db
    # The assistant insert fails (metadata not JSON-serialisable) AFTER the session
    # upsert and user insert ran: the whole transaction must roll back.
    with pytest.raises(TypeError):
        db.save_exchange("s-x", "prompt", "user msg", "reply", {"bad": object()})
    assert _rows(client, "SELECT COUNT(*) FROM messages")[0][0] == 0
    assert _rows(client, "SELECT COUNT(*) FROM sessions")[0][0] == 0


def test_db_write_failure_returns_json_500_and_stores_nothing(client, monkeypatch):
    db = client.app.state.db

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(db, "save_exchange", broken)
    r = _chat(client)
    assert r.status_code == 500
    assert r.json() == {"detail": "internal server error"}
    assert _rows(client, "SELECT COUNT(*) FROM messages")[0][0] == 0


def test_unhandled_error_is_json_500(client, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("kaboom with traceback")

    monkeypatch.setattr(client.app.state.chat, "handle", boom)
    r = _chat(client)
    assert r.status_code == 500
    assert r.json() == {"detail": "internal server error"}
    assert "kaboom" not in r.text and "Traceback" not in r.text


def test_unknown_route_is_json(client):
    r = client.get("/does-not-exist")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert "detail" in r.json()


def test_cors_allows_simulation_header(client):
    r = client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-simulate-failure",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    allowed = r.headers["access-control-allow-headers"].lower()
    assert "x-simulate-failure" in allowed and "content-type" in allowed


# ---------------- config ----------------

@pytest.mark.parametrize(
    "url,expected",
    [
        ("sqlite:////data/app.db", "/data/app.db"),
        ("sqlite:///./app.db", "./app.db"),
        ("sqlite:///app.db", "app.db"),
        ("/tmp/x.db", "/tmp/x.db"),
    ],
)
def test_sqlite_url_parsing(url, expected):
    assert sqlite_path_from_url(url) == expected


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("LLM_API_KEYS", " k1 , k2 ,k3")
    monkeypatch.setenv("LLM_MODEL", "gemini/gemini-2.5-flash")
    monkeypatch.setenv("LLM_MODELS", "gemini/gemini-2.5-flash,groq/llama-3.1-8b-instant")
    monkeypatch.setenv("ENABLE_FAILURE_SIMULATION", "TRUE")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://a.com, http://b.com")
    s = Settings.from_env(load_env_file=False)
    assert [(k.key_id, k.api_key, k.model) for k in s.key_pool] == [
        ("key_1", "k1", "gemini/gemini-2.5-flash"),
        ("key_2", "k2", "groq/llama-3.1-8b-instant"),
        ("key_3", "k3", "gemini/gemini-2.5-flash"),
    ]
    assert s.enable_failure_simulation is True
    assert s.allowed_origins == ["http://a.com", "http://b.com"]
