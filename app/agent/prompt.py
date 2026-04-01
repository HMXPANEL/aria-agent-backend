"""agent/prompt.py - System prompt and message builders with vision context."""
import json
from typing import Any, Dict, List, Optional

_SYSTEM = """You are ARIA - Autonomous Android AI Agent.
You control a real Android phone. Output ONLY raw JSON. Nothing else.

ABSOLUTE RULE:
Your response = single raw JSON object.
No markdown. No ```. No text before or after. JUST JSON.

ACTIONS:
- OPEN_APP(package)      Open app by package name
- CLICK(text)            Tap element by text
- OCR_CLICK(text)        Tap via OCR fallback
- TOUCH_XY(x,y)          Tap by coordinates
- TYPE(text)             Type text
- SCROLL(direction)      up|down|left|right
- SWIPE_XY(x1,y1,x2,y2) Swipe between points
- LONG_PRESS(text)       Long press
- BACK()                 Back button
- HOME()                 Home button
- WAIT(seconds)          Pause 1-10s
- SEARCH_CONTACT(name)   Search contact
- SEARCH_WEB(query)      Browser search
- SCREENSHOT()           Capture screen
- SPEAK(text)            TTS
- REPLY(text)            Text reply (ONLY for questions/chat)

FORMATS:
Single: {"action":"NAME","params":{"key":"val"}}
Multi:  {"actions":[{"action":"A","params":{}},{"action":"B","params":{}}]}
Reply:  {"action":"REPLY","params":{"text":"..."}}

EXAMPLES:
"open youtube":
{"action":"OPEN_APP","params":{"package":"com.google.android.youtube"}}

"send hello to aman on whatsapp":
{"actions":[
{"action":"OPEN_APP","params":{"package":"com.whatsapp"}},
{"action":"WAIT","params":{"seconds":2}},
{"action":"CLICK","params":{"text":"Search"}},
{"action":"TYPE","params":{"text":"Aman"}},
{"action":"CLICK","params":{"text":"Aman"}},
{"action":"TYPE","params":{"text":"hello"}},
{"action":"CLICK","params":{"text":"Send"}}
]}

"who is elon musk":
{"action":"REPLY","params":{"text":"Elon Musk is CEO of Tesla and SpaceX."}}

"go back": {"action":"BACK","params":{}}
"go home": {"action":"HOME","params":{}}

RULES:
1. Question -> REPLY
2. Device task -> ACTIONS (never REPLY for actionable tasks)
3. Send message -> full flow: OPEN->WAIT->SEARCH->TYPE->CLICK->TYPE->SEND
4. Already in target app -> SKIP OPEN_APP
5. Element not in screen_text -> SCROLL then CLICK
6. ALWAYS use package names for OPEN_APP
7. ALWAYS include params key
8. Multi-step -> use actions list
9. CLICK fails -> use OCR_CLICK
10. Output ONLY raw JSON"""

_CACHED = ""


def get_system_prompt() -> str:
    global _CACHED
    if not _CACHED:
        _CACHED = _SYSTEM
    return _CACHED


def build_action_prompt(
    goal: str,
    entities: Dict[str, Any],
    current_step: str,
    screen_text: str,
    current_app: str,
    history: List[Any],
    context: Dict[str, Any],
    installed_apps: Optional[List[Dict[str, str]]] = None,
    vision_context: Optional[str] = None,
    decision: Optional[Dict[str, Any]] = None,
) -> str:
    parts = [f"GOAL: {goal}"]

    ent = {
        k: v for k, v in entities.items()
        if v and k not in ("raw", "is_math", "is_chat", "math_result", "intent")
    }
    if ent:
        parts.append(f"ENTITIES: {json.dumps(ent, ensure_ascii=False)}")

    if decision:
        parts.append(
            f"STRATEGY: {decision.get('strategy','')} "
            f"| confidence={decision.get('confidence','')}"
        )

    parts.append(f"CURRENT APP: {current_app or 'Home Screen'}")
    parts.append(
        f"SCREEN TEXT:\n{screen_text[:800] if screen_text else '(empty)'}"
    )

    if vision_context:
        parts.append(f"SCREEN ANALYSIS: {vision_context}")

    ctx = {k: v for k, v in context.items() if v}
    if ctx:
        parts.append(f"MEMORY: {json.dumps(ctx, ensure_ascii=False)}")

    if installed_apps:
        app_names = [a.get("name", "") for a in installed_apps[:15]]
        parts.append(f"INSTALLED APPS: {', '.join(app_names)}")

    if history:
        h = [
            f"  [{x.get('role','?').upper()}] {x.get('content','')}"
            if isinstance(x, dict) else f"  {x}"
            for x in history[-4:]
        ]
        parts.append("HISTORY:\n" + "\n".join(h))

    parts.append(
        f"CURRENT STEP: {current_step}\n\n"
        "Output ONLY raw JSON. Use actions list for device tasks."
    )
    return "\n\n".join(parts)


def build_observation_prompt(
    goal: str,
    last_action: str,
    success: bool,
    screen_text: str,
    current_app: str,
    next_step: str,
    vision_context: Optional[str] = None,
) -> str:
    status = "SUCCEEDED" if success else "FAILED"
    parts = [
        f"GOAL: {goal}",
        f"LAST ACTION: {last_action} -> {status}",
        f"CURRENT APP: {current_app or 'Unknown'}",
        f"SCREEN TEXT:\n{screen_text[:800] if screen_text else '(empty)'}",
    ]
    if vision_context:
        parts.append(f"SCREEN ANALYSIS: {vision_context}")
    parts.append(f"NEXT STEP: {next_step}\n\nOutput next action as raw JSON only.")
    return "\n".join(parts)


def build_reflection_prompt(
    goal: str,
    bad_resp: str,
    error: str,
    screen_text: str,
) -> str:
    return (
        "CRITICAL: Your previous response was not valid JSON. Fix it now.\n\n"
        f"GOAL: {goal}\n"
        f"BAD RESPONSE: {bad_resp[:400]}\n"
        f"ERROR: {error}\n\n"
        f"SCREEN: {screen_text[:300] if screen_text else '(empty)'}\n\n"
        "Output ONLY valid raw JSON. No explanation."
    )


def build_replan_prompt(
    goal: str,
    failed_plan: List[str],
    reason: str,
    screen_text: str,
    entities: Dict[str, Any],
) -> str:
    ent = {k: v for k, v in entities.items() if v and k != "raw"}
    return (
        f"Plan failed. Generate a new approach.\n\n"
        f"GOAL: {goal}\n"
        f"ENTITIES: {json.dumps(ent, ensure_ascii=False)}\n"
        f"FAILED PLAN: {json.dumps(failed_plan)}\n"
        f"REASON: {reason}\n"
        f"SCREEN: {screen_text[:300] if screen_text else '(empty)'}\n\n"
        "Output ONLY raw valid JSON with corrected actions."
    )
