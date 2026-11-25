# Relay: Resilient AI Chat

A full-stack LLM chatbot with **API-key failover**, **LiteLLM response caching**, **per-request token tracking** and **SQLite-backed multi-turn sessions**. It is built for the Lyftr AI full-stack assignment.

- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS v4, served by nginx in Docker
- **Backend:** Python 3.12 + FastAPI + LiteLLM (`litellm==1.97.0`) + SQLite (stdlib `sqlite3`)
- **Infra:** multi-stage Dockerfiles, `docker-compose.yml` with a named `/data` volume, and a `Makefile`

```
 Browser (React SPA, :3000)
   |  JSON over HTTPS, CORS (ALLOWED_ORIGINS)
   v
 FastAPI (:8000)  GET /health · POST /chat · GET /sessions/{id}/messages
   |- Pydantic validation (422) ------------------------------ nothing stored
   |- ChatService: system prompt + SQLite history + new message
   |- LLMGateway: ordered failover loop key_1 -> key_2 -> ... -> key_n
   |     each attempt = litellm.acompletion(api_key=k, num_retries=0, timeout=T)
   |     X-Simulate-Failure injects a 429/5xx per key, for this request only
   |     every key failed -> 503 {"detail": "all providers unavailable"}
   |- LiteLLM built-in Cache (type="local" in-memory, or "disk")
   |     key = model + messages (never the api_key or the session_id)
   '- SQLite (DATABASE_URL, /data/app.db on a Docker volume)
         sessions + messages; the user+assistant pair is written in ONE transaction after success
```

---

## 1. Live URLs

| Tier | URL |
|---|---|
| Frontend | `<FRONTEND_URL>` |
| Backend | `<BACKEND_URL>` (try `<BACKEND_URL>/health`) |
| Repository | `<GITHUB_REPO_URL>` |
| Demo video | `<DEMO_VIDEO_URL>` |

> **TODO:** fill these in after deployment. The planned hosts are Vercel for the frontend and Railway for the backend, with a volume mounted at `/data`. Nothing in the code is host-specific, so any host that runs a Dockerfile, honours `$PORT` and offers a persistent disk will work.

**Deployment settings (any host)**

- **Backend:** build `backend/Dockerfile`. The container listens on `$PORT` (default 8000). Mount a persistent volume at `/data`. Set `LLM_API_KEYS` (at least 2 keys), `DATABASE_URL=sqlite:////data/app.db`, `ALLOWED_ORIGINS=<FRONTEND_URL>` and `ENABLE_FAILURE_SIMULATION=true`.
- **Frontend (static host, e.g. Vercel):** use `frontend/` as the project root, with build `npm run build` and output `dist` (already in `frontend/vercel.json`). Set `VITE_API_BASE_URL=<BACKEND_URL>` at build time.
- **Frontend (Docker host):** build `frontend/Dockerfile` and set `API_BASE_URL=<BACKEND_URL>` at runtime. The nginx entrypoint writes it to `/config.js`, so you do not need to rebuild.

---

## 2. Run locally

### With Docker (recommended)

Prerequisites: Docker with Compose v2.24 or later (needed for the optional `env_file` syntax).

```bash
cp .env.example .env          # then put two real keys in LLM_API_KEYS
make up                       # docker compose up -d --build
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000/health

```bash
make down                     # stop; the SQLite volume (relay-data) is kept
make clean                    # stop AND delete the volume
make logs                     # follow logs
```

**Windows without `make`:** run the underlying commands directly: `docker compose up -d --build` and `docker compose down`.

SQLite lives on the named volume `relay-data`, mounted at `/data`, so history survives `make down` / `make up`.

### Without Docker

**Backend** (Python 3.12+; 3.13 also works):

```bash
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt  # runtime deps + pytest

# Local overrides. Real environment variables win over .env files.
export LLM_API_KEYS="key-one,key-two"
export DATABASE_URL="sqlite:///./data/app.db"     # see the note below
export ALLOWED_ORIGINS="http://localhost:5173,http://localhost:3000"
export ENABLE_FAILURE_SIMULATION=true
export LITELLM_LOCAL_MODEL_COST_MAP=True          # use LiteLLM's bundled cost map, no network fetch at import

uvicorn app.main:app --reload --port 8000
```

> **DATABASE_URL note:** the backend also reads `backend/.env` and the repo-root `.env`. The value in `.env.example`, `sqlite:////data/app.db`, is an absolute container path. On Windows it resolves to `<drive>:\data\app.db`. For a local run, override it with `sqlite:///./data/app.db`, which is relative to `backend/`. The parent directory is created automatically, and the schema is created on startup.

