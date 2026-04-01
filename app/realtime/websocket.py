"""
realtime/websocket.py - WebSocket real-time continuous execution system.

Android connects ONCE via WebSocket. No more HTTP polling.

Message flow:
  Android -> Backend:
    {"type":"task",    "user_input":"...", "installed_apps":[...]}
    {"type":"observe", "last_action":"...", "success":true,
     "screen_text":"...", "current_app":"...", "screenshot":"..."}
    {"type":"ping"}
    {"type":"disconnect"}

  Backend -> Android:
    {"type":"action",  "data":{...}}
    {"type":"reply",   "text":"..."}
    {"type":"pong"}
    {"type":"error",   "message":"..."}
    {"type":"complete","message":"All tasks done."}
"""
import asyncio
import json
import logging
from typing import Any, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect

from app.agent.core import run_agent, handle_observation
from app.agent.memory import reset as mem_reset
from app.config import WS_TIMEOUT

logger = logging.getLogger("websocket")


async def _send(ws: WebSocket, msg: Dict[str, Any]) -> None:
    """Send JSON message to Android. Swallows send errors gracefully."""
    try:
        await ws.send_text(json.dumps(msg))
    except Exception as e:
        logger.warning(f"[WS] Send failed: {e}")


async def _recv(ws: WebSocket, timeout: float = WS_TIMEOUT) -> Optional[Dict[str, Any]]:
    """Receive and parse JSON message from Android. Returns None on error/timeout."""
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=timeout)
        return json.loads(raw)
    except asyncio.TimeoutError:
        logger.warning("[WS] Receive timeout.")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"[WS] JSON decode error: {e}")
        return None
    except WebSocketDisconnect:
        raise
    except Exception as e:
        logger.error(f"[WS] Receive error: {e}")
        return None


async def websocket_handler(ws: WebSocket, session_id: str) -> None:
    """
    Main WebSocket handler. Runs continuous autonomous loop.
    Android connects once and the agent runs until task complete or disconnected.
    """
    await ws.accept()
    logger.info(f"[WS] Connected: session={session_id!r}")

    installed_apps = []

    await _send(ws, {
        "type":    "connected",
        "message": "ARIA v7 connected. Send a task to begin.",
        "session": session_id,
    })

    try:
        while True:
            msg = await _recv(ws)

            if msg is None:
                # Timeout - send keepalive ping
                await _send(ws, {"type": "ping"})
                continue

            msg_type = str(msg.get("type") or "").lower()

            # ── Ping/pong keepalive ────────────────────────────────────────
            if msg_type == "ping":
                await _send(ws, {"type": "pong"})
                continue

            # ── Disconnect request ─────────────────────────────────────────
            if msg_type == "disconnect":
                logger.info(f"[WS] Disconnect requested: session={session_id!r}")
                await _send(ws, {"type": "disconnected", "message": "Goodbye!"})
                break

            # ── New task ───────────────────────────────────────────────────
            if msg_type == "task":
                user_input     = str(msg.get("user_input") or "").strip()
                screen_text    = str(msg.get("screen_text")    or "")
                current_app    = str(msg.get("current_app")    or "")
                screenshot     = msg.get("screenshot")
                installed_apps = list(msg.get("installed_apps") or [])

                if not user_input:
                    await _send(ws, {"type": "error", "message": "user_input is empty."})
                    continue

                logger.info(f"[WS] Task: {user_input[:80]!r}")

                try:
                    result = await run_agent(
                        user_input=user_input,
                        screen_text=screen_text,
                        current_app=current_app,
                        history=[],
                        memory={},
                        session_id=session_id,
                        installed_apps=installed_apps if installed_apps else None,
                        screenshot=screenshot,
                    )
                except Exception as e:
                    logger.error(f"[WS] run_agent error: {e}")
                    result = {
                        "action": "REPLY",
                        "params": {"text": "Something went wrong. Please try again."},
                    }

                # Determine response type
                if result.get("action") == "REPLY":
                    await _send(ws, {
                        "type": "reply",
                        "text": result.get("params", {}).get("text", ""),
                        "data": result,
                    })
                else:
                    await _send(ws, {
                        "type": "action",
                        "data": result,
                    })
                continue

            # ── Observation (Android reports result of last action) ────────
            if msg_type == "observe":
                last_action   = str(msg.get("last_action")   or "")
                success       = bool(msg.get("success",   True))
                screen_text   = str(msg.get("screen_text")    or "")
                current_app   = str(msg.get("current_app")    or "")
                screenshot    = msg.get("screenshot")
                error_msg     = str(msg.get("error_message")  or "")
                ia             = list(msg.get("installed_apps") or installed_apps)

                logger.info(
                    f"[WS] Observe: action={last_action!r} "
                    f"ok={success} app={current_app!r}"
                )

                try:
                    result = await handle_observation(
                        session_id=session_id,
                        last_action=last_action,
                        success=success,
                        screen_text=screen_text,
                        current_app=current_app,
                        error_message=error_msg,
                        installed_apps=ia if ia else None,
                        screenshot=screenshot,
                    )
                except Exception as e:
                    logger.error(f"[WS] handle_observation error: {e}")
                    result = {
                        "action": "REPLY",
                        "params": {"text": "Observation processing failed. Please retry."},
                    }

                if result.get("action") == "REPLY":
                    text = result.get("params", {}).get("text", "")
                    # Check if it's a completion message
                    if any(w in text.lower() for w in ["completed", "done", "success"]):
                        await _send(ws, {
                            "type":    "complete",
                            "message": text,
                            "data":    result,
                        })
                    else:
                        await _send(ws, {
                            "type": "reply",
                            "text": text,
                            "data": result,
                        })
                else:
                    await _send(ws, {
                        "type": "action",
                        "data": result,
                    })
                continue

            # ── Memory reset ───────────────────────────────────────────────
            if msg_type == "reset":
                try:
                    mem_reset(session_id)
                    await _send(ws, {"type": "reset", "message": "Session memory cleared."})
                except Exception as e:
                    await _send(ws, {"type": "error", "message": str(e)})
                continue

            # ── Unknown message type ───────────────────────────────────────
            await _send(ws, {
                "type":    "error",
                "message": f"Unknown message type: '{msg_type}'. "
                           f"Use: task, observe, ping, disconnect, reset",
            })

    except WebSocketDisconnect:
        logger.info(f"[WS] Disconnected: session={session_id!r}")
    except Exception as e:
        logger.error(f"[WS] Unexpected error: {e}")
        try:
            await _send(ws, {"type": "error", "message": f"Server error: {e}"})
        except Exception:
            pass
    finally:
        logger.info(f"[WS] Session closed: {session_id!r}")
