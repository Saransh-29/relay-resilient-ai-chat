"""FastAPI application: exactly GET /health, POST /chat, GET /sessions/{session_id}/messages."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from .chat_service import ChatService
from .config import Settings
from .db import Database
from .llm import AllProvidersUnavailable, LLMGateway
from .logging_utils import configure_logging
from .schemas import ChatRequest, ChatResponse, HealthResponse
from .simulation import SimulationHeaderError, parse_simulation_header

logger = logging.getLogger("relay")


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level, settings.llm_api_keys)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings.database_path)
        try:
            await run_in_threadpool(db.init)
        except Exception as exc:  # health reports 503; app still starts
            logger.error("database initialisation failed: %s", type(exc).__name__)
        gateway = LLMGateway(settings)
        app.state.settings = settings
        app.state.db = db
        app.state.gateway = gateway
        app.state.chat = ChatService(settings, db, gateway)
        logger.info(
            "relay started: keys=%d models=%s cache=%s simulation=%s",
            len(settings.key_pool),
            sorted({k.model for k in settings.key_pool}),
            settings.cache_type,
            settings.enable_failure_simulation,
        )
        yield

    app = FastAPI(title="Relay - Resilient AI Chat", version="1.0.0", lifespan=lifespan)

    origins = settings.allowed_origins
    allow_all = "*" in origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if allow_all else origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Simulate-Failure", "Accept", "Authorization"],
    )

    # ---- error handlers: every error is JSON with a "detail" field ----

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        # Same shape as FastAPI's default, but make sure non-serialisable ctx
        # values (e.g. a ValueError instance) never break the JSON response.
        errors = []
        for err in exc.errors():
            item = {k: v for k, v in err.items() if k in ("type", "loc", "msg", "input")}
            if "input" in item and not isinstance(item["input"], (str, int, float, bool, type(None), list, dict)):
                item["input"] = str(item["input"])
            errors.append(item)
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(AllProvidersUnavailable)
    async def _all_failed_handler(request: Request, exc: AllProvidersUnavailable):
        return JSONResponse(status_code=503, content={"detail": "all providers unavailable"})

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception):
        logger.error("unhandled error on %s %s: %s", request.method, request.url.path, type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    # ---- routes ----

    @app.get("/health", response_model=HealthResponse)
    async def health(request: Request):
        db: Database = request.app.state.db
        keys = len(settings.key_pool)
        db_ok = await run_in_threadpool(db.ping)
        if not db_ok or keys == 0:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unavailable",
                    "keys_configured": keys,
                    "cache_enabled": request.app.state.gateway.cache_enabled,
                    "detail": "database unreachable" if not db_ok else "no API keys configured",
                },
            )
        return {"status": "ok", "keys_configured": keys, "cache_enabled": request.app.state.gateway.cache_enabled}

    @app.post("/chat", response_model=ChatResponse)
    async def chat(
        request: Request,
        body: ChatRequest,
        x_simulate_failure: Optional[str] = Header(default=None, alias="X-Simulate-Failure"),
    ):
        simulation: dict[str, int] = {}
        if settings.enable_failure_simulation and x_simulate_failure is not None:
            try:
                simulation = parse_simulation_header(x_simulate_failure)
            except SimulationHeaderError as exc:
                return JSONResponse(status_code=422, content={"detail": str(exc)})
        return await request.app.state.chat.handle(body, simulation)

    @app.get("/sessions/{session_id}/messages")
    async def session_messages(request: Request, session_id: str):
        db: Database = request.app.state.db
        session = await run_in_threadpool(db.get_session, session_id)
        if session is None:
            return JSONResponse(status_code=404, content={"detail": "session not found"})
        history = await run_in_threadpool(db.get_history, session_id)
        return {"session_id": session_id, "messages": history}

    return app


app = create_app()
