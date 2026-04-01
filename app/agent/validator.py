"""agent/validator.py - Strict JSON validation. Never returns None. Never crashes."""
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.agent.safety import WHITELIST

logger = logging.getLogger("validator")

_FENCE   = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.I)
_TRAIL_C = re.compile(r",\s*([}\]])")
_BOOLFIX = re.compile(r"\b(True|False|None)\b")

_REQUIRED: Dict[str, List[str]] = {
    "OPEN_APP":       ["package"],
    "CLICK":          ["text"],
    "OCR_CLICK":      ["text"],
    "TOUCH_XY":       ["x", "y"],
    "TAP_XY":         ["x", "y"],
    "TYPE":           ["text"],
    "SCROLL":         ["direction"],
    "WAIT":           ["seconds"],
    "SEARCH_CONTACT": ["name"],
    "SEARCH_WEB":     ["query"],
    "REPLY":          ["text"],
    "BROWSER_OPEN":   ["url"],
    "BROWSER_FILL":   ["field", "value"],
    "SPEAK":          ["text"],
    "SWIPE_XY":       ["x1", "y1", "x2", "y2"],
}

SAFE_FALLBACK: Dict[str, Any] = {
    "action": "REPLY",
    "params": {"text": "I encountered an issue. Please try again."},
}


def _extract(text: str) -> Optional[str]:
    if not text:
        return None
    m = _FENCE.search(text)
    if m:
        text = m.group(1).strip()
    s, e = text.find("{"), text.rfind("}")
    if s != -1 and e > s:
        return text[s:e + 1]
    s, e = text.find("["), text.rfind("]")
    if s != -1 and e > s:
        return '{"actions":' + text[s:e + 1] + "}"
    return None


def _repair(text: str) -> str:
    text = _TRAIL_C.sub(r"\1", text)

    def _b(m: re.Match) -> str:
        return {"True": "true", "False": "false", "None": "null"}[m.group(1)]

    text = _BOOLFIX.sub(_b, text)
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass
    text = re.sub(r"'([^']*)'", r'"\1"', text)
    return text


def _parse(text: str) -> Tuple[Optional[Dict], str]:
    try:
        d = json.loads(text)
        if isinstance(d, dict):
            return d, ""
        return None, f"Expected object, got {type(d).__name__}"
    except json.JSONDecodeError as exc:
        return None, str(exc)


def _valid_item(action: str, params: Any) -> Tuple[bool, str]:
    a = str(action).upper().strip()
    if a not in WHITELIST:
        return False, f"Unknown action '{a}'"
    if not isinstance(params, dict):
        return False, "params must be a dict"
    for p in _REQUIRED.get(a, []):
        v = params.get(p)
        if v is None or str(v).strip() == "":
            return False, f"'{a}' missing param '{p}'"
    return True, ""


def validate(raw: Any) -> Dict[str, Any]:
    """Parse and validate LLM output. Always returns a valid dict."""
    if not raw or not str(raw).strip():
        logger.warning("[VAL] Empty response -> fallback")
        return SAFE_FALLBACK.copy()

    candidate = _extract(str(raw))
    if not candidate:
        logger.warning(f"[VAL] No JSON in: {str(raw)[:100]!r}")
        return SAFE_FALLBACK.copy()

    candidate = _repair(candidate)
    data, err = _parse(candidate)
    if data is None:
        logger.warning(f"[VAL] Parse failed: {err}")
        return SAFE_FALLBACK.copy()

    if "action" in data:
        action = str(data.get("action") or "").upper().strip()
        params = data.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        data["action"] = action
        data["params"] = params
        ok, err = _valid_item(action, params)
        if not ok:
            logger.warning(f"[VAL] Invalid: {err}")
            return SAFE_FALLBACK.copy()
        logger.info(f"[VAL] Single: {action}")
        return data

    if "actions" in data:
        raw_items = data.get("actions") or []
        if not isinstance(raw_items, list):
            return SAFE_FALLBACK.copy()
        valid_items = []
        for i, item in enumerate(raw_items):
            if not isinstance(item, dict):
                continue
            action = str(item.get("action") or "").upper().strip()
            params = item.get("params") or {}
            if not isinstance(params, dict):
                params = {}
            ok, err = _valid_item(action, params)
            if ok:
                valid_items.append({"action": action, "params": params})
            else:
                logger.debug(f"[VAL] actions[{i}] skipped: {err}")
        if not valid_items:
            return SAFE_FALLBACK.copy()
        logger.info(f"[VAL] Multi: {len(valid_items)} steps")
        return {"actions": valid_items}

    logger.warning(f"[VAL] No action/actions key. Keys={list(data)}")
    return SAFE_FALLBACK.copy()


def is_fallback(result: Dict[str, Any]) -> bool:
    return (
        result.get("action") == "REPLY"
        and "issue" in str(result.get("params", {}).get("text", "")).lower()
    )


def sanitise(
    user_input: str,
    screen_text: str,
    current_app: str,
    history: list,
    memory: dict,
) -> Tuple[str, str, str, list, dict]:
    ui = str(user_input  or "").strip()[:1200]
    st = str(screen_text or "").strip()[:3000]
    ca = str(current_app or "").strip()[:200]
    h  = list(history or [])[-20:] if isinstance(history, (list, tuple)) else []
    # Handle memory being a string or invalid type gracefully
    if isinstance(memory, dict):
        m = memory
    else:
        try:
            import json
            m = json.loads(memory) if isinstance(memory, str) else {}
        except Exception:
            m = {}
    if not ui:
        raise ValueError("user_input is empty.")
    return ui, st, ca, h, m
