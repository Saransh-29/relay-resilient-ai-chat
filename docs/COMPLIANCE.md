# Compliance Checklist

This maps every requirement in `Lyftr_AI_Full_Stack_Assignment.pdf` (sections 2–7) to evidence in the repository. Paths are relative to the repo root.

**Legend**

- ✅ Verified in code, and by an automated test where one is cited. The backend suite gives `76 passed`.
- ⏳ Pending verification: Docker build and `make up`, the live deployment, the real-provider smoke test, and the submission artifacts.

## Section 2: System requirements

### Frontend (UI)

| Requirement | Evidence | Status |
|---|---|---|
| Clean UI showing a multi-turn conversation | `frontend/src/App.tsx:153-175`, `frontend/src/components/Messages.tsx:8-19,106-137` | ✅ |
| Per-reply resolution source | `frontend/src/components/Messages.tsx:56` | ✅ |
| Per-reply model | `frontend/src/components/Messages.tsx:61-63` | ✅ |
| Per-reply latency in ms | `frontend/src/components/Messages.tsx:68-70` (`{latency_ms} ms`) | ✅ |
| Per-request input and output tokens (never a running total) | `frontend/src/components/Messages.tsx:75-82` renders `metadata` from that response only. Backend: `backend/app/llm.py:86-93,165`; `backend/tests/test_cache.py:13` | ✅ |
| Optional system-prompt field | `frontend/src/components/DevPanel.tsx:138`, `frontend/src/lib/api.ts:214`; `backend/tests/test_api.py:170` | ✅ |

### Backend and LiteLLM gateway

| Requirement | Evidence | Status |
|---|---|---|
| Multi-turn state stored per session | `backend/app/chat_service.py:22-38`; `backend/tests/test_api.py:149` | ✅ |
| Key pool of at least 2 keys, ids `key_1..key_n` | `backend/app/config.py:89-100` | ✅ |
| Fail over on 429, quota or 5xx | `backend/app/llm.py:133-161`; `backend/tests/test_failover.py:28,111,171` | ✅ |
| The user never sees an unhandled exception | `backend/app/main.py:66-93`; `backend/tests/test_api.py:201,214,225` | ✅ |
| LiteLLM built-in cache (in-memory or disk) | `backend/app/llm.py:58-61,109`; `backend/tests/test_cache.py:105` | ✅ |
| `LLM_CACHE` / `LIVE_INFERENCE` reported correctly | `backend/app/llm.py:163-168`, `backend/app/chat_service.py:44`; `backend/tests/test_cache.py:13,32` | ✅ |
| Input and output tokens returned with every response | `backend/app/chat_service.py:43-53`, `backend/app/schemas.py:53-60`; `backend/tests/test_api.py:41` | ✅ |

### Storage (SQLite)

| Requirement | Evidence | Status |
|---|---|---|
| SQLite only, with no external services | `backend/app/db.py` (stdlib `sqlite3`), `backend/requirements.txt` | ✅ |
| File on a Docker volume, set via `DATABASE_URL` | `docker-compose.yml:15,22-23,38-39`, `backend/Dockerfile:24,37`, `backend/app/config.py:45-60,86-87` | ✅ code / ⏳ survives a container restart |
| Schema created automatically on startup | `backend/app/db.py:53-60`, `backend/app/main.py:33-37` | ✅ |
| `messages` table matches the minimal model | `backend/app/db.py:18-25` (plus an index at `:26` and a `sessions` table at `:27-32`) | ✅ |

### Deployment

| Requirement | Evidence | Status |
|---|---|---|
| Frontend deployed and public | `<FRONTEND_URL>`; config in `frontend/vercel.json` | ⏳ |
| Backend deployed and running | `<BACKEND_URL>`; `backend/Dockerfile:43-44` honours `$PORT` | ⏳ |
| Both tiers connected (CORS allows the frontend origin) | `backend/app/main.py:54-62`; `backend/tests/test_api.py:232` | ✅ code / ⏳ live |

## Section 3: Backend API contract

