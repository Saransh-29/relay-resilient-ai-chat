"""Logging setup with a redaction filter so API keys never reach log output."""

from __future__ import annotations

import logging
from typing import Iterable

REDACTED = "[REDACTED]"


class SecretRedactingFilter(logging.Filter):
    """Replace any configured secret appearing in a log record with [REDACTED].

    Defence in depth: application code never logs keys, but third-party libraries
    might include them in exception messages.
    """

    def __init__(self, secrets: Iterable[str]):
        super().__init__()
        # Longest first so overlapping secrets are fully masked.
        self.secrets = sorted({s for s in secrets if s and len(s) >= 4}, key=len, reverse=True)

    def _scrub(self, text: str) -> str:
        for secret in self.secrets:
            if secret in text:
                text = text.replace(secret, REDACTED)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        if not self.secrets:
            return True
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - malformed record
            return True
        scrubbed = self._scrub(message)
        if record.exc_info:
            # Pre-render the traceback so it can be scrubbed, then drop exc_info.
            formatter = logging.Formatter()
            scrubbed = scrubbed + "\n" + self._scrub(formatter.formatException(record.exc_info))
            record.exc_info = None
            record.exc_text = None
        if record.stack_info:
            record.stack_info = self._scrub(record.stack_info)
        record.msg = scrubbed
        record.args = None
        return True


def configure_logging(level: str, secrets: Iterable[str]) -> None:
    root = logging.getLogger()
    if not any(getattr(h, "_relay_handler", False) for h in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        handler._relay_handler = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    redactor = SecretRedactingFilter(secrets)
    # Attach to every handler on the root logger (filters on handlers see records
    # propagated from all child loggers, unlike logger-level filters).
    for handler in root.handlers:
        for f in list(handler.filters):
            if isinstance(f, SecretRedactingFilter):
                handler.removeFilter(f)
        handler.addFilter(redactor)

    # Keep LiteLLM and HTTP client chatter quiet.
    for noisy in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "litellm", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
