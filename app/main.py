import asyncio
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.api.websocket import router as ws_router
from app.core.task_manager.task_manager import task_manager
from app.core.controller_agent import controller_agent
from app.config import settings
from app.utils.logger import logger

# Safe tool imports (prevent crash)
try:
    import app.tools.web
    import app.tools.file
    import app.tools.android
    import app.tools.shell
    import app.tools.memory_tool
    logger.info("Tools loaded successfully")
except Exception as e:
    logger.error(f"Tool loading error: {e}")

# Create app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG
)

# CORS (Render compatible)
=======
"""app/main.py - ARIA v8 FastAPI entry point with WebSocket + REST support."""
import logging
import traceback
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.agent.core    import run_agent, handle_observation
from app.agent.memory  import (
    get_turns, get_task, all_ctx, set_ctx, reset, list_sessions,
)
from app.config        import HOST, PORT
from app.realtime.websocket import websocket_handler
from app.tasks.queue   import queue_status, enqueue_tasks

logger = logging.getLogger("main")


# Request models
class AgentRequest(BaseModel):
    user_input:     str                              = Field(...)
    screen_text:    Optional[str]                    = Field(default="")
    current_app:    Optional[str]                    = Field(default="")
    session_id:     Optional[str]                    = Field(default="default")
    history:        Optional[List[Any]]              = Field(default_factory=list)
    memory:         Optional[Dict[str, Any]]         = Field(default_factory=dict)
    screenshot:     Optional[str]                    = Field(default=None)
    installed_apps: Optional[List[Dict[str, str]]]   = Field(default=None)
    model_config = {"extra": "ignore"}


class ObservationRequest(BaseModel):
    session_id:     Optional[str]                  = Field(default="default")
    last_action:    str                             = Field(...)
    success:        bool                            = Field(...)
    screen_text:    Optional[str]                   = Field(default="")
    current_app:    Optional[str]                   = Field(default="")
    error_message:  Optional[str]                   = Field(default=None)
    screenshot:     Optional[str]                   = Field(default=None)
    installed_apps: Optional[List[Dict[str, str]]]  = Field(default=None)
    model_config = {"extra": "ignore"}


app = FastAPI(
    title="ARIA v8 - Autonomous Android Agent",
    description=(
        "Real-time autonomous Android AI agent. "
        "WebSocket for continuous execution. "
        "REST API for single-shot requests. "
        "Vision system, task queue, self-healing, multi-task support."
    ),
    version="8.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

>>>>>>> e389411 (Initial commit)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

<<<<<<< HEAD
# Routers
app.include_router(api_router, prefix="/api")
app.include_router(ws_router)

# =========================
# STARTUP EVENT (SAFE)
# =========================
@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    print("SERVER STARTING...")

    # Check env variables
    try:
        nvidia_key = os.getenv("NVIDIA_API_KEY")
        if not nvidia_key:
            logger.warning("NVIDIA_API_KEY not set")
        else:
            logger.info("NVIDIA API key detected")
    except Exception as e:
        logger.error(f"Env check error: {e}")

    # Start background task safely
    try:
        asyncio.create_task(task_manager.start(controller_agent.cognition_loop))
        logger.info("Background task manager started")
    except Exception as e:
        logger.error(f"Task manager start failed: {e}")

# =========================
# SHUTDOWN EVENT
# =========================
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down application...")
    try:
        task_manager.stop()
    except Exception as e:
        logger.error(f"Shutdown error: {e}")

# =========================
# ROUTES
# =========================
@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs"
    }

# Health check (Render useful)
@app.get("/health")
async def health():
    return {"status": "healthy"}

# =========================
# GLOBAL ERROR HANDLER
# =========================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "message": "Internal server error",
            "detail": str(exc)
        }
    )

# =========================
# LOCAL RUN (optional)
# =========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
=======

