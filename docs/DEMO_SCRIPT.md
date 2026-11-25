# Demo Script: Relay (target 2:30)

**Before recording**

- Use the deployed app at `<FRONTEND_URL>`, with the backend at `<BACKEND_URL>` running `ENABLE_FAILURE_SIMULATION=true` and two real keys. Use a desktop-width window, where Dev Tools is open by default at 1024 px and wider.
- Use the exact prompts below. The first message must not have been sent since the last backend restart; otherwise step 2 is already a cache hit. If needed, add a unique suffix such as `(take 3)` to both the step 2 and step 3 prompts.
- Keep a terminal open with `BASE=<BACKEND_URL>` set for the closing shot of the 422 and 404 errors.
- Badge colours: blue = `LIVE_INFERENCE`, green = `LLM_CACHE`, amber = `fallback ×N`, red card = error.

| Time | Do (click / type) | Say |
|---|---|---|
| **0:00–0:10** | Show `<FRONTEND_URL>`. Point at the green **Connected · keys 2 · cache on** pill. | "This is Relay, a resilient AI chat. It has a React frontend on `<frontend host>` and a FastAPI and LiteLLM backend on `<backend host>`, with SQLite storage." |
| **0:10–0:20** | **Dev Tools → Backend health → `GET /health`**. Show the JSON. | "Endpoint one is health. It reports status ok, two keys in the pool and the cache enabled." |
| **0:20–0:40** | Type `What is the capital of France?` and press Enter. Point at the meta row. | "Endpoint two is chat. The input clears, and each reply carries its own metadata: LIVE_INFERENCE, the model, the server-measured latency, and the input and output tokens for this request only, not a running total. Key 1 answered with no fallbacks." |
| **0:40–1:00** | Click **New Chat**. Send the same `What is the capital of France?`. | "New Chat starts a new session ID. The same first message now gives a green LLM_CACHE badge from LiteLLM's built-in cache. The reply and token counts are identical, the key is null, and latency dropped from about *N* hundred milliseconds to a few milliseconds. The cache key is the model plus the full message list, so a different message never comes from cache." |
| **1:00–1:15** | Send `My name is Ada. Remember it.`, then `What is my name?` | "Multi-turn memory: the client sends only the new message. The backend rebuilds the system prompt and the history from SQLite, so it remembers Ada." |
| **1:15–1:25** | **Dev Tools → Session → `GET /sessions/{id}/messages`**. Scroll the JSON. | "Endpoint three is history. It returns user and assistant messages oldest first, with metadata on assistant rows and no system prompt. Note: six messages." |
| **1:25–1:45** | **Failure simulation:** tick *Send X-Simulate-Failure header*, choose **`key_1=429`**. Send `Name one primary color.` | "Now failover. The X-Simulate-Failure header makes key 1 behave as if the provider returned 429, for this request only. Simulated requests skip the cache read, so the failover really runs. The answer is still a real reply, now from key 2, with an amber 'fallback ×1' badge. A 500 on key 1 behaves the same way." |
| **1:45–2:05** | Choose **`*=429`**. Send `This one should fail.` Show the red card. Then click **`GET /sessions/{id}/messages`** again. | "With every key rate-limited, the backend returns a clean 503, 'all providers unavailable'. The UI shows a readable error with Retry and Edit buttons, not a blank screen. History now has eight messages. The key 2 exchange was stored, but the failed request was not, because failed requests are never written." |
| **2:05–2:15** | Untick simulation. Click **New Chat**. Send `What is my name?` | "Sessions are isolated. A fresh session has no idea who I am." |
| **2:15–2:25** | Terminal: `curl -s -w '\n%{http_code}\n' $BASE/sessions/nope/messages`, then `curl -s -w '\n%{http_code}\n' -X POST $BASE/chat -H 'Content-Type: application/json' -d '{"session_id":"x","message":"   "}'` | "Errors are always JSON with a detail field: 404 'session not found' for an unknown session, and 422 for a blank message." |
| **2:25–2:30** | Back to the app. | "Key failover, response caching, per-request tokens and SQLite sessions all run through `make up` locally and are deployed live. Thanks." |

**Fallbacks if something goes wrong on camera**

- **Step 2 is already `LLM_CACHE`:** say "this message was cached earlier", then rerun the step with a unique suffix.
- **A real provider 429 during the take:** the amber fallback badge appears without any simulation. Point it out, because it is the same mechanism working live.
- **Under time pressure:** drop the `key_1=500` sentence and the terminal shot. The Dev Tools history call already demonstrates the third endpoint.
