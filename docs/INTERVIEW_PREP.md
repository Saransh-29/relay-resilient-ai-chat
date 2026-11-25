# Interview Prep: Relay

Short answers grounded in the code. File references are relative to the repo root.

---

**1. Walk me through a `POST /chat` request.**
1. Pydantic validates the body (`strict=True`; the message is trimmed and must be 1–4000 characters). Failures give a 422.
2. The `X-Simulate-Failure` header is parsed if simulation is enabled. A malformed header gives a 422.
3. `ChatService.handle` loads the session's stored system prompt and history from SQLite and builds `[system] + history + [user]`.
4. `LLMGateway.complete` tries `key_1..key_n` through `litellm.acompletion`. The cache is consulted inside that call.
5. On success, the code builds the metadata (the latency timer stops here) and writes the session upsert plus the user and assistant rows in one transaction, then returns.
6. If every key fails, the result is a 503 and nothing is written.

**2. Why an explicit failover loop instead of LiteLLM's Router?**
The contract needs an exact `key_id` and `fallback_attempts` for each request, plus per-key failure injection that lasts for one request only. With a loop, both are just the loop index and an `if` before the call. The Router's fallbacks, retries and cooldowns are stateful across requests and would make the reported numbers harder to guarantee. LiteLLM still does the actual work: provider calls, error mapping into `RateLimitError` and similar, and caching. At scale I would move to the Router to get cooldowns and load balancing (see Q13).

**3. Why `num_retries=0`?**
LiteLLM retries would hit the *same* failing key again. That adds latency, burns quota and hides the failover. Every attempt is bounded by `timeout=LLM_TIMEOUT_SECONDS`, so a hung provider costs at most one timeout per key.

**4. Which errors trigger failover?**
All of them. The loop catches `Exception`, so failover happens on 429, quota errors, 5xx, timeouts, connection errors, authentication errors and anything unexpected. An empty completion also counts as a failure and is converted into a 502 `APIError`. I chose "fail open to the next key" because the user-facing goal is "never broken". Retrying a bad request on another key is harmless here, because validation has already rejected malformed input.

**5. How is the cache key designed?**
I use LiteLLM's own `Cache.get_cache_key`, which hashes only recognised LLM API params. Here that is `model` + `messages`. `api_key`, `timeout`, `num_retries` and `caching` are not in that set, and `session_id` is never sent to the LLM. So the key is exactly what the contract asks for: the model plus the full message list (system prompt, history and new message). I verified this in `litellm/caching/caching.py` and pinned it with `tests/test_cache.py::test_cache_key_independent_of_api_key_and_call_options`. The practical result is that an answer produced by `key_2` is reused by a later request that starts on `key_1`.

**6. How do you know a response came from the cache?**
LiteLLM sets `response._hidden_params["cache_hit"]`. When it is set, the response gets `LLM_CACHE`, `key_id: null`, `fallback_attempts: 0`, and the token usage stored with the cached response, which is identical to the original call.

**7. Why do simulated requests bypass the cache read?**
Otherwise a demo of `key_1=429` on an already-cached message would return `LLM_CACHE` and never exercise failover. Simulated requests send `cache={"no-cache": True}`, which skips the lookup but still stores the result. The contract also says a simulated request must return a real answer, so the bypass is what makes the demo honest. The cost is one real provider call per simulated request.

**8. What race exists in cache writes, and how did you handle it?**
LiteLLM stores the response in a fire-and-forget `asyncio` task after `acompletion` returns. If the HTTP response goes out immediately, an identical request that follows straight away can arrive before the write and miss the cache. After a live answer, the gateway yields to the event loop a few times (`await asyncio.sleep(0)` five times) so the pending write runs first. It is a workaround that depends on LiteLLM internals, so it is documented as a known limitation. A proper fix is to write the cache explicitly, or to use a cache with synchronous writes.