**Frontend** (Node 22):

```bash
cd frontend
npm ci
VITE_API_BASE_URL=http://localhost:8000 npm run dev   # http://localhost:5173
```

In PowerShell, run `$env:VITE_API_BASE_URL="http://localhost:8000"; npm run dev`. If the variable is unset, the frontend falls back to `http://localhost:8000`.

### Environment variables

| Variable | Used by | Default (code) | Meaning |
|---|---|---|---|
| `LLM_API_KEYS` | backend | *(empty: `/health` returns 503)* | Comma-separated key pool, at least 2 keys. Ids are `key_1`, `key_2`, ... in this order. |
| `LLM_MODEL` | backend | `gemini/gemini-3.5-flash-lite` | LiteLLM model name used by every key. |
| `LLM_MODELS` | backend | *(empty)* | Optional: one model per key, by position, to mix providers (for example `gemini/gemini-3.5-flash-lite,groq/openai/gpt-oss-120b`). Missing positions fall back to `LLM_MODEL`. |
| `DATABASE_URL` | backend | `sqlite:///./data/app.db` | SQLite location. In Docker it is `sqlite:////data/app.db`. |
| `ALLOWED_ORIGINS` | backend | `*` if unset | Comma-separated CORS origins. Compose defaults to `http://localhost:3000`. |
| `ENABLE_FAILURE_SIMULATION` | backend | `false` | `true` enables the `X-Simulate-Failure` hook. Compose and `.env.example` set `true`. |
| `DEFAULT_SYSTEM_PROMPT` | backend | `You are a helpful, concise assistant.` | Used when a session has no system prompt. |
| `CACHE_TYPE` | backend | `local` | LiteLLM cache backend: `local` (in-memory) or `disk`. |
| `CACHE_DIR` | backend | `./data/llm_cache` | Disk-cache directory (only when `CACHE_TYPE=disk`). |
| `LLM_TIMEOUT_SECONDS` | backend | `30` | Per-key provider timeout. |
| `LOG_LEVEL` | backend | `INFO` | Log level. |
| `PORT` | backend image | `8000` | Port uvicorn listens on (Railway and Render inject it). |
| `API_BASE_URL` | frontend image (runtime) | `http://localhost:8000` | Written into `/config.js` at container start. |
| `VITE_API_BASE_URL` | frontend build / dev | *(empty)* | Build-time fallback for the backend URL. |

The frontend resolves the backend URL in this order: runtime `window.__RELAY_CONFIG__.API_BASE_URL` (from `/config.js`), then `VITE_API_BASE_URL`, then `http://localhost:8000` (`frontend/src/lib/api.ts`, `resolveApiBase`).

---

## 3. Design decisions

### Key fallback: an explicit ordered loop over LiteLLM

`LLMGateway.complete` (`backend/app/llm.py`) iterates `key_1..key_n` in order. Each attempt is one `litellm.acompletion(model=..., messages=..., api_key=<that key>, num_retries=0, timeout=LLM_TIMEOUT_SECONDS, caching=True)`.

- **Any exception fails over to the next key.** That covers 429, quota exhaustion (`RateLimitError`), 5xx, timeouts, connection errors, authentication errors and unexpected errors. The tests cover each case.
- **An empty reply counts as a failure.** It is converted into a 502 `APIError`. Because LiteLLM may already have cached that empty answer, the remaining keys are forced to bypass the cache read so they cannot pick it up.
- **If every key fails,** the gateway raises `AllProvidersUnavailable`, which maps to `503 {"detail": "all providers unavailable"}`. Nothing is written to SQLite.
- `key_id` is the id of the key that answered, and `fallback_attempts` counts the keys that failed before it. Both are exact because the loop owns the iteration.
- **Why not LiteLLM's Router?** The contract needs exact per-request `key_id` and `fallback_attempts`, plus per-key failure injection for one request only. A plain loop makes both trivial and keeps the behaviour easy to audit. LiteLLM still does every provider call, error mapping and caching. `num_retries=0` stops LiteLLM retrying the same failing key, which would hide failover and add latency.
- **`X-Simulate-Failure`** (`backend/app/simulation.py`): the backend parses `key_id=status` pairs (statuses `429|500|502|503`, with `*` for every key; a specific entry wins over `*`). A malformed header returns 422. For a listed key, the gateway raises the matching LiteLLM exception (`RateLimitError`, `InternalServerError`, `BadGatewayError` or `ServiceUnavailableError`) instead of calling the provider. The header is honoured only when `ENABLE_FAILURE_SIMULATION=true`; otherwise it is ignored.

