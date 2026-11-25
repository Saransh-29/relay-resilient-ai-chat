"""Configuration loaded from environment variables (optionally from a .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # .env support is optional
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

DEFAULT_MODEL = "gemini/gemini-3.5-flash-lite"
DEFAULT_SYSTEM_PROMPT = "You are a helpful, concise assistant."
DEFAULT_DATABASE_URL = "sqlite:///./data/app.db"


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except ValueError:
        return default


def _float(value: str | None, default: float) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except ValueError:
        return default


def sqlite_path_from_url(url: str) -> str:
    """Translate a SQLAlchemy-style SQLite URL into a filesystem path.

    sqlite:////data/app.db   -> /data/app.db       (absolute)
    sqlite:///./app.db       -> ./app.db           (relative)
    sqlite:///app.db         -> app.db             (relative)
    sqlite:///:memory:       -> :memory:
    A bare path (no scheme) is returned unchanged.
    """
    url = url.strip()
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///"):] or ":memory:"
    if url.startswith("sqlite://"):
        rest = url[len("sqlite://"):]
        return rest or ":memory:"
    return url


@dataclass(frozen=True)
class KeyEntry:
    key_id: str
    api_key: str
    model: str


@dataclass
class Settings:
    llm_api_keys: list[str] = field(default_factory=list)
    llm_model: str = DEFAULT_MODEL
    llm_models: list[str] = field(default_factory=list)
    database_url: str = DEFAULT_DATABASE_URL
    allowed_origins: list[str] = field(default_factory=lambda: ["*"])
    enable_failure_simulation: bool = False
    default_system_prompt: str = DEFAULT_SYSTEM_PROMPT
    cache_type: str = "local"
    cache_dir: str = "./data/llm_cache"
    llm_timeout_seconds: float = 30.0
    log_level: str = "INFO"

    @property
    def database_path(self) -> str:
        return sqlite_path_from_url(self.database_url)

    @property
    def key_pool(self) -> list[KeyEntry]:
        """Ordered key pool: key_1..key_n, each paired with its model.

        LLM_MODELS (optional) aligns models to keys by position, so one pool can mix
        providers. Missing positions fall back to LLM_MODEL.
        """
        pool = []
        for i, key in enumerate(self.llm_api_keys):
            model = self.llm_models[i] if i < len(self.llm_models) else self.llm_model
            pool.append(KeyEntry(key_id=f"key_{i + 1}", api_key=key, model=model))
        return pool

    @classmethod
    def from_env(cls, load_env_file: bool = True) -> "Settings":
        if load_env_file and load_dotenv is not None:
            # Look for backend/.env and the repo-root .env; never override real env vars.
            here = Path(__file__).resolve().parent.parent
            for candidate in (here / ".env", here.parent / ".env"):
                if candidate.is_file():
                    load_dotenv(candidate, override=False)
        env = os.environ
        origins = _split_csv(env.get("ALLOWED_ORIGINS")) or ["*"]
        return cls(
            llm_api_keys=_split_csv(env.get("LLM_API_KEYS")),
            llm_model=(env.get("LLM_MODEL") or DEFAULT_MODEL).strip(),
            llm_models=_split_csv(env.get("LLM_MODELS")),
            database_url=(env.get("DATABASE_URL") or DEFAULT_DATABASE_URL).strip(),
            allowed_origins=origins,
            enable_failure_simulation=_bool(env.get("ENABLE_FAILURE_SIMULATION")),
            default_system_prompt=(env.get("DEFAULT_SYSTEM_PROMPT") or DEFAULT_SYSTEM_PROMPT).strip(),
            cache_type=(env.get("CACHE_TYPE") or "local").strip().lower(),
            cache_dir=(env.get("CACHE_DIR") or "./data/llm_cache").strip(),
            llm_timeout_seconds=_float(env.get("LLM_TIMEOUT_SECONDS"), 30.0),
            log_level=(env.get("LOG_LEVEL") or "INFO").strip().upper(),
        )
