"""Parsing of the X-Simulate-Failure request header (request-scoped failure injection)."""

from __future__ import annotations

import re

ALLOWED_STATUSES = frozenset({429, 500, 502, 503})
_KEY_ID_RE = re.compile(r"^(\*|key_[1-9][0-9]*)$")


class SimulationHeaderError(ValueError):
    """Raised when the X-Simulate-Failure header is malformed."""


def parse_simulation_header(raw: str | None) -> dict[str, int]:
    """Parse e.g. "key_1=429, key_2=500" or "*=429" into {"key_1": 429, ...}.

    Whitespace is tolerated. An empty/blank header means "no simulation".
    Raises SimulationHeaderError with a human-readable message on bad input.
    """
    if raw is None or raw.strip() == "":
        return {}
    result: dict[str, int] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            raise SimulationHeaderError("empty entry in X-Simulate-Failure header")
        if "=" not in part:
            raise SimulationHeaderError(
                f"invalid X-Simulate-Failure entry '{part}': expected <key_id>=<status>"
            )
        key_id, _, status_str = part.partition("=")
        key_id, status_str = key_id.strip(), status_str.strip()
        if not _KEY_ID_RE.match(key_id):
            raise SimulationHeaderError(
                f"invalid key id '{key_id}' in X-Simulate-Failure (use key_1, key_2, ... or *)"
            )
        try:
            status = int(status_str)
        except ValueError:
            raise SimulationHeaderError(
                f"invalid status '{status_str}' in X-Simulate-Failure (allowed: 429, 500, 502, 503)"
            ) from None
        if status not in ALLOWED_STATUSES:
            raise SimulationHeaderError(
                f"unsupported status {status} in X-Simulate-Failure (allowed: 429, 500, 502, 503)"
            )
        result[key_id] = status
    return result


def simulated_status_for(plan: dict[str, int], key_id: str) -> int | None:
    """Status to simulate for key_id, if any. Specific entries win over '*'."""
    if key_id in plan:
        return plan[key_id]
    return plan.get("*")
