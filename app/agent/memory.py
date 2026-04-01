"""agent/memory.py - 3-tier session memory with habit tracking."""
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("memory")

_SESSIONS: Dict[str, Dict[str, Any]] = {}


def _s(sid: str) -> Dict[str, Any]:
    if sid not in _SESSIONS:
        _SESSIONS[sid] = {
            "short_term": [],
            "task": {
                "goal": None, "plan": [], "step": 0,
                "status": "idle", "retries": 0,
            },
            "ctx": {},
            "habits": defaultdict(int),
            "pending_goal": None,
            "pending_key":  None,
        }
    return _SESSIONS[sid]


# Short-term
def add_turn(role: str, content: str, sid: str = "default") -> None:
    st = _s(sid)["short_term"]
    st.append({"role": role, "content": str(content)})
    if len(st) > 40:
        _s(sid)["short_term"] = st[-40:]


def get_turns(sid: str = "default", n: int = 4) -> List[Dict]:
    return list(_s(sid)["short_term"][-n:])


# Task
def set_goal(goal: str, plan: List[str], sid: str = "default") -> None:
    _s(sid)["task"] = {
        "goal": goal, "plan": plan, "step": 0,
        "status": "running", "retries": 0,
    }
    logger.info(f"[MEM] Goal: {goal!r} | {len(plan)} steps")


def advance(sid: str = "default") -> None:
    t = _s(sid)["task"]
    t["step"] = min(t["step"] + 1, len(t["plan"]))
    if t["step"] >= len(t["plan"]):
        t["status"] = "complete"


def inc_retry(sid: str = "default") -> int:
    t = _s(sid)["task"]
    t["retries"] = t.get("retries", 0) + 1
    t["status"]  = "retrying"
    return t["retries"]


def mark_done(sid: str = "default") -> None:
    _s(sid)["task"]["status"] = "complete"


def mark_failed(sid: str = "default") -> None:
    _s(sid)["task"]["status"] = "failed"


def get_task(sid: str = "default") -> Dict:
    return dict(_s(sid)["task"])


def reset_task(sid: str = "default") -> None:
    _s(sid)["task"] = {
        "goal": None, "plan": [], "step": 0,
        "status": "idle", "retries": 0,
    }


# Context
def set_ctx(k: str, v: Any, sid: str = "default") -> None:
    _s(sid)["ctx"][k] = v


def get_ctx(k: str, default: Any = None, sid: str = "default") -> Any:
    return _s(sid)["ctx"].get(k, default)


def all_ctx(sid: str = "default") -> Dict:
    return dict(_s(sid)["ctx"])


def update_from_entities(e: Dict, sid: str = "default") -> None:
    if e.get("contact"): set_ctx("last_contact", e["contact"], sid)
    if e.get("app"):     set_ctx("last_app",     e["app"],     sid)
    if e.get("message"): set_ctx("last_message", e["message"], sid)
    if e.get("query"):   set_ctx("last_query",   e["query"],   sid)


def recall_missing(e: Dict, sid: str = "default") -> Dict:
    ctx    = all_ctx(sid)
    intent = e.get("intent", "general")

    # Only recall contact for messaging/calling intents
    if intent in ("send_message", "make_call"):
        if not e.get("contact") and ctx.get("last_contact"):
            e["contact"] = ctx["last_contact"]
            logger.info(f"[MEM] Recalled contact={e['contact']!r}")

    # Only recall app for explicit app intents, never for general/chat/broken
    # This prevents broken input from inheriting a previous session's app
    if intent in ("send_message", "open_app", "play_media", "make_call"):
        if not e.get("app") and ctx.get("last_app"):
            e["app"] = ctx["last_app"]
            logger.info(f"[MEM] Recalled app={e['app']!r}")

    # Only recall message for send_message
    if intent == "send_message":
        if not e.get("message") and ctx.get("last_message"):
            e["message"] = ctx["last_message"]
            logger.info(f"[MEM] Recalled message={e['message']!r}")

    return e


# Habit tracking
def record_habit(intent: str, sid: str = "default") -> None:
    _s(sid)["habits"][intent] += 1


def top_habit(sid: str = "default") -> Optional[str]:
    habits = _s(sid)["habits"]
    if not habits:
        return None
    return max(habits, key=lambda k: habits[k])


# Pending multi-turn
def set_pending(goal: str, key: str, sid: str = "default") -> None:
    _s(sid)["pending_goal"] = goal
    _s(sid)["pending_key"]  = key


def get_pending(sid: str = "default") -> Tuple[Optional[str], Optional[str]]:
    s = _s(sid)
    return s.get("pending_goal"), s.get("pending_key")


def clear_pending(sid: str = "default") -> None:
    _s(sid)["pending_goal"] = None
    _s(sid)["pending_key"]  = None


def has_pending(sid: str = "default") -> bool:
    return bool(_s(sid).get("pending_goal"))


def reset(sid: str = "default") -> None:
    if sid in _SESSIONS:
        del _SESSIONS[sid]


def list_sessions() -> List[str]:
    return list(_SESSIONS.keys())