### Caching: LiteLLM's built-in cache

- `litellm.cache = Cache(type="local")`, or `Cache(type="disk", disk_cache_dir=CACHE_DIR)`.
- **Cache key = model + messages.** LiteLLM's `Cache.get_cache_key` hashes only recognised LLM API params. `api_key`, `timeout`, `num_retries` and `caching` are not in that set, and `session_id` is never sent to the LLM. So the same system prompt, history and message on the same model hits the cache whichever key produced the answer. Any difference in the message list (another message, other history or another system prompt) is a miss. `tests/test_cache.py` checks this both at the key level and end to end.
- **Hit detection:** `response._hidden_params["cache_hit"]`. A hit returns the identical reply and the usage stored with the cached response, with `key_id: null` and `fallback_attempts: 0`.
- **Simulated requests bypass the cache read.** When `X-Simulate-Failure` is active, every attempt passes `cache={"no-cache": True}`. This skips the lookup but still stores the fresh answer. Without it, a demo of `key_1=429` on a message that is already cached would return `LLM_CACHE` and never touch the failover path. The trade-off is that a simulated request always costs a real provider call.
- **Cache-write race:** LiteLLM writes the cache in a fire-and-forget asyncio task. After a live answer, the gateway yields to the event loop five times (`await asyncio.sleep(0)`) so the write lands before the response returns. An identical request sent right afterwards then hits the cache.

### SQLite session storage

- Two tables, created on startup with `CREATE TABLE IF NOT EXISTS`:
  - `messages`: exactly the contract's schema, plus an index on `(session_id, id)`.
  - `sessions`: `session_id` primary key, `system_prompt`, `created_at` and `updated_at`.
- **Atomic, success-only writes:** after the LLM succeeds, a single `BEGIN IMMEDIATE` transaction upserts the session row and inserts the user and assistant rows. A 422 or 503 never writes, and a failed write rolls back.
- **System prompt:** an explicit `system_prompt` overrides the stored one and persists (`COALESCE` on upsert). The resolution order is request, then stored, then `DEFAULT_SYSTEM_PROMPT`. The system prompt is sent to the LLM but never stored as a message, so the history endpoint excludes it.
- **History:** the client sends only the new message. The server rebuilds `[system] + history + [user]`, sending only `role` and `content` to the LLM. `GET /sessions/{id}/messages` returns oldest first, and assistant rows include their stored metadata.
- WAL mode, a 10 s busy timeout, a fresh connection per operation, and blocking calls run in a threadpool.

### Latency measurement

`latency_ms` is measured server-side with `time.perf_counter()`. The clock starts when `ChatService.handle` begins and stops once the LLM result is resolved, before the database write. It therefore covers loading context from SQLite plus cache lookup or provider calls, including any failed keys. The same value is returned and stored. A cache hit is typically a few milliseconds; a live call takes hundreds of milliseconds or more.

### Security

- **Keys are never exposed.** Responses only carry `key_id`. Every log handler has a redaction filter that replaces any configured key, including inside tracebacks, with `[REDACTED]`. Provider errors are logged as `ExceptionClass(status=N)` only, never the provider's message. A test checks that neither responses, logs nor SQLite contain a key.
- **Parameterized SQL only** (`?` placeholders); no string-built queries.
- **CORS** is restricted to `ALLOWED_ORIGINS`, with `allow_credentials=False`, methods `GET`/`POST`/`OPTIONS`, and `X-Simulate-Failure` an allowed header.
- **No stack traces:** handlers for validation errors, HTTP errors, `AllProvidersUnavailable` and a catch-all `Exception` always return JSON with `detail`. The catch-all returns `500 {"detail": "internal server error"}`.
- **Strict validation:** Pydantic `strict=True`, so `123` is not coerced to `"123"`. Messages are trimmed and must be 1–4000 characters; `session_id` must be 1–128 characters and not blank.
- **Containers:** the backend runs as a non-root user (uid 10001). Secrets come only from the environment; `.env` is git-ignored and Docker-ignored.

### Trade-offs

| Decision | Benefit | Cost |
|---|---|---|
| Explicit loop instead of Router | Exact `key_id`/`fallback_attempts`, simple per-key simulation | No built-in cooldowns or circuit breaking; a dead `key_1` is retried on every request |
| In-memory `local` cache | Zero dependencies, fastest hits | Per-process and lost on restart (`CACHE_TYPE=disk` on `/data` mitigates this) |
| Cache bypass on simulation | Failover demos are real | Simulated requests always hit a provider |
| Full history sent each turn | Exact multi-turn memory | Prompt size grows with the session; there is no truncation window |
| SQLite | Assignment constraint, no external services, durable on a volume | Single writer, one backend instance |

