"""app/main.py - ARIA v10 FINAL CLEAN ENTRY POINT"""

import logging
import traceback
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.agent.core import run_agent, handle_observation
from app.agent.memory import (
    get_turns, get_task, all_ctx, set_ctx, reset, list_sessions,
)
from app.config import HOST, PORT
from app.realtime.websocket import websocket_handler
from app.tasks.queue import queue_status, enqueue_tasks

logger = logging.getLogger("main")


# =========================
# REQUEST MODELS
# =========================

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


# =========================
# APP INIT
# =========================

app = FastAPI(
    title="ARIA v10 - Autonomous Android Agent",
    version="10.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# GLOBAL ERROR HANDLER
# =========================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        f"[UNHANDLED] {type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    )
    return JSONResponse(
        status_code=500,
        content={
            "action": "REPLY",
            "params": {"text": "Server error. Please retry."},
        },
    )


# =========================
# WEBSOCKET
# =========================

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(ws: WebSocket, session_id: str) -> None:
    await websocket_handler(ws, session_id)


# =========================
# REST ENDPOINTS
# =========================

@app.get("/health", tags=["System"])
async def health() -> Dict[str, str]:
    return {"status": "ok", "service": "ARIA v10"}


@app.post("/agent/run", tags=["Agent"])
async def agent_run(req: AgentRequest) -> Dict[str, Any]:
    try:
        sid  = ((req.session_id or "").strip() or "default")
        hist = get_turns(sid, n=4) + list(req.history or [])

        return await run_agent(
            user_input     = req.user_input,
            screen_text    = req.screen_text or "",
            current_app    = req.current_app or "",
            history        = hist,
            memory         = dict(req.memory or {}),
            session_id     = sid,
            installed_apps = req.installed_apps,
            screenshot     = req.screenshot,
        )

    except Exception as e:
        logger.error(f"[/run] error: {e}", exc_info=True)
        return {
            "action": "REPLY",
            "params": {"text": "Something went wrong. Please try again."},
        }


@app.post("/agent/observe", tags=["Agent"])
async def agent_observe(req: ObservationRequest) -> Dict[str, Any]:
    try:
        sid = ((req.session_id or "").strip() or "default")

        return await handle_observation(
            session_id     = sid,
            last_action    = req.last_action,
            success        = req.success,
            screen_text    = req.screen_text or "",
            current_app    = req.current_app or "",
            error_message  = req.error_message or "",
            installed_apps = req.installed_apps,
            screenshot     = req.screenshot,
        )

    except Exception as e:
        logger.error(f"[/observe] error: {e}", exc_info=True)
        return {
            "action": "REPLY",
            "params": {"text": "Something went wrong. Please try again."},
        }


# =========================
# MEMORY
# =========================

@app.get("/memory", tags=["Memory"])
async def get_memory(session_id: str = "default") -> Dict[str, Any]:
    return {
        "short_term": get_turns(session_id, n=10),
        "task":       get_task(session_id),
        "context":    all_ctx(session_id),
    }


@app.post("/memory/add", tags=["Memory"])
async def add_memory(body: Dict[str, str], session_id: str = "default"):
    k = (body.get("key") or "").strip()
    v = (body.get("value") or "").strip()
    if not k or not v:
        raise HTTPException(400, "Both 'key' and 'value' required.")
    set_ctx(k, v, session_id)
    return {"status": "added"}


@app.delete("/memory", tags=["Memory"])
async def clear_memory(session_id: str = "default"):
    reset(session_id)
    return {"status": "cleared"}


# =========================
# TASK QUEUE
# =========================

@app.get("/tasks", tags=["Tasks"])
async def get_tasks(session_id: str = "default"):
    return queue_status(session_id)


@app.post("/tasks/add", tags=["Tasks"])
async def add_tasks(body: Dict[str, Any], session_id: str = "default"):
    goals = body.get("goals") or []
    if isinstance(goals, str):
        goals = [goals]
    if not goals:
        raise HTTPException(400, "'goals' required")
    tasks = enqueue_tasks(session_id, goals)
    return {"count": len(tasks)}


@app.get("/sessions", tags=["System"])
async def sessions():
    return {"sessions": list_sessions()}


# =========================
# LOCAL RUN
# =========================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