**9. What about an empty reply being cached?**
LiteLLM may cache an empty completion before my code inspects it. When the reply is empty, the gateway treats it as a failure *and* sets `bypass_cache_read = True` for the remaining keys. That stops the poisoned entry being served as a "hit" by the next key in the same request.

**10. How do you keep history atomic?**
Nothing is written until the LLM succeeds. Then `save_exchange` runs `BEGIN IMMEDIATE`, upserts the `sessions` row and inserts the user and assistant rows, then commits. Any exception triggers a rollback. So a 422, a 503 or a failed write never leaves half an exchange. Tests cover the 503 path and a simulated write failure.

**11. How is latency measured, and why is a cache hit faster?**
`time.perf_counter()` runs from the start of `ChatService.handle` until the LLM result is resolved, before the DB write. That way the stored and returned metadata are identical. A cache hit skips the network round trip, so it takes a few milliseconds against hundreds for a live call. `tests/test_cache.py::test_cache_hit_is_faster_than_live` adds a 200 ms mocked provider delay and asserts the ordering.

**12. Why SQLite, and how is it configured?**
The assignment requires it. The file path comes from `DATABASE_URL` (`/data/app.db` on a named Docker volume), and the schema is created on startup. I added a `sessions` table to persist the system prompt and an index on `(session_id, id)` for ordered history reads. The database uses WAL mode, a 10 s busy timeout and a fresh connection per operation, and blocking calls run in Starlette's threadpool so the event loop never blocks.

**13. What would you change at scale?**
- **Cache:** Redis through LiteLLM's `Cache(type="redis")`, shared across replicas and surviving restarts. Optionally a semantic cache, plus request coalescing so identical in-flight prompts share one provider call.
- **Storage:** Postgres for concurrent writers and multiple instances, with migrations (Alembic).
- **Routing:** LiteLLM Router, or the loop plus per-key health. Add cooldowns and circuit breakers so a key that keeps failing is skipped for N seconds instead of costing an attempt on every request. Weight keys by remaining quota.
- **UX and latency:** streaming responses (SSE), and a context window or summarisation so long sessions do not resend everything.
- **Ops:** auth and rate limiting on the API, structured logs and metrics (fallback rate, hit ratio, p95 latency), and tracing.

**14. How did you handle security?**
- Keys never leave the server: responses carry only `key_id`. A logging filter on every handler redacts configured keys, including inside tracebacks, and provider errors are logged as `Class(status=N)` only.
- All SQL is parameterized.
- CORS uses an explicit origin list with `allow_credentials=False`.
- Exception handlers guarantee JSON `{"detail": ...}` and never a stack trace or HTML page.
- Validation is strict.
- The backend container runs as non-root, and `.env` is git-ignored and Docker-ignored.
- One test checks that no key appears in responses, logs or the database.

**15. What is your testing strategy?**
There are 76 pytest tests across `test_api.py`, `test_cache.py` and `test_failover.py`. The key choice is *where* to mock: I wrap `litellm.acompletion` and inject LiteLLM's own `mock_response`. That way the real LiteLLM pipeline runs, including cache key computation, lookup, store and the `cache_hit` flag, without network access. Tests can also make a specific `api_key` raise any exception type. On top of that, `scripts/smoke_live.py` runs the same contract checks against a running backend with real keys, and the frontend was checked with headless-browser E2E tests against a mock backend.

**16. How does the frontend find the backend?**
In order: a runtime `/config.js` (written by the nginx entrypoint from `API_BASE_URL` in Docker), then the build-time `VITE_API_BASE_URL` (Vercel), then `http://localhost:8000`. That lets one Docker image point at any backend without a rebuild.

**17. Why is LiteLLM pinned to 1.97.0?**
On `>=1.98.1`, the cache-hit path imports `litellm.proxy.*` modules that need proxy-only extras, so a plain install crashes on every cache hit. Pinning exactly, with a comment in `requirements.txt`, keeps behaviour reproducible. Any upgrade should be gated on the cache tests and the smoke test.