---

## 4. Verification

The commands below use bash. On Windows, use Git Bash or WSL. If you are in PowerShell, call `curl.exe`, not the `curl` alias for `Invoke-WebRequest`. Windows PowerShell 5.1 also strips inner double quotes from arguments, so put the JSON body in a file and pass `-d "@body.json"`.

```bash
BASE=http://localhost:8000        # or <BACKEND_URL>
J='Content-Type: application/json'
```

**Health**

```bash
curl -s $BASE/health
# {"status":"ok","keys_configured":2,"cache_enabled":true}
```

**Live chat:** check `resolution_source`, `key_id` and the token counts.

```bash
curl -s -X POST $BASE/chat -H "$J" \
  -d '{"session_id":"verify-a","message":"What is the capital of France?"}'
# "resolution_source":"LIVE_INFERENCE", "key_id":"key_1", "fallback_attempts":0, input/output tokens > 0
```

**Cache hit:** send the same first message in a new session.

```bash
curl -s -X POST $BASE/chat -H "$J" \
  -d '{"session_id":"verify-b","message":"What is the capital of France?"}'
# "resolution_source":"LLM_CACHE", identical reply, same input/output tokens, "key_id":null,
# "fallback_attempts":0, much lower latency_ms
```

A different message (for example `...capital of Spain?`) returns `LIVE_INFERENCE`.

**Failover:** `key_1=429` falls over to `key_2`.

```bash
curl -s -X POST $BASE/chat -H "$J" -H 'X-Simulate-Failure: key_1=429' \
  -d '{"session_id":"verify-c","message":"Name one primary color."}'
# 200, "key_id":"key_2", "fallback_attempts":1, "resolution_source":"LIVE_INFERENCE"
```

**Failover:** `key_1=500` falls over to `key_2`.

```bash
curl -s -X POST $BASE/chat -H "$J" -H 'X-Simulate-Failure: key_1=500' \
  -d '{"session_id":"verify-c","message":"And another one?"}'
# 200, "key_id":"key_2", "fallback_attempts":1
```

**Every key fails:** `503`, and the history is unchanged.

```bash
curl -s $BASE/sessions/verify-a/messages            # note: 2 messages
curl -s -w '\nHTTP %{http_code}\n' -X POST $BASE/chat -H "$J" -H 'X-Simulate-Failure: *=429' \
  -d '{"session_id":"verify-a","message":"This should fail"}'
# {"detail":"all providers unavailable"}  HTTP 503
curl -s $BASE/sessions/verify-a/messages            # still the same 2 messages
```

**422 validation:** none of these requests is stored.

```bash
# blank message (trimmed to empty)
curl -s -w '\nHTTP %{http_code}\n' -X POST $BASE/chat -H "$J" -d '{"session_id":"x","message":"   "}'
# missing session_id
curl -s -w '\nHTTP %{http_code}\n' -X POST $BASE/chat -H "$J" -d '{"message":"hi"}'
# message over 4000 characters
LONG=$(printf 'a%.0s' $(seq 1 4001))
curl -s -w '\nHTTP %{http_code}\n' -X POST $BASE/chat -H "$J" -d "{\"session_id\":\"x\",\"message\":\"$LONG\"}"
# malformed JSON
curl -s -w '\nHTTP %{http_code}\n' -X POST $BASE/chat -H "$J" -d '{"session_id": "x", "message": '
# malformed simulation header (when simulation is enabled)
curl -s -w '\nHTTP %{http_code}\n' -X POST $BASE/chat -H "$J" -H 'X-Simulate-Failure: key_1=418' \
  -d '{"session_id":"x","message":"hi"}'
```

**404 for an unknown session**

```bash
curl -s -w '\nHTTP %{http_code}\n' $BASE/sessions/does-not-exist/messages
# {"detail":"session not found"}  HTTP 404
```

**History and multi-turn memory**

```bash
curl -s -X POST $BASE/chat -H "$J" -d '{"session_id":"verify-m","message":"My name is Ada. Remember it."}'
curl -s -X POST $BASE/chat -H "$J" -d '{"session_id":"verify-m","message":"What is my name?"}'   # mentions Ada
curl -s $BASE/sessions/verify-m/messages
# user, assistant, user, assistant (oldest first); assistant rows carry metadata; no system prompt
```

### In the UI

