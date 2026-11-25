"""SQLite storage (stdlib sqlite3, parameterized queries only).

All functions here are blocking; callers run them in a worker thread.
A fresh connection is opened per operation, which is safe across threads and cheap
for SQLite. WAL mode plus a busy timeout keep concurrent readers/writers happy.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id  TEXT NOT NULL,
  role        TEXT NOT NULL,   -- 'user' or 'assistant'
  content     TEXT NOT NULL,
  metadata    TEXT,            -- JSON string, assistant messages only
  created_at  TEXT NOT NULL    -- server time, ISO-8601
);
CREATE INDEX IF NOT EXISTS idx_messages_session_id_id ON messages (session_id, id);
CREATE TABLE IF NOT EXISTS sessions (
  session_id     TEXT PRIMARY KEY,
  system_prompt  TEXT,
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL
);
"""

BUSY_TIMEOUT_SECONDS = 10.0


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Database:
    def __init__(self, path: str):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_SECONDS)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {int(BUSY_TIMEOUT_SECONDS * 1000)}")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init(self) -> None:
        """Create the parent directory and schema (idempotent)."""
        if self.path != ":memory:":
            Path(self.path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)
            conn.commit()

    def ping(self) -> bool:
        try:
            with closing(self._connect()) as conn:
                conn.execute("SELECT 1 FROM messages LIMIT 1").fetchall()
            return True
        except sqlite3.Error:
            return False

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT session_id, system_prompt, created_at, updated_at "
                "FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is not None:
                return dict(row)
            # Sessions are also considered to exist if messages exist without a session row.
            exists = conn.execute(
                "SELECT 1 FROM messages WHERE session_id = ? LIMIT 1", (session_id,)
            ).fetchone()
            if exists:
                return {"session_id": session_id, "system_prompt": None}
            return None

    def get_history(self, session_id: str) -> list[dict[str, Any]]:
        """Messages of a session, oldest first. metadata is decoded for assistant rows."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT role, content, metadata FROM messages "
                "WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        history = []
        for row in rows:
            item: dict[str, Any] = {"role": row["role"], "content": row["content"]}
            if row["role"] == "assistant" and row["metadata"]:
                try:
                    item["metadata"] = json.loads(row["metadata"])
                except (TypeError, ValueError):
                    item["metadata"] = {}
            history.append(item)
        return history

    def save_exchange(
        self,
        session_id: str,
        system_prompt_override: str | None,
        user_message: str,
        assistant_message: str,
        metadata: dict[str, Any],
    ) -> None:
        """Atomically upsert the session and store the user+assistant pair.

        An explicitly provided system prompt overrides and persists; otherwise the
        stored one is kept.
        """
        now = utc_now_iso()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO sessions (session_id, system_prompt, created_at, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET "
                "system_prompt = COALESCE(excluded.system_prompt, sessions.system_prompt), "
                "updated_at = excluded.updated_at",
                (session_id, system_prompt_override, now, now),
            )
            conn.execute(
                "INSERT INTO messages (session_id, role, content, metadata, created_at) "
                "VALUES (?, 'user', ?, NULL, ?)",
                (session_id, user_message, now),
            )
            conn.execute(
                "INSERT INTO messages (session_id, role, content, metadata, created_at) "
                "VALUES (?, 'assistant', ?, ?, ?)",
                (session_id, assistant_message, json.dumps(metadata), utc_now_iso()),
            )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()
