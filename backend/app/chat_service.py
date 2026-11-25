"""Chat orchestration: build the prompt, call the gateway, persist the exchange."""

from __future__ import annotations

import time
from typing import Any

from starlette.concurrency import run_in_threadpool

from .config import Settings
from .db import Database
from .llm import LLMGateway
from .schemas import ChatRequest


class ChatService:
    def __init__(self, settings: Settings, db: Database, gateway: LLMGateway):
        self.settings = settings
        self.db = db
        self.gateway = gateway

    def _load_context(self, session_id: str) -> tuple[str | None, list[dict[str, str]]]:
        session = self.db.get_session(session_id)
        stored_prompt = session.get("system_prompt") if session else None
        history = self.db.get_history(session_id) if session else []
        # Only role/content go to the LLM; metadata stays server-side.
        return stored_prompt, [{"role": m["role"], "content": m["content"]} for m in history]

    async def handle(self, body: ChatRequest, simulation: dict[str, int]) -> dict[str, Any]:
        started = time.perf_counter()
        stored_prompt, history = await run_in_threadpool(self._load_context, body.session_id)

        system_prompt = body.system_prompt or stored_prompt or self.settings.default_system_prompt
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.extend(history)
        messages.append({"role": "user", "content": body.message})

        # Raises AllProvidersUnavailable -> 503 before anything is written.
        result = await self.gateway.complete(messages, simulation)

        metadata = {
            "resolution_source": "LLM_CACHE" if result.cache_hit else "LIVE_INFERENCE",
            "model": result.model,
            # Server-side time for context load + LLM resolution. Measured before the
            # DB write so the stored and returned metadata are identical.
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "key_id": result.key_id,
            "fallback_attempts": result.fallback_attempts,
        }
        # Persist the session upsert + user/assistant pair in one transaction.
        await run_in_threadpool(
            self.db.save_exchange,
            body.session_id,
            body.system_prompt,
            body.message,
            result.reply,
            dict(metadata),
        )
        return {"session_id": body.session_id, "reply": result.reply, "metadata": metadata}