1. Open http://localhost:3000 (or `<FRONTEND_URL>`). The header pill shows **Connected · keys 2 · cache on** (green).
2. Send `What is the capital of France?`. Under the reply, the meta row shows a **blue `LIVE_INFERENCE`** badge, the model, latency (`… ms`), `in N / out M` tokens and `key_1`. The input box clears after sending.
3. Click **New Chat** (a new `session_id`) and send the same message. The badge turns **green `LLM_CACHE`**, latency drops, and the reply and tokens are identical, with key `null`.
4. Open **Dev Tools** (top right) → **Failure simulation**. Tick *Send X-Simulate-Failure header*, pick `key_1=429` and send any message. Expect `key_2` and an **amber `fallback ×1`** badge. The header shows a **Sim** pill while simulation is active.
5. Pick `*=429` and send. A red **Request failed · HTTP 503** card shows *"All providers are unavailable right now…"* with Retry and Edit message buttons. Then go to **Dev Tools → Session → GET /sessions/{id}/messages**: the failed message is not stored.
6. **Dev Tools → System prompt** sets `system_prompt` for the session. **Last response metadata** shows the raw JSON of the last reply.
7. Click **New Chat** and ask `What is my name?`. The new session has no memory of the previous one.

### Automated tests

```bash
cd backend && python -m pytest -q        # or: make test   ->  76 passed
```

The suite mocks the provider using LiteLLM's own `mock_response`, so the real LiteLLM cache pipeline (key computation, lookup, store and the `cache_hit` flag) runs without network access. Coverage includes the API contract, the 422 matrix, 404, history order and shape, multi-turn, session isolation, system-prompt persistence, atomic writes, cache hit and miss rules, cache-key independence from `api_key`, hits being faster than live calls, the disk cache, failover on every simulated status, failover on real exception types, the 503 path storing nothing, CORS, and key redaction.

### Live smoke test (real provider keys)

With the backend running using two real keys and `ENABLE_FAILURE_SIMULATION=true`:

```bash
cd backend && python scripts/smoke_live.py http://localhost:8000     # or: make smoke BASE_URL=<BACKEND_URL>
```

The script uses the standard library only and exits non-zero on any failure. It checks health, a live call, a cache hit (identical reply and tokens, `key_id` null, faster), `key_1=429` → `key_2`, `*=429` → 503 with nothing stored, a 4-message history, the 404 and the 422s.

---

## 5. Setup Used

- **Editor:** Antigravity, on Windows 11.
- **AI tooling:** Claude Code running Claude Opus as a lead-architect agent. It coordinated specialized subagents (backend, frontend, documentation, plus QA and security review roles), each owning a defined set of files. The lead reviewed and re-ran their output, for example re-running the backend test suite and fixing the empty-reply cache issue.
- **Runtime:** Python 3.12 (Docker; 3.13 locally), Node 22, Docker Compose.

---

## 6. Bonus features

| Feature | Why |
|---|---|
| **Dev Tools panel**: failure-simulation presets (`key_1=429`, `key_1=500`, `key_1=429,key_2=500`, `*=429`, custom), a `GET /health` button, a session history inspector and the last-response JSON | Every endpoint and the failover path can be shown from the browser, with no curl needed |
| **Optional system prompt** (`data-testid="system-prompt-input"`), persisted per session | The PDF lists it as optional |
| **`key_id` and an amber `fallback ×N` badge** in each meta row | Failover is visible per message, not only in the API |
| **Readable error cards with Retry / Edit message** | A 422, 503, network or timeout error never blanks the screen, and the user can recover in one click |
| **Health pill** polling `/health` every 15 s (only while the tab is visible) | Shows at a glance whether the backend is reachable and configured |
| **Mixed-provider key pool** (`LLM_MODELS`) | Failover can cross providers (for example Gemini → Groq), not only keys |
| **Disk cache option** (`CACHE_TYPE=disk`, `CACHE_DIR` on `/data`) | The cache can survive restarts if wanted |
| **Key redaction logging filter** and sanitized error logs | Defence in depth against secrets leaking through third-party exception messages |
| **Runtime `/config.js`** for the frontend image | One image runs against any backend URL without rebuilding |
| **Hardening:** non-root backend container, Docker `HEALTHCHECK`s on both images, nginx security headers, immutable asset caching | Production hygiene at no extra cost |
| **`scripts/smoke_live.py`** and extra Makefile targets (`logs`, `ps`, `clean`, `test`, `smoke`) | End-to-end checks against real providers or the deployed URL |
| **Markdown rendering** (GFM) with a copy button on replies | Code answers stay readable |
