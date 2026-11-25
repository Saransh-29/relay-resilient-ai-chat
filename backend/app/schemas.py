"""Request/response models matching the assignment's API contract exactly."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_MESSAGE_CHARS = 4000
MAX_SESSION_ID_CHARS = 128
MAX_SYSTEM_PROMPT_CHARS = 4000


class ChatRequest(BaseModel):
    # strict=True: wrong types (e.g. a number for message) are rejected with 422
    # instead of being coerced.
    model_config = ConfigDict(strict=True)

    session_id: str = Field(..., min_length=1, max_length=MAX_SESSION_ID_CHARS)
    message: str
    system_prompt: Optional[str] = None

    @field_validator("session_id")
    @classmethod
    def _session_id_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("session_id must not be empty or whitespace")
        return v

    @field_validator("message")
    @classmethod
    def _message_trimmed_length(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message must not be empty or whitespace")
        if len(v) > MAX_MESSAGE_CHARS:
            raise ValueError(f"message must be at most {MAX_MESSAGE_CHARS} characters after trimming")
        return v

    @field_validator("system_prompt")
    @classmethod
    def _system_prompt_clean(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None  # empty == absent
        if len(v) > MAX_SYSTEM_PROMPT_CHARS:
            raise ValueError(f"system_prompt must be at most {MAX_SYSTEM_PROMPT_CHARS} characters")
        return v


class ChatMetadata(BaseModel):
    resolution_source: Literal["LIVE_INFERENCE", "LLM_CACHE"]
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    key_id: Optional[str]
    fallback_attempts: int


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    metadata: ChatMetadata


class HealthResponse(BaseModel):
    status: str
    keys_configured: int
    cache_enabled: bool
