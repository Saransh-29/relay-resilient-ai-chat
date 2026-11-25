"""Live smoke test against a RUNNING backend with real provider keys.

Usage:
    python scripts/smoke_live.py [BASE_URL]        (default http://localhost:8000)

Requires the backend to run with >= 2 real keys and ENABLE_FAILURE_SIMULATION=true.
Uses only the standard library. Exits non-zero if any check fails. Prints what it
observed; it never invents results.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
TIMEOUT = 90
results: list[tuple[str, bool, str]] = []


def request(method: str, path: str, body=None, headers=None, raw: bytes | None = None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status, text = resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        status, text = exc.code, exc.read().decode()
    elapsed = int((time.perf_counter() - started) * 1000)
    try:
        payload = json.loads(text)
    except ValueError:
        payload = {"_non_json": text[:200]}
    return status, payload, elapsed


def check(name: str, ok: bool, info: str = "") -> bool:
    results.append((name, ok, info))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {info}" if info else ""))
    return ok


def main() -> int:
    run = uuid.uuid4().hex[:8]
    print(f"Smoke testing {BASE} (run {run})\n")

    s, p, _ = request("GET", "/health")
    check("GET /health 200", s == 200 and p.get("status") == "ok", json.dumps(p))
    check("keys_configured >= 2", isinstance(p.get("keys_configured"), int) and p["keys_configured"] >= 2)

    # Unique question per run so the first call is guaranteed to be live.
    question = f"In one short sentence, what is the capital of France? (ref {run})"
    s1, p1, _ = request("POST", "/chat", {"session_id": f"smoke-a-{run}", "message": question})
    md1 = p1.get("metadata", {})
    check("live chat 200", s1 == 200, f"status={s1} body={json.dumps(p1)[:300]}")
    check("live: LIVE_INFERENCE", md1.get("resolution_source") == "LIVE_INFERENCE", json.dumps(md1))
    check("live: non-empty reply", bool(p1.get("reply")), repr(p1.get("reply", ""))[:120])
    check("live: key_id set, tokens > 0",
          md1.get("key_id") is not None and md1.get("input_tokens", 0) > 0 and md1.get("output_tokens", 0) > 0)

    s2, p2, _ = request("POST", "/chat", {"session_id": f"smoke-b-{run}", "message": question})
    md2 = p2.get("metadata", {})
    check("cache: LLM_CACHE on same first message in new session", md2.get("resolution_source") == "LLM_CACHE", json.dumps(md2))
    check("cache: identical reply", bool(p1.get("reply")) and p2.get("reply") == p1.get("reply"))
    check("cache: key_id null, fallback 0", md2.get("key_id") is None and md2.get("fallback_attempts") == 0)
    check("cache: same tokens", bool(md1.get("input_tokens")) and (md2.get("input_tokens"), md2.get("output_tokens")) == (md1.get("input_tokens"), md1.get("output_tokens")))
    check("cache: faster than live", md2.get("latency_ms", 1e9) < md1.get("latency_ms", 0),
          f"live={md1.get('latency_ms')}ms cache={md2.get('latency_ms')}ms")

    s3, p3, _ = request("POST", "/chat", {"session_id": f"smoke-c-{run}", "message": f"Name one primary color. (ref {run})"},
                        headers={"X-Simulate-Failure": "key_1=429"})
    md3 = p3.get("metadata", {})
    check("failover key_1=429 -> 200 key_2, fallback 1",
          s3 == 200 and md3.get("key_id") == "key_2" and md3.get("fallback_attempts") == 1,
          f"status={s3} {json.dumps(md3)}")

    s4, p4, _ = request("POST", "/chat", {"session_id": f"smoke-d-{run}", "message": "hello"},
                        headers={"X-Simulate-Failure": "*=429"})
    check("*=429 -> 503 all providers unavailable", s4 == 503 and p4 == {"detail": "all providers unavailable"}, json.dumps(p4))
    s4h, p4h, _ = request("GET", f"/sessions/smoke-d-{run}/messages")
    check("*=429 stored nothing (history 404)", s4h == 404 and p4h == {"detail": "session not found"})

    sid = f"smoke-a-{run}"
    request("POST", "/chat", {"session_id": sid, "message": "What city did I just ask about? Answer with one word."})
    s5, p5, _ = request("GET", f"/sessions/{sid}/messages")
    msgs = p5.get("messages", [])
    check("history 200 with 4 messages oldest first",
          s5 == 200 and [m.get("role") for m in msgs] == ["user", "assistant", "user", "assistant"],
          f"roles={[m.get('role') for m in msgs]}")
    if len(msgs) == 4:
        print(f"       multi-turn reply: {msgs[3].get('content')!r}")

    s6, p6, _ = request("GET", f"/sessions/unknown-{run}/messages")
    check("unknown session 404", s6 == 404 and p6 == {"detail": "session not found"})

    s7, p7, _ = request("POST", "/chat", {"session_id": "x", "message": "   "})
    check("whitespace message 422", s7 == 422 and "detail" in p7)
    s8, p8, _ = request("POST", "/chat", raw=b'{"session_id": "x", "message": ')
    check("malformed JSON 422", s8 == 422 and "detail" in p8)

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
