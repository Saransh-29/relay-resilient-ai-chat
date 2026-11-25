"""Relay backend: resilient LLM chat API (FastAPI + LiteLLM + SQLite)."""

import os

# Use LiteLLM's bundled model cost map instead of fetching it from GitHub at import time:
# no startup network dependency (must be set before litellm is imported).
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
