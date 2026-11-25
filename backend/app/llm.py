"""LLM gateway: ordered key-pool failover over LiteLLM, with LiteLLM's built-in cache.

Design
------
* Every provider call goes through ``litellm.acompletion`` with ``num_retries=0`` and a
  timeout, so the gateway controls failover explicitly and ``key_id`` /
  ``fallback_attempts`` are exact.
* Caching uses LiteLLM's own ``litellm.cache = Cache(type="local" | "disk")``.
  The cache key is computed by ``Cache.get_cache_key`` from the kwargs that are known
  LLM API params (``ModelParamHelper.get_all_llm_api_params()``): here that is
  ``model`` + ``messages`` (+ fixed params). ``api_key``, ``timeout``, ``num_retries``,
  ``caching``, ``mock_response`` are not part of that set, so the key is independent of
  which pool key answered and of the session id (which is never sent to the LLM).
  This is asserted by tests (tests/test_cache.py).
* A cache hit is detected via ``response._hidden_params["cache_hit"]``.
* Failure simulation: a simulated key raises the matching LiteLLM exception without
  calling the provider. When simulation is active, the cache read is bypassed with
  LiteLLM's dynamic cache control ``cache={"no-cache": True}`` so failover really runs;
  the successful answer is still written to the cache.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

import litellm
from litellm.caching.caching import Cache

from .config import KeyEntry, Settings
from .simulation import simulated_status_for

logger = logging.getLogger("relay.llm")

litellm.suppress_debug_info = True
litellm.set_verbose = False  # type: ignore[attr-defined]
litellm.drop_params = True


class AllProvidersUnavailable(Exception):
    """Every key in the pool failed for this request."""


@dataclass
class LLMResult:
    reply: str
    model: str
    input_tokens: int
    output_tokens: int
    key_id: Optional[str]
    fallback_attempts: int
    cache_hit: bool


def build_cache(settings: Settings) -> Cache:
    if settings.cache_type == "disk":
        return Cache(type="disk", disk_cache_dir=settings.cache_dir)
    return Cache(type="local")


def simulated_exception(status: int, key: KeyEntry) -> Exception:
    """Build the LiteLLM exception a provider failure with ``status`` would raise."""
    provider = key.model.split("/", 1)[0] if "/" in key.model else "unknown"
    message = f"Simulated HTTP {status} for {key.key_id} (X-Simulate-Failure)"
    if status == 429:
        return litellm.RateLimitError(message=message, llm_provider=provider, model=key.model)
    if status == 500:
        return litellm.InternalServerError(message=message, llm_provider=provider, model=key.model)
    if status == 502:
        return litellm.BadGatewayError(message=message, llm_provider=provider, model=key.model)
    if status == 503:
        return litellm.ServiceUnavailableError(message=message, llm_provider=provider, model=key.model)
    raise ValueError(f"unsupported simulated status {status}")


def describe_error(exc: BaseException) -> str:
    """Sanitised one-line description: exception class + HTTP status. Never the message,
    which could echo request details or credentials."""
    status = getattr(exc, "status_code", None)
    return f"{type(exc).__name__}(status={status})" if status is not None else type(exc).__name__


def _usage_tokens(response: Any) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return 0, 0
    get = usage.get if isinstance(usage, dict) else lambda k, d=None: getattr(usage, k, d)
    return int(get("prompt_tokens", 0) or 0), int(get("completion_tokens", 0) or 0)


def _reply_text(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, KeyError, TypeError):
        return ""
    return content.strip() if isinstance(content, str) else ""


class LLMGateway:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.keys = settings.key_pool
        # LiteLLM's built-in response cache (process-wide setting).
        litellm.cache = build_cache(settings)

    @property
    def cache_enabled(self) -> bool:
        return litellm.cache is not None

    async def _call(self, key: KeyEntry, messages: list[dict], bypass_cache_read: bool) -> Any:
        kwargs: dict[str, Any] = dict(
            model=key.model,
            messages=messages,
            api_key=key.api_key,
            num_retries=0,
            timeout=self.settings.llm_timeout_seconds,
            caching=True,
        )
        if bypass_cache_read:
            # Skip the cache lookup but still store the fresh response.
            kwargs["cache"] = {"no-cache": True}
        return await litellm.acompletion(**kwargs)

    async def complete(self, messages: list[dict], simulation: dict[str, int]) -> LLMResult:
        """Try key_1..key_n in order; return the first successful completion."""
        bypass_cache_read = bool(simulation)
        failures = 0
        for key in self.keys:
            status = simulated_status_for(simulation, key.key_id)
            started = time.perf_counter()
            try:
                if status is not None:
                    raise simulated_exception(status, key)
                response = await self._call(key, messages, bypass_cache_read)
                reply = _reply_text(response)
                if not reply:
                    # LiteLLM may already have cached this empty answer; make the
                    # remaining keys skip the cache read so it can't poison the pool.
                    bypass_cache_read = True
                    raise litellm.APIError(
                        status_code=502,
                        message="empty completion",
                        llm_provider=key.model.split("/", 1)[0],
                        model=key.model,
                    )
            except Exception as exc:  # any provider failure -> next key
                failures += 1
                logger.warning(
                    "key %s (%s) failed after %dms: %s%s; trying next key",
                    key.key_id,
                    key.model,
                    int((time.perf_counter() - started) * 1000),
                    describe_error(exc),
                    " [simulated]" if status is not None else "",
                )
                continue

            hidden = getattr(response, "_hidden_params", None) or {}
            cache_hit = bool(hidden.get("cache_hit"))
            input_tokens, output_tokens = _usage_tokens(response)
            if cache_hit:
                logger.info("cache hit (%s)", key.model)
                return LLMResult(reply, key.model, input_tokens, output_tokens, None, 0, True)
            # LiteLLM writes the response to the cache in a fire-and-forget
            # asyncio task (caching_handler.async_set_cache -> asyncio.create_task).
            # Yield to the loop briefly so that write completes before we return; an
            # identical request arriving immediately afterwards then hits the cache.
            for _ in range(5):
                await asyncio.sleep(0)
            logger.info("key %s answered (%s), fallback_attempts=%d", key.key_id, key.model, failures)
            return LLMResult(reply, key.model, input_tokens, output_tokens, key.key_id, failures, False)

        logger.error("all %d keys failed", len(self.keys))
        raise AllProvidersUnavailable()
