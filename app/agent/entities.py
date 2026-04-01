"""
agent/entities.py - Intent + entity extraction with dynamic app resolution.

Handles:
  - Greeting/chat detection (never routes to device actions)
  - Dynamic installed_apps with fuzzy matching
  - Any contact name (any case, any language)
  - Multi-task splitting ("open youtube AND send hi to aman")
  - Math eval (sandboxed)
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.config import APP_MAP

logger = logging.getLogger("entities")

# Intent rules
_INTENTS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b(send|ping|dm)\b", re.I),                               "send_message"),
    (re.compile(r"\b(call|dial|ring|facetime|video call)\b", re.I),         "make_call"),
    (re.compile(r"\b(open|launch|start|go to|switch to)\b", re.I),          "open_app"),
    (re.compile(r"\b(search|google|find|look up|browse)\b", re.I),          "search_web"),
    (re.compile(r"\b(play|watch|stream|listen|music|video|song)\b", re.I),  "play_media"),
    (re.compile(r"\b(set|alarm|timer|remind|schedule)\b", re.I),            "set_reminder"),
    (re.compile(r"\b(take|capture|photo|screenshot|selfie)\b", re.I),       "capture"),
    (re.compile(r"\bgo home\b|\bpress home\b", re.I),                       "home"),
    (re.compile(r"\bgo back\b|\bpress back\b", re.I),                       "back"),
    (re.compile(r"\bscroll (down|up|left|right)\b", re.I),                  "scroll"),
    (re.compile(r"\bmessage\s+[A-Za-z]", re.I),                             "send_message"),
    (re.compile(r"\btext\s+[A-Za-z]", re.I),                                "send_message"),
]

_CHAT_RE = re.compile(
    r"\b(hi|hello|hey|howdy|greetings|sup|yo|hiya|"
    r"what is|what are|who is|who are|explain|tell me|define|"
    r"describe|how does|how do|why|when|where is|"
    r"difference|meaning of|can you tell|"
    r"how are you|how's it going|what's up|nice to meet|"
    r"thank you|thanks|good morning|good night|good afternoon|"
    r"i need help|help me|what can you do|who are you)\b",
    re.I,
)

_GREETING_EXACT: set = {
    "hi", "hello", "hey", "howdy", "sup", "yo", "hiya", "helo",
    "good morning", "good night", "good afternoon", "good evening",
    "how are you", "how r u", "what's up", "whats up",
    "thank you", "thanks", "ty", "thx",
    "who are you", "what can you do", "help", "help me",
    "nice", "ok", "okay", "cool", "great", "sure", "yes", "no",
    "bye", "goodbye", "see you", "take care",
}

_ACTION_VERB_RE = re.compile(
    r"\b(send|text|dm|ping|open|launch|call|dial|search|play|set|"
    r"go to|switch|start|find|message\s+\w|scroll)\b",
    re.I,
)

_MATH_CHARS  = re.compile(r"^[\d\s\+\-\*\/\^\(\)\.%]+$")
_MATH_DETECT = re.compile(
    r"^\s*(?:what(?:'s| is)\s+|calc(?:ulate)?\s+|compute\s+|solve\s+)?"
    r"([\d][\d\s\+\-\*\/\^\(\)\.%]*)\s*[\?]?\s*$",
    re.I,
)

_STOP: set = {
    "on", "via", "using", "through", "in", "at", "with", "by", "from",
    "the", "a", "an", "to", "for", "about", "and", "or", "but", "not",
    "it", "this", "that", "whatsapp", "telegram", "instagram", "facebook",
    "twitter", "discord", "snapchat", "signal", "message", "msg", "text",
    "send", "app", "phone", "mobile", "chat", "now", "please", "him", "her",
    "them", "me", "us", "you", "my", "your", "their", "our", "wa", "tg",
}

_NAME_STOP: set = {
    "hi", "hello", "hey", "bye", "goodbye", "thanks", "thank", "ok", "okay",
    "yes", "no", "please", "sorry", "lol", "haha", "great", "good", "nice",
    "sure", "right", "wrong", "maybe", "always",
}

_APP_KEYS = set(APP_MAP.keys())
_MSG_FILLERS: set = {
    "a", "an", "the", "some", "my", "your", "message", "msg",
    "text", "something", "anything", "it",
}

_SEARCH_RE = re.compile(r"\b(?:search|google|find|look up|browse)\s+(?:for\s+)?(.+)", re.I)
_APP_SFXRE = re.compile(r"^(?:on|via|using|through|in|at)\s+\w+$", re.I)

# Multi-task splitters
_SPLIT_RE = re.compile(
    r"\s+(?:and then|then|after that|also)\s+",
    re.I,
)

# Action verbs that signal a new task when they follow "and"
_ACTION_VERB_START = re.compile(
    r"^\s*(?:open|launch|start|send|call|dial|search|google|find|play|watch|"
    r"stream|set|alarm|timer|remind|take|capture|go home|go back|scroll|"
    r"message|text|dm|ping|browse|look up)\b",
    re.I,
)


def split_multi_tasks(user_input: str) -> List[str]:
    """
    Splits compound commands into individual tasks.

    FIX: Only splits on bare "and" when BOTH sides begin with an action verb.
    This prevents "search latest war between us and iran" from splitting on
    the "and" in the middle of the query.

    Examples:
      "open youtube and send hi to aman" -> 2 tasks (both sides are actions)
      "search latest war between us and iran" -> 1 task (right side not action)
    """
    # First try strong splitters (and then, then, after that, also)
    parts = _SPLIT_RE.split(user_input.strip())

    if len(parts) == 1:
        # Try bare "and" — but ONLY when both sides start with action verbs
        bare_and = re.compile(r"\s+and\s+", re.I)
        candidates = bare_and.split(user_input.strip())
        if len(candidates) > 1:
            # Rebuild valid splits: only split when right side starts with action verb
            result = [candidates[0]]
            for candidate in candidates[1:]:
                if _ACTION_VERB_START.match(candidate):
                    # Both the new part starts with action verb → real task boundary
                    result.append(candidate.strip())
                else:
                    # "and" is part of content (e.g. "us and iran") → merge back
                    result[-1] = result[-1] + " and " + candidate
            parts = result

    cleaned = [p.strip() for p in parts if p.strip()]
    if len(cleaned) > 1:
        logger.info(f"[ENT] Multi-task split: {cleaned}")
    return cleaned if cleaned else [user_input.strip()]


def resolve_app(
    text: str,
    installed_apps: Optional[List[Dict[str, str]]] = None,
) -> Optional[str]:
    """
    Resolves app name to package. Priority:
    1. Exact match in installed_apps
    2. Fuzzy/contains/compressed match in installed_apps
    3. Built-in APP_MAP
    """
    if not text:
        return None
    lower = text.lower()

    if installed_apps:
        input_words    = set(lower.split())
        input_nospace  = lower.replace(" ", "").replace("-", "")

        for app in installed_apps:
            name    = str(app.get("name") or "").lower().strip()
            package = str(app.get("package") or "").strip()
            if not name or not package:
                continue
            # Exact contains match
            if name in lower:
                logger.info(f"[APP] Exact match: {name} -> {package}")
                return package

        for app in installed_apps:
            name    = str(app.get("name") or "").lower().strip()
            package = str(app.get("package") or "").strip()
            if not name or not package:
                continue
            name_nospace = name.replace(" ", "").replace("-", "")
            app_words    = set(name.split())
            if (
                (app_words & input_words)
                or (name_nospace in input_nospace)
                or (input_nospace in name_nospace)
            ):
                logger.info(f"[APP] Fuzzy match: {name} -> {package}")
                return package

    for kw in sorted(APP_MAP, key=len, reverse=True):
        if re.search(r"\b" + re.escape(kw) + r"\b", lower):
            return APP_MAP[kw]

    return None


def extract(
    user_input: str,
    installed_apps: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    raw     = user_input.strip()
    raw_low = raw.lower()

    # Math first
    m = _MATH_DETECT.match(raw)
    if m:
        return {
            "intent": "math", "app": None, "contact": None, "message": None,
            "query": None, "is_math": True, "is_chat": False,
            "math_result": _safe_math(m.group(1).strip()), "raw": raw,
        }

    # Greeting/chat shortcut (only when no action verb present)
    if raw_low in _GREETING_EXACT or (
        len(raw.split()) <= 4
        and bool(_CHAT_RE.search(raw))
        and not _ACTION_VERB_RE.search(raw)
    ):
        logger.info(f"[ENT] Greeting: {raw!r}")
        return {
            "intent": "chat", "app": None, "contact": None,
            "message": None, "query": raw,
            "is_math": False, "is_chat": True, "raw": raw,
        }

    intent  = _detect_intent(raw)
    is_chat = bool(_CHAT_RE.search(raw)) and intent == "general"
    app     = resolve_app(raw, installed_apps)
    contact = _extract_contact(raw)
    message = None
    query   = None

    if intent == "send_message":
        message = _extract_message(raw, contact)
        if not app:
            app = "com.whatsapp"

    if intent == "search_web":
        sm = _SEARCH_RE.search(raw)
        query = sm.group(1).strip() if sm else raw

    result = {
        "intent": intent, "app": app, "contact": contact,
        "message": message, "query": query,
        "is_math": False, "is_chat": is_chat, "raw": raw,
    }
    logger.info(f"[ENT] {intent!r} contact={contact!r} msg={message!r} app={app!r}")
    return result


def check_completeness(e: Dict) -> Tuple[bool, str]:
    intent  = e.get("intent", "general")
    missing = []

    if intent == "send_message":
        if not e.get("contact"):
            missing.append("who to send it to")
    elif intent == "make_call":
        if not e.get("contact"):
            missing.append("who to call")
    elif intent == "open_app":
        if not e.get("app"):
            missing.append("which app to open")
    elif intent == "search_web":
        if not e.get("query"):
            missing.append("what to search for")

    if not missing:
        return True, ""
    q = "Who should I send it to?" if (
        intent == "send_message" and not e.get("contact")
    ) else "Could you tell me " + " and ".join(missing) + "?"
    return False, q


def _detect_intent(text: str) -> str:
    for pat, intent in _INTENTS:
        if pat.search(text):
            return intent
    return "general"


def _clean_name(raw: str, max_words: int) -> Optional[str]:
    words, clean = raw.strip().split(), []
    for w in words:
        if len(clean) >= max_words:
            break
        wl = w.lower().rstrip(".,!?;")
        if wl in _STOP or wl in _APP_KEYS:
            break
        if wl in _NAME_STOP and len(clean) >= 1:
            break
        clean.append(w)
    if not clean:
        return None
    name = " ".join(clean).title()
    return None if name.lower() in _STOP or name.lower() in _APP_KEYS else name


def _extract_contact(text: str) -> Optional[str]:
    m = re.search(
        r"\b(?:to|for)\s+([A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*)?)",
        text, re.I,
    )
    if m:
        r = _clean_name(m.group(1), max_words=2)
        if r:
            return r
    m = re.search(
        r"\b(?:text|message|call|ping|dm)\s+([A-Za-z][A-Za-z'\-]*)",
        text, re.I,
    )
    if m:
        r = _clean_name(m.group(1), max_words=1)
        if r:
            return r
    return None


def _valid_msg(s: str) -> bool:
    s = s.strip()
    if len(s) < 1:
        return False
    if _APP_SFXRE.match(s):
        return False
    return not all(w in _MSG_FILLERS for w in s.lower().split())


def _extract_message(text: str, contact: Optional[str] = None) -> Optional[str]:
    m = re.search(
        r'["\u201c\u201d\u2018\u2019]([^"\']{1,})["\u201c\u201d\u2018\u2019]',
        text,
    )
    if m and _valid_msg(m.group(1)):
        return m.group(1).strip()

    m = re.search(
        r"\b(?:say|type|write|telling?)\s+(.+?)(?=\s+to\b|\s+on\b|\s+via\b|$)",
        text, re.I,
    )
    if m and _valid_msg(m.group(1)):
        return m.group(1).strip()

    if contact:
        esc = re.escape(contact.lower())
        m = re.search(r"\bsend\s+(.+?)\s+to\s+" + esc, text, re.I)
        if m:
            c = m.group(1).strip()
            if _valid_msg(c) and c.lower() != contact.lower():
                return c
        m = re.search(r"\bsend\s+(.+?)\s+to\s+\w", text, re.I)
        if m:
            c = m.group(1).strip()
            if _valid_msg(c) and c.lower() != contact.lower():
                return c

    if contact:
        esc = re.escape(contact.lower())
        m = re.search(
            r"\b(?:text|message|ping|dm)\s+" + esc + r"\s+(.+)",
            text, re.I,
        )
        if m and _valid_msg(m.group(1)):
            return m.group(1).strip()

    return None


def _safe_math(expr: str) -> str:
    if not _MATH_CHARS.match(expr):
        return "I can only evaluate simple arithmetic."
    try:
        result = eval(  # noqa: S307
            compile(expr.replace("^", "**"), "<math>", "eval"),
            {"__builtins__": {}, "__name__": None},
            {},
        )
        if isinstance(result, float):
            r = round(result, 10)
            return str(int(r)) if r == int(r) else str(r)
        return str(result)
    except ZeroDivisionError:
        return "Cannot divide by zero."
    except Exception:
        return "Could not evaluate."
