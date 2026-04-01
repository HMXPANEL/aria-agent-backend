"""agent/reflection.py - Self-correction and dynamic replanning."""
import logging
from typing import Any, Dict, List

from app.agent.executor  import call_llm
from app.agent.prompt    import build_reflection_prompt, build_replan_prompt, get_system_prompt
from app.agent.validator import validate, is_fallback
from app.config          import MAX_RETRIES

logger = logging.getLogger("reflection")

_SAFE: Dict[str, Any] = {
    "action": "REPLY",
    "params": {"text": "I couldn't complete that. Please try again."},
}


async def reflect(
    model: str, goal: str,
    bad_raw: str, error: str, screen: str = "",
) -> Dict[str, Any]:
    """Retry with corrective prompt. Always returns a valid dict."""
    sys = get_system_prompt()
    cur_bad, cur_err = bad_raw, error

    for i in range(1, MAX_RETRIES + 1):
        logger.warning(f"[REFLECT] attempt {i}/{MAX_RETRIES} err={cur_err!r}")
        prompt = build_reflection_prompt(goal, cur_bad, cur_err, screen)
        try:
            raw = await call_llm(model=model, system_prompt=sys, user_message=prompt)
        except RuntimeError as e:
            cur_err = str(e)
            cur_bad = ""
            continue
        result = validate(raw)
        if not is_fallback(result):
            logger.info(f"[REFLECT] Recovered on attempt {i}")
            return result
        cur_bad = raw
        cur_err = "Still a fallback REPLY."

    logger.error(f"[REFLECT] Exhausted {MAX_RETRIES} retries.")
    return _SAFE.copy()


async def replan(
    model: str, goal: str,
    failed_plan: List[str], reason: str,
    screen: str, entities: Dict[str, Any],
) -> Dict[str, Any]:
    """Dynamic replan when original plan fails."""
    logger.warning(f"[REPLAN] goal={goal!r}")
    sys    = get_system_prompt()
    prompt = build_replan_prompt(goal, failed_plan, reason, screen, entities)
    try:
        raw = await call_llm(model=model, system_prompt=sys, user_message=prompt)
    except RuntimeError:
        return _SAFE.copy()
    result = validate(raw)
    if not is_fallback(result):
        logger.info("[REPLAN] New plan generated.")
        return result
    return await reflect(
        model=model, goal=goal, bad_raw=raw,
        error="Replan output invalid.", screen=screen,
    )