| Requirement | Evidence | Status |
|---|---|---|
| `GET /health` returns 200 `{status, keys_configured, cache_enabled}` once the DB is reachable and keys are loaded | `backend/app/main.py:97-112`; `backend/tests/test_api.py:25,31` | ✅ |
| `POST /chat` request fields and rules | `backend/app/schemas.py:14-50`; `backend/tests/test_api.py:66,74,98,107,118` | ✅ |
| `session_id` 1–128 characters; an unknown id starts a session | `backend/app/schemas.py:19,25-28`, `backend/app/db.py:106-146` (upsert) | ✅ |
| `message` 1–4000 characters after trimming | `backend/app/schemas.py:32-38`; `backend/tests/test_api.py:66,74,98` | ✅ |
| `system_prompt` optional and overrides the default for the session | `backend/app/chat_service.py:33`, `backend/app/db.py:126-127` (COALESCE); `backend/tests/test_api.py:170` | ✅ |
| Response shape: `session_id`, `reply`, and `metadata` with 7 fields | `backend/app/schemas.py:53-66`; `backend/tests/test_api.py:41` | ✅ |
| `key_id` null and `fallback_attempts` 0 on `LLM_CACHE`; never the key itself | `backend/app/llm.py:166-168`; `backend/tests/test_cache.py:13`, `backend/tests/test_failover.py:136` | ✅ |
| `GET /sessions/{id}/messages`: oldest first, no system prompt, metadata on assistant rows | `backend/app/main.py:128-135`, `backend/app/db.py:87-104`; `backend/tests/test_api.py:126,170` | ✅ |
| Every error is JSON with `detail`; no stack traces or HTML | `backend/app/main.py:66-93`; `backend/tests/test_api.py:214,225` | ✅ |
| 422 for missing or empty fields, messages over 4000, malformed JSON | `backend/app/main.py:66-76`; `backend/tests/test_api.py:98,112` | ✅ |
| 503 `{"detail": "all providers unavailable"}` | `backend/app/main.py:86-88`, `backend/app/llm.py:178-179`; `backend/tests/test_failover.py:40,119` | ✅ |
| 404 `{"detail": "session not found"}` | `backend/app/main.py:131-133`; `backend/tests/test_api.py:143` | ✅ |
| A failed request (422 or 503) is not added to history | `backend/app/chat_service.py:40-41` (writes only after success); `backend/tests/test_api.py:98`, `backend/tests/test_failover.py:40,119` | ✅ |
| Cache key = model + full message list | `backend/app/llm.py:115-127` (no session id is sent); `backend/tests/test_cache.py:40,47,63` | ✅ |
| The same first message in a new session gives `LLM_CACHE` | `backend/tests/test_cache.py:13,78` | ✅ |
| A different message never comes from cache | `backend/tests/test_cache.py:32` | ✅ |
| A cache hit returns the identical reply and the stored tokens | `backend/tests/test_cache.py:13` | ✅ |
| Multi-turn: the client sends only the new message | `frontend/src/lib/api.ts:212-220`; `backend/tests/test_api.py:149` | ✅ |
| Tokens are per request; two equal first messages give about the same `input_tokens` | `backend/app/llm.py:86-93` (provider `usage` for that call) | ✅ |
| `latency_ms` is an integer; a cache hit is faster than a live call | `backend/app/chat_service.py:48`; `backend/tests/test_cache.py:88` | ✅ |

## Section 4: Failover test hook

| Requirement | Evidence | Status |
|---|---|---|
| `X-Simulate-Failure` header with comma-separated `key_id=status` pairs, `*`, statuses 429/500/502/503 | `backend/app/simulation.py:7-56`; `backend/tests/test_failover.py:71,79` | ✅ |
| Affects only this request | `backend/app/main.py:120-126` (parsed per request and passed as an argument) | ✅ |
| Honoured only when `ENABLE_FAILURE_SIMULATION=true` | `backend/app/main.py:121`; `backend/tests/test_failover.py:61` | ✅ |
| `key_1=429` gives 200 with `key_2`; `key_1=500` gives 200 with `key_2` | `backend/app/llm.py:134-138`; `backend/tests/test_failover.py:28` (429/500/502/503) | ✅ |
| `*=429` gives 503 and adds nothing to history | `backend/tests/test_failover.py:40,49` | ✅ |
| A simulated request returns a real answer | `backend/app/llm.py:124-126` (a real call on the next key, with the cache read bypassed); `backend/tests/test_failover.py:88` | ✅ |
| Enabled on the deployed backend | Host environment variable | ⏳ |

## Section 5: Frontend contract

