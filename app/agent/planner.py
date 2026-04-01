"""agent/planner.py - Hierarchical planner + thinking engine + model routing."""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.config import MODEL_AGENT, MODEL_CHAT

logger = logging.getLogger("planner")

_AGENT_RE = re.compile(
    r"\b(open|send|type|click|tap|scroll|search|call|play|pause|share|"
    r"post|message|set|change|enable|disable|take|screenshot|navigate|"
    r"launch|start|install|download|swipe|press|dm|ping)\b",
    re.I,
)
_CHAT_RE = re.compile(
    r"\b(what is|who is|explain|define|tell me|summarise|how does|"
    r"why|when|where is|list|compare|difference|can you tell)\b",
    re.I,
)


def select_model(
    user_input: str,
    is_chat: bool,
    current_app: str = "",
) -> Tuple[str, str]:
    """
    Fixed: is_chat ALWAYS wins. current_app never overrides chat classification.
    """
    if is_chat:
        return "chat", MODEL_CHAT
    if _AGENT_RE.search(user_input):
        return "agent", MODEL_AGENT
    if _CHAT_RE.search(user_input):
        return "chat", MODEL_CHAT
    return "chat", MODEL_CHAT


def think(
    goal: str,
    entities: Dict[str, Any],
    screen_text: str,
    current_app: str,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Thinking engine - reasons about goal before acting.
    Returns a decision dict with intent, strategy, and confidence.
    The agent must think before acting (not blindly execute).
    """
    intent    = entities.get("intent", "general")
    app       = entities.get("app") or ""
    contact   = entities.get("contact") or ""
    screen    = screen_text.lower() if screen_text else ""
    in_app    = bool(app) and current_app == app
    last_app  = context.get("last_app", "")

    # Determine strategy
    if intent == "send_message":
        if not contact:
            strategy = "ask_contact"
        elif in_app:
            strategy = "search_and_send"
        else:
            strategy = "open_and_send"
    elif intent == "open_app":
        strategy = "already_open" if in_app else "open_app"
    elif intent == "search_web":
        strategy = "search"
    elif intent == "chat":
        strategy = "reply_human"
    elif intent == "math":
        strategy = "calculate"
    else:
        strategy = "general_llm"

    # Screen-aware decisions
    if "error" in screen or "not found" in screen:
        strategy = "handle_error"
    if "loading" in screen or "please wait" in screen:
        strategy = "wait_and_observe"

    decision = {
        "intent":     intent,
        "strategy":   strategy,
        "in_app":     in_app,
        "has_contact": bool(contact),
        "app":        app,
        "confidence": "high" if intent != "general" else "low",
    }
    logger.info(f"[THINK] strategy={strategy!r} confidence={decision['confidence']}")
    return decision


def build_plan(
    entities: Dict[str, Any],
    current_app: str,
    installed_apps: Optional[List[Dict[str, str]]] = None,
    decision: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Converts entities + thinking decision into an ordered step list.
    Every path produces >= 1 concrete step. No 'analyse_and_respond'.
    """
    intent  = entities.get("intent", "general")
    app     = entities.get("app") or ""
    contact = entities.get("contact") or ""
    message = entities.get("message") or ""
    query   = entities.get("query") or ""
    in_app  = bool(app) and current_app == app

    # Use strategy from thinking engine if available
    strategy = (decision or {}).get("strategy", "")

    if strategy == "wait_and_observe":
        return ["WAIT:2"]

    if strategy == "handle_error":
        return ["SCROLL:up", "WAIT:1"]

    # FIX: send_message - strict locked order, no variation
    # OPEN_APP -> WAIT -> CLICK:Search -> TYPE:contact -> CLICK:contact -> TYPE:msg -> CLICK:Send
    if intent == "send_message" and app:
        plan = []
        if not in_app:
            plan += [f"OPEN_APP:{app}", "WAIT:2"]
        # Strict locked sequence - no shortcuts
        plan += [
            "CLICK:Search",
            f"TYPE:{contact}",
            f"CLICK:{contact}",
        ]
        if message:
            plan += [f"TYPE:{message}", "CLICK:Send"]
        else:
            # Open chat, let user type manually
            plan += ["CLICK:Message"]
        return plan

    # FIX: make_call - ALWAYS uses Dialer, NEVER WhatsApp
    if intent == "make_call":
        dialer = "com.android.dialer"   # hardcoded - never use messaging app
        plan = []
        if current_app != dialer:
            plan += [f"OPEN_APP:{dialer}", "WAIT:2"]
        if contact:
            plan += [
                f"TYPE:{contact}",
                f"CLICK:{contact}",
                "CLICK:Call",
            ]
        return plan or [f"OPEN_APP:{dialer}", "WAIT:2"]

    # open_app
    if intent == "open_app" and app:
        if in_app:
            return ["REPLY:Already inside that app. What would you like to do?"]
        return [f"OPEN_APP:{app}", "WAIT:2"]

    # FIX: search_web - ALWAYS Chrome, ALWAYS address bar flow
    # Never route search to WhatsApp or other apps
    if intent == "search_web":
        browser = "com.android.chrome"   # always Chrome for web search
        plan = []
        if current_app != browser:
            plan += [f"OPEN_APP:{browser}", "WAIT:2"]
        if query:
            plan += ["CLICK:address bar", f"TYPE:{query}", "CLICK:Go"]
        return plan or [f"OPEN_APP:{browser}", "WAIT:2"]

    # play_media
    if intent == "play_media":
        media = app or "com.google.android.youtube"
        plan = []
        if current_app != media:
            plan += [f"OPEN_APP:{media}", "WAIT:2"]
        target = query or message or "music"
        plan += [
            "CLICK:Search",
            f"TYPE:{target}",
            "CLICK:Search",
            "CLICK:first result",
        ]
        return plan

    # Navigation
    if intent == "home":    return ["HOME"]
    if intent == "back":    return ["BACK"]
    if intent == "scroll":  return ["SCROLL:down"]
    if intent == "capture": return ["SCREENSHOT"]

    # App mentioned without strong intent - open it
    if app and not in_app:
        return [f"OPEN_APP:{app}", "WAIT:2"]

    # FIX: Unknown/general/garbage input -> REPLY, never open random browser
    # Requirement: "I didn't understand. Please try again."
    return ["REPLY:I didn't understand that. Could you please rephrase?"]


def step_label(plan: List[str], idx: int) -> str:
    return plan[idx] if plan and 0 <= idx < len(plan) else "DONE"
