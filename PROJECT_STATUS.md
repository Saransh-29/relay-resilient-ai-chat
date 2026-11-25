# PROJECT_STATUS — Relay (Resilient AI Chat)

Lead Architect: single point of contact. Source of truth: `Lyftr_AI_Full_Stack_Assignment.pdf` (repo root).

## Architecture
```
Browser (React/Vite SPA, :3000)  --JSON/CORS-->  FastAPI (:8000)
                                                   |- validation (Pydantic)
                                                   |- ChatService: build messages (system + SQLite history + new msg)
                                                   |- KeyPool failover loop: key_1..key_n, litellm.acompletion(api_key=..., num_retries=0)
                                                   |     X-Simulate-Failure injected per key, request-scoped
                                                   |- LiteLLM built-in Cache (in-memory "local"; key = model + messages)
                                                   '- SQLite (/data/app.db): sessions + messages, pair written atomically
```

## File ownership
| Area | Owner | Paths |
|---|---|---|
| Backend API, LLM gateway, caching, DB, tests, backend Dockerfile | Backend Agent | `backend/**` |
| Frontend app, UI/UX, frontend Dockerfile + nginx | Frontend Agent | `frontend/**` |
| Root infra, status, README, demo script, compliance | Lead Architect (+ DevOps/Docs/QA/Security roles) | `docker-compose.yml`, `Makefile`, `.env.example`, `README.md`, `docs/**`, `PROJECT_STATUS.md` |

## Key decisions
1. **Failover is an explicit ordered loop over the key pool**, with LiteLLM making each provider call (`num_retries=0`). This makes `key_id` and `fallback_attempts` exact and lets simulated failures be injected per key. Every keyed attempt is bounded by a timeout.
2. **Caching uses LiteLLM's `litellm.cache = Cache(type="local")`** (configurable to `disk`). The cache key is model + messages, so it must NOT include the api_key or session_id; this is verified with a test.
3. **Simulated failure requests bypass cache reads** (`cache={"no-cache": True}`) so the failover path really runs. This is documented in the README.
4. **Cache hits report** `key_id=null`, `fallback_attempts=0`, and the usage stored with the cached response.
5. **Sessions:** a `sessions` table stores the system prompt (an explicit system_prompt overrides and persists). The session row and the user+assistant pair are written in one transaction, and only after LLM success.
6. **Frontend API URL:** runtime `/config.js` (Docker; nginx entrypoint renders from env) → `VITE_API_BASE_URL` (Vercel build) → `http://localhost:8000`.

## Tasks
| # | Task | Owner | Status |
|---|---|---|---|
| 1 | Read PDF, architecture, ownership | Lead | done |
| 2 | Backend implementation + pytest | Backend Agent | done, Lead-reviewed (empty-reply cache fix applied) |
| 3 | Frontend implementation | Frontend Agent | done, Lead-reviewed (docker build pending daemon) |
| 4 | Root docker-compose / Makefile / .env.example | Lead/DevOps | done (unverified until Docker runs) |
| 5 | Real-provider integration test | QA | done 18/18 |
| 6 | `make up` Docker verification | DevOps | done |
| 7 | Security review | Security | secret scan clean; PDF git-ignored |
| 8 | GitHub publish | DevOps | blocked: user permission/account |
| 9 | Deploy backend + frontend | DevOps | blocked: user permission/accounts |
| 10 | README, demo script, compliance checklist, interview prep | Docs Agent | done (URLs placeholders) |

## Test results
- Frontend: `npm run build` 0 type errors (JS 112 kB gzip); `npm run lint` clean; `npm audit --omit=dev` 0 vulns; headless-Edge E2E vs mock backend passed (testids, input clears, 422/503/non-JSON errors readable, New Chat).
- Backend: `77 passed in 8.08s` (incl. new empty-reply cache-poison test) (pytest, Lead re-run after fix). litellm pinned 1.97.0 (>=1.98.1 imports proxy-only deps on cache hit). Cache key verified api_key-independent (source + test).
- Docker: `make up` OK (frontend :3000 200, backend :8000 healthy, CORS for localhost:3000 incl. X-Simulate-Failure). History + system prompt survived `docker compose restart backend` (SQLite on named volume).
- Real-provider smoke (backend image on :8001, gemini/gemini-3.5-flash-lite + groq/openai/gpt-oss-120b): 18/18 PASS. Live 5449ms vs cache 5ms; key_1=429 -> key_2; *=429 -> 503 nothing stored. 0 key occurrences in logs.

## Blockers
- GitHub account / repo creation (user permission; `gh` CLI not installed)
- Hosting accounts + deploy permission (user)
