"""
agent/safety.py — ARIA v9 FINAL PRODUCTION

Changes from v8:
  - is_junk_input()  : detects symbols-only / repeat-char / no-real-words
  - final_gate()     : hard block before every return (OPEN_APP only when valid)
  - guard_action()   : unchanged
  - guard_list()     : empty CLICK -> WAIT(1), unchanged
"""
import logging
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("safety")

WHITELIST: set = {
    "OPEN_APP", "CLICK", "OCR_CLICK", "TOUCH_XY", "TAP_XY", "TYPE", "SCROLL",
    "SWIPE", "SWIPE_XY", "LONG_PRESS", "BACK", "HOME", "WAIT",
    "SEARCH_CONTACT", "SEARCH_WEB", "SCREENSHOT", "COPY", "PASTE",
    "BROWSER_OPEN", "BROWSER_BACK", "BROWSER_REFRESH", "BROWSER_SCROLL",
    "BROWSER_FILL", "BROWSER_CLICK", "BROWSER_SUBMIT", "BROWSER_GET_TEXT",
    "EXEC_CODE", "SPEAK", "REPLY",
}

_BLOCKED_PKG  = re.compile(r"^com\.android\.shell$|superuser|magisk|xposed|chainfire", re.I)
_INJECT       = re.compile(r"ignore previous instructions|jailbreak|act as DAN|forget your (system|instructions)", re.I)
_SYMBOLS_ONLY = re.compile(r'^[^a-zA-Z0-9]+$')
_REPEAT_CHAR  = re.compile(r'^(.)\1{4,}$')
_REAL_WORD    = re.compile(r'[a-zA-Z]{2,}')


def is_junk_input(text: str) -> bool:
    """
    True for garbage: symbols-only / all-repeating-chars / no real 2+ letter word.
    '@@@@@@@' -> True
    'aaaaaaa' -> True
    '1 2 3'   -> True   (no alphabetic word >= 2 chars)
    'hi'      -> False
    'hello'   -> False
    """
    t = (text or "").strip()
    if not t:
        return True
    if _SYMBOLS_ONLY.match(t):
        return True
    if _REPEAT_CHAR.match(t):
        return True
    return not bool(_REAL_WORD.search(t))


def guard_action(action: str, params: Dict[str, Any]) -> Tuple[bool, str]:
    a = str(action).upper().strip()
    if a not in WHITELIST:
        return False, f"'{a}' not in whitelist."
    if a == "OPEN_APP":
        pkg = str(params.get("package") or "").strip()
        if not pkg:
            return False, "OPEN_APP missing 'package'."
        if _BLOCKED_PKG.search(pkg):
            return False, f"Blocked package: {pkg}"
    if a in ("TYPE", "REPLY", "SPEAK"):
        if _INJECT.search(str(params.get("text") or "")):
            return False, "Prompt injection detected."
    if a == "WAIT":
        try:
            s = int(params.get("seconds", 2))
            params["seconds"] = max(1, min(s, 10))
        except Exception:
            params["seconds"] = 2
    if a == "SCROLL":
        d = str(params.get("direction", "down")).lower()
        if d not in ("up", "down", "left", "right"):
            params["direction"] = "down"
    return True, ""


def guard_list(actions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    safe, blocked = [], []
    for item in actions:
        a = str(item.get("action") or "").upper().strip()
        p = dict(item.get("params") or {})
        item["action"] = a
        item["params"] = p
        if a in ("CLICK", "OCR_CLICK") and not str(p.get("text") or "").strip():
            logger.warning("[SAFETY] CLICK has empty text -> replaced with WAIT(1)")
            safe.append({"action": "WAIT", "params": {"seconds": 1}})
            continue
        ok, reason = guard_action(a, p)
        if ok:
            safe.append({"action": a, "params": p})
        else:
            logger.warning(f"[SAFETY] Blocked {a}: {reason}")
            blocked.append(reason)
    return safe, blocked


def final_gate(result: Dict[str, Any], intent: str) -> Dict[str, Any]:
    """
    ARIA v9 final safety layer — called immediately before every return.

    Rules enforced:
      1. intent == 'general' or 'chat'  -> BLOCK all OPEN_APP
      2. intent == 'search_web'         -> BLOCK any OPEN_APP that is NOT Chrome
      3. Empty package OPEN_APP         -> BLOCK always
    """
    chrome = "com.android.chrome"

    def _allow(a: Dict[str, Any]) -> bool:
        act = str(a.get("action", "")).upper()
        if act != "OPEN_APP":
            return True
        pkg = str(a.get("params", {}).get("package", "")).strip()
        if not pkg:
            logger.warning("[V9-GATE] Blocked OPEN_APP — empty package")
            return False
        if intent in ("general", "chat"):
            logger.warning(f"[V9-GATE] Blocked OPEN_APP({pkg}) — intent={intent!r}")
            return False
        if intent == "search_web" and pkg != chrome:
            logger.warning(f"[V9-GATE] Blocked OPEN_APP({pkg}) — search must use chrome")
            return False
        return True

    _reply = {
        "action": "REPLY",
        "params": {"text": "I didn't understand that. Could you please rephrase?"},
    }

    if "actions" in result:
        kept = [a for a in (result.get("actions") or []) if _allow(a)]
        if not kept:
            return _reply
        return kept[0] if len(kept) == 1 else {"actions": kept}

    if "action" in result:
        return result if _allow(result) else _reply

    return result


def is_safe_input(text: str) -> bool:
    return not bool(_INJECT.search(str(text)))
