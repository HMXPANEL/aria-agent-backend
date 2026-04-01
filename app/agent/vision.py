"""
agent/vision.py - Vision system for live screen understanding.

Analyzes screen_text and optional base64 screenshot to:
  - Detect visible UI elements (buttons, inputs, lists)
  - Suggest the best next action based on current screen state
  - Enable OCR fallback when text matching fails
  - Adapt actions to actual UI instead of fixed assumptions
"""
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("vision")

# Common UI element patterns detected from screen_text
_SEND_BTN     = re.compile(r"\b(send|submit|post|share)\b", re.I)
_SEARCH_BTN   = re.compile(r"\b(search|find|magnif)\b", re.I)
_INPUT_FIELD  = re.compile(r"\b(type|message|enter|write|compose|reply)\b", re.I)
_CALL_BTN     = re.compile(r"\b(call|dial|video call|voice)\b", re.I)
_BACK_SIGNAL  = re.compile(r"\b(back|return|close)\b", re.I)
_SCROLL_HINT  = re.compile(r"\b(scroll|more|load|see more)\b", re.I)
_ERROR_SIG    = re.compile(r"\b(error|failed|not found|unable|retry|crash|stopped)\b", re.I)
_SUCCESS_SIG  = re.compile(r"\b(sent|delivered|done|success|complete|tick|check)\b", re.I)
_LOADING_SIG  = re.compile(r"\b(loading|please wait|connecting|syncing)\b", re.I)
_PERMISSION   = re.compile(r"\b(allow|deny|permission|grant|block)\b", re.I)


class ScreenAnalysis:
    """
    Result of analyzing a screen state.
    Contains detected elements and recommended actions.
    """

    def __init__(
        self,
        screen_text: str,
        current_app: str,
        goal: str = "",
    ):
        self.screen_text = (screen_text or "").strip()
        self.screen_lower = self.screen_text.lower()
        self.current_app = current_app or ""
        self.goal        = goal or ""

        self.has_send_button    = bool(_SEND_BTN.search(self.screen_text))
        self.has_search_bar     = bool(_SEARCH_BTN.search(self.screen_text))
        self.has_input_field    = bool(_INPUT_FIELD.search(self.screen_text))
        self.has_call_button    = bool(_CALL_BTN.search(self.screen_text))
        self.has_error          = bool(_ERROR_SIG.search(self.screen_text))
        self.has_success        = bool(_SUCCESS_SIG.search(self.screen_text))
        self.is_loading         = bool(_LOADING_SIG.search(self.screen_text))
        self.needs_permission   = bool(_PERMISSION.search(self.screen_text))
        self.needs_scroll       = bool(_SCROLL_HINT.search(self.screen_text))

    def element_visible(self, text: str) -> bool:
        """Returns True if a UI element text is visible on screen."""
        return text.lower() in self.screen_lower

    def smart_click(self, target_text: str) -> Dict[str, Any]:
        """
        Returns the best action to tap a target element.
        Uses CLICK if visible, OCR_CLICK as fallback, SCROLL if not found.
        """
        if self.element_visible(target_text):
            return {"action": "CLICK", "params": {"text": target_text}}
        logger.info(f"[VISION] '{target_text}' not visible -> OCR_CLICK fallback")
        return {"action": "OCR_CLICK", "params": {"text": target_text}}

    def get_next_action_hint(self) -> Optional[Dict[str, Any]]:
        """
        Suggests the most sensible next action based purely on screen state.
        Returns None if no strong signal detected.
        """
        # Handle permission dialogs immediately
        if self.needs_permission:
            logger.info("[VISION] Permission dialog detected -> CLICK Allow")
            return {"action": "CLICK", "params": {"text": "Allow"}}

        # Handle loading screen
        if self.is_loading:
            logger.info("[VISION] Loading detected -> WAIT")
            return {"action": "WAIT", "params": {"seconds": 2}}

        # If error detected, suggest scrolling or replanning
        if self.has_error:
            logger.info("[VISION] Error on screen -> SCROLL to find alternative")
            return {"action": "SCROLL", "params": {"direction": "up"}}

        return None

    def describe(self) -> str:
        """Returns a short human-readable description of the screen state."""
        parts = []
        if self.has_send_button:  parts.append("send button visible")
        if self.has_search_bar:   parts.append("search bar visible")
        if self.has_input_field:  parts.append("input field visible")
        if self.has_error:        parts.append("error message present")
        if self.has_success:      parts.append("success indicator present")
        if self.is_loading:       parts.append("loading in progress")
        if self.needs_permission: parts.append("permission dialog")
        if not parts:
            return "no notable UI elements detected"
        return ", ".join(parts)


def analyze(
    screen_text: str,
    current_app: str,
    goal: str = "",
    screenshot_b64: Optional[str] = None,
) -> ScreenAnalysis:
    """
    Analyzes current screen state and returns a ScreenAnalysis object.
    screenshot_b64 is accepted for future vision model integration
    but screen_text analysis is the primary mechanism.
    """
    analysis = ScreenAnalysis(screen_text, current_app, goal)
    logger.info(
        f"[VISION] app={current_app!r} | {analysis.describe()}"
    )
    return analysis


def extract_clickable_elements(screen_text: str) -> List[str]:
    """
    Extracts likely clickable element labels from screen_text.
    Returns list of potential tap targets.
    """
    if not screen_text:
        return []
    elements = []
    lines = screen_text.strip().split("\n")
    for line in lines:
        line = line.strip()
        if 1 < len(line) < 40:
            elements.append(line)
    return elements[:20]


def build_ui_context(
    screen_text: str,
    current_app: str,
    goal: str = "",
) -> str:
    """
    Builds a compact UI context string for injection into LLM prompts.
    Summarizes what's visible on screen.
    """
    analysis = analyze(screen_text, current_app, goal)
    elements = extract_clickable_elements(screen_text)
    ctx_parts = [
        f"Screen state: {analysis.describe()}",
        f"App: {current_app or 'unknown'}",
    ]
    if elements:
        ctx_parts.append(f"Visible elements: {', '.join(elements[:8])}")
    return " | ".join(ctx_parts)