@app.exception_handler(Exception)
async def _global(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        f"[UNHANDLED] {type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    )
    return JSONResponse(
        status_code=500,
        content={"action": "REPLY", "params": {"text": "Server error. Please retry."}},
    )


# WebSocket - real-time continuous execution
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(ws: WebSocket, session_id: str) -> None:
    """
    WebSocket endpoint for real-time autonomous execution.
    Android connects once and communicates continuously.
    No HTTP polling required.
    """
    await websocket_handler(ws, session_id)


# REST - single shot (backward compatible)
@app.get("/health", tags=["System"])
async def health() -> Dict[str, str]:
    return {"status": "ok", "service": "ARIA v8"}


@app.post("/agent/run", tags=["Agent"])
async def agent_run(req: AgentRequest) -> Dict[str, Any]:
    """
    REST endpoint. Supports Android input format:
    {user_input, screen_text, current_app, installed_apps, session_id}
    """
    try:
        sid  = ((req.session_id or "").strip() or "default")
        hist = get_turns(sid, n=4) + list(req.history or [])
        logger.info(
            f"[/run] sid={sid!r} | {req.user_input[:80]!r} "
            f"| apps={len(req.installed_apps or [])} installed"
        )
        return await run_agent(
            user_input     = req.user_input,
            screen_text    = req.screen_text    or "",
            current_app    = req.current_app    or "",
            history        = hist,
            memory         = dict(req.memory    or {}),
            session_id     = sid,
            installed_apps = req.installed_apps,
            screenshot     = req.screenshot,
        )
    except Exception as e:
        logger.error(f"[/run] endpoint error: {e}", exc_info=True)
        return {"action": "REPLY", "params": {"text": "Something went wrong. Please try again."}}


@app.post("/agent/observe", tags=["Agent"])
async def agent_observe(req: ObservationRequest) -> Dict[str, Any]:
    """REST endpoint for observation loop step. Never crashes."""
    try:
        sid = ((req.session_id or "").strip() or "default")
        logger.info(
            f"[/observe] sid={sid!r} action={req.last_action!r} ok={req.success}"
        )
        return await handle_observation(
            session_id     = sid,
            last_action    = req.last_action,
            success        = req.success,
            screen_text    = req.screen_text    or "",
            current_app    = req.current_app    or "",
            error_message  = req.error_message  or "",
            installed_apps = req.installed_apps,
            screenshot     = req.screenshot,
        )
    except Exception as e:
        logger.error(f"[/observe] endpoint error: {e}", exc_info=True)
        return {"action": "REPLY", "params": {"text": "Something went wrong. Please try again."}}


# Memory
@app.get("/memory", tags=["Memory"])
async def get_memory(session_id: str = "default") -> Dict[str, Any]:
    return {
        "short_term": get_turns(session_id, n=10),
        "task":       get_task(session_id),
        "context":    all_ctx(session_id),
    }


@app.post("/memory/add", tags=["Memory"])
async def add_memory(
    body: Dict[str, str],
    session_id: str = "default",
) -> Dict[str, str]:
    k = (body.get("key")   or "").strip()
    v = (body.get("value") or "").strip()
    if not k or not v:
        raise HTTPException(400, "Both 'key' and 'value' are required.")
    set_ctx(k, v, session_id)
    return {"status": "added", "key": k, "value": v}


@app.delete("/memory", tags=["Memory"])
async def clear_memory(session_id: str = "default") -> Dict[str, str]:
    reset(session_id)
    return {"status": "cleared", "session_id": session_id}


# Task queue
@app.get("/tasks", tags=["Tasks"])
async def get_tasks(session_id: str = "default") -> Dict[str, Any]:
    return queue_status(session_id)


@app.post("/tasks/add", tags=["Tasks"])
async def add_tasks(
    body: Dict[str, Any],
    session_id: str = "default",
) -> Dict[str, Any]:
    goals = body.get("goals") or []
    if isinstance(goals, str):
        goals = [goals]
    if not goals:
        raise HTTPException(400, "'goals' list is required.")
    tasks = enqueue_tasks(session_id, goals)
    return {
        "status": "queued",
        "count":  len(tasks),
        "goals":  [t.goal for t in tasks],
    }


@app.get("/sessions", tags=["System"])
async def sessions() -> Dict[str, Any]:
    return {"sessions": list_sessions()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