| `data-testid` / rule | Evidence | Status |
|---|---|---|
| `chat-input`, empty after sending | `frontend/src/components/Composer.tsx:77`, `frontend/src/App.tsx:90` | ✅ |
| `send-button`; Enter also sends | `frontend/src/components/Composer.tsx:90,30-35` | ✅ |
| `assistant-message` | `frontend/src/components/Messages.tsx:111` | ✅ |
| `meta-source`, `meta-model`, `meta-latency` | `frontend/src/components/Messages.tsx:56,61,68` | ✅ |
| `meta-input-tokens`, `meta-output-tokens` | `frontend/src/components/Messages.tsx:75,80` | ✅ |
| `system-prompt-input` | `frontend/src/components/DevPanel.tsx:138` | ✅ |
| A new session on each page load | `frontend/src/App.tsx:18-19` (not persisted) | ✅ |
| 422 and 503 shown as a readable message, never a blank screen | `frontend/src/lib/api.ts:104-125`, `frontend/src/App.tsx:71-76`, `frontend/src/components/Messages.tsx:148-188` | ✅ |
| The deployed frontend talks to the deployed backend | `frontend/src/lib/api.ts:44-53`, `frontend/docker/40-relay-config.sh` | ✅ code / ⏳ live |

## Section 6: Docker

| Requirement | Evidence | Status |
|---|---|---|
| `make up` gives backend `:8000` and frontend `:3000` | `Makefile:3-6`, `docker-compose.yml:20-21,32-33` | ⏳ (not yet run; the Docker daemon was unavailable) |
| Multi-stage backend Dockerfile with a small runtime image | `backend/Dockerfile` (`builder` → `python:3.12-slim` runtime; venv only, non-root) | ✅ file / ⏳ build |
| Multi-stage frontend Dockerfile | `frontend/Dockerfile:4,15` (`node:22-alpine` → `nginx:1.27-alpine`) | ✅ file / ⏳ build |
| Compose at the repo root with both services and a named volume at `/data` | `docker-compose.yml:3-39` | ✅ |
| Makefile with `up` and `down` | `Makefile:3-9` | ✅ |
| All configuration through environment variables | `backend/app/config.py:102-125`, `docker-compose.yml:11-19,30-31` | ✅ |

## Section 7: Deliverables

| Requirement | Evidence | Status |
|---|---|---|
| Repository structure: `/backend`, `/frontend`, compose, Makefile, `.env.example`, README | Repo root | ✅ |
| Backend tests | `backend/tests/` (76 tests) | ✅ |
| `LLM_API_KEYS`, `DATABASE_URL`, `ALLOWED_ORIGINS`, `ENABLE_FAILURE_SIMULATION` | `backend/app/config.py:111-118`, `.env.example` | ✅ |
| `.env.example` lists every variable with placeholders; no real keys in the repo | `.env.example`, `.gitignore`, `backend/.dockerignore` | ✅ |
| README with the 6 required headings | `README.md` | ✅ |
| Public GitHub repository | `<GITHUB_REPO_URL>` | ⏳ |
| Live URLs public without login | `<FRONTEND_URL>`, `<BACKEND_URL>` | ⏳ |
| 2–3 minute demo video with voice | Script in `docs/DEMO_SCRIPT.md` | ⏳ |
| Real-provider end-to-end check | `backend/scripts/smoke_live.py` | ⏳ (needs real keys) |

## Known limitations

- **The in-memory cache is per-process and lost on restart.** `CACHE_TYPE=local` lives inside one uvicorn worker. Running multiple replicas or restarting empties it. `CACHE_TYPE=disk` with `CACHE_DIR=/data/litellm-cache` persists it on the volume but is still single-host.
- **LiteLLM is pinned to `1.97.0`.** Versions `>=1.98.1` import proxy-only modules on the cache-hit path and crash a plain `pip install litellm` on every hit. Any upgrade must re-run `tests/test_cache.py` and the smoke test.
- **A Render free tier would have no persistent disk.** SQLite history (and a disk cache) would be wiped on every redeploy or spin-down, which breaks the "history survives restarts" requirement. The backend therefore needs a host with a volume at `/data` (for example Railway, Fly.io or a paid Render disk).
- **Provider free-tier quotas.** Real keys on free tiers can return 429 during a demo or evaluation. Failover covers one exhausted key, but if every key is exhausted the correct behaviour is a 503.
- **The cache-write yield is a workaround.** LiteLLM stores responses in a fire-and-forget task. The gateway yields to the event loop five times (`backend/app/llm.py:169-174`) so the write lands before returning. This depends on LiteLLM internals, and a slow cache backend could still miss an immediate repeat.
- **Other limitations:**
  - Identical concurrent requests both go live, because nothing coalesces them.
  - The full history is resent every turn, with no truncation window.
  - A dead `key_1` is retried on every request, because there is no cooldown or circuit breaker.
  - The API has no authentication or rate limiting.
  - With `ENABLE_FAILURE_SIMULATION=false`, the header is silently ignored rather than rejected.
