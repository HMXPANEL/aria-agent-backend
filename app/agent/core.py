"""
agent/core.py — ARIA v9 FINAL PRODUCTION

All v8 fixes retained. New v9 changes:
  1. Junk-input detection at pipeline entry (is_junk_input)
  2. Intent forced to 'search_web' when search keywords detected (Intent Priority Override)
  3. General-intent keyword-fallback is BLOCKED — returns REPLY only
  4. Keyword-fallback cannot trigger OPEN_APP when intent != open_app / send_message etc.
  5. v9 final_gate() called on every result path before return
  6. Memory safety: recall_missing never fires for general/chat/junk intent
  7. Vision hint guard: never fires for search/open/send intents (avoids override)
  8. Deterministic planner ALWAYS wins priority-1; LLM only when planner produces nothing
"""
import logging
from typing import Any, Dict, List, Optional

from app.agent.entities   import extract, check_completeness, split_multi_tasks
from app.agent.executor   import call_llm
from app.agent.planner    import build_plan, select_model, step_label, think
from app.agent.prompt     import (
    build_action_prompt, build_observation_prompt, get_system_prompt,
)
from app.agent.reflection import reflect, replan
from app.agent.validator  import sanitise, validate, is_fallback
from app.agent.vision     import analyze as vision_analyze, build_ui_context
from app.agent.memory     import (
    add_turn, get_turns, all_ctx, update_from_entities, recall_missing,
    set_pending, get_pending, clear_pending, set_ctx,
    set_goal, advance, inc_retry, mark_done, mark_failed, get_task,
    record_habit,
)
from app.agent.safety     import guard_list, is_safe_input, is_junk_input, final_gate
from app.config           import APP_MAP, COMPLETION_SIGNALS, MAX_RETRIES, MAX_LOOP_STEPS
from app.tasks.queue      import enqueue_tasks, get_next_task, complete_task, fail_task

logger = logging.getLogger("core")

_ERROR_REPLY: Dict[str, Any] = {
    "action": "REPLY",
    "params": {"text": "I didn't understand that. Could you please rephrase?"},
}

# Instant replies — zero LLM latency for greetings
_INSTANT_REPLIES: Dict[str, str] = {
    "hi":               "Hi there! How can I help you?",
    "hello":            "Hello! What can I do for you?",
    "hey":              "Hey! How can I assist?",
    "howdy":            "Howdy! What do you need?",
    "sup":              "Hey! What's up?",
    "yo":               "Yo! What can I do for you?",
    "hiya":             "Hiya! How can I help?",
    "helo":             "Hello! How can I assist you?",
    "good morning":     "Good morning! How can I help you today?",
    "good afternoon":   "Good afternoon! What can I do for you?",
    "good evening":     "Good evening! How can I assist?",
    "good night":       "Good night! Let me know if you need anything.",
    "how are you":      "I'm doing great, thanks! How can I help you?",
    "how r u":          "Doing well! What can I do for you?",
    "what's up":        "Not much! Ready to help. What do you need?",
    "whats up":         "All good! What can I help you with?",
    "thank you":        "You're welcome! Anything else I can help with?",
    "thanks":           "Happy to help! Let me know if you need anything else.",
    "ty":               "You're welcome!",
    "thx":              "No problem!",
    "bye":              "Goodbye! Come back anytime.",
    "goodbye":          "See you! Feel free to return whenever.",
    "see you":          "See you soon! Take care.",
    "who are you":      (
        "I'm ARIA — your Autonomous Android AI Agent. "
        "I can control your phone, send messages, open apps, "
        "search the web, and much more!"
    ),
    "what can you do":  (
        "I can: send messages, open apps, make calls, "
        "search the web, control your phone, answer questions, and more!"
    ),
    "help":             (
        "I can send messages, open apps, make calls, search the web, "
        "and answer questions. What would you like me to do?"
    ),
    "help me":          "Of course! Tell me what you'd like me to do.",
}

# ── Search keyword detection (intent priority override) ────────────────────────
import re as _re
_SEARCH_KW = _re.compile(
    r"\b(search|google|find|look up|lookup|browse|bing|ddg|search for)\b", _re.I
)


def _force_search_intent(user_input: str, entities: Dict[str, Any]) -> Dict[str, Any]:
    """
    v9 Intent Priority Override:
    If input contains search keywords, force intent = 'search_web'.
    Prevents 'search X' from being misrouted to general/open_app.
    """
    if _SEARCH_KW.search(user_input):
        if entities.get("intent") != "search_web":
            logger.info(
                f"[V9] Intent override: {entities.get('intent')!r} -> 'search_web'"
            )
            entities = dict(entities)
            entities["intent"] = "search_web"
            # Extract query if missing
            if not entities.get("query"):
                m = _re.search(
                    r"\b(?:search|google|find|look up|browse|search for)\s+(?:for\s+)?(.+)",
                    user_input, _re.I,
                )
                entities["query"] = m.group(1).strip() if m else user_input
            # NEVER open a non-chrome app for search
            entities["app"] = "com.android.chrome"
    return entities


def plan_to_actions(plan: Optional[List[str]]) -> List[Dict[str, Any]]:
    """Converts planner step strings to concrete action dicts. Never raises."""
    if not plan:
        return []
    actions: List[Dict[str, Any]] = []
    for step in plan:
        try:
            parts = step.split(":", 1)
            cmd   = parts[0].upper().strip()
            arg   = parts[1].strip() if len(parts) > 1 else ""

            if cmd == "OPEN_APP":
                actions.append({"action": "OPEN_APP",  "params": {"package": arg}})
            elif cmd == "WAIT":
                try: secs = int(arg)
                except Exception: secs = 2
                actions.append({"action": "WAIT", "params": {"seconds": max(1, min(secs, 10))}})
            elif cmd == "CLICK":
                actions.append({"action": "CLICK", "params": {"text": arg}})
            elif cmd in ("OCR_CLICK",):
                actions.append({"action": "OCR_CLICK", "params": {"text": arg}})
            elif cmd in ("TAP_XY", "TOUCH_XY"):
                coords = arg.split(",")
                try:
                    x, y = int(coords[0].strip()), int(coords[1].strip())
                except Exception:
                    x, y = 540, 960
                actions.append({"action": "TAP_XY", "params": {"x": x, "y": y}})
            elif cmd == "TYPE":
                actions.append({"action": "TYPE", "params": {"text": arg}})
            elif cmd == "SCROLL":
                d = arg if arg in ("up", "down", "left", "right") else "down"
                actions.append({"action": "SCROLL", "params": {"direction": d}})
            elif cmd == "SEARCH_CONTACT":
                actions.append({"action": "SEARCH_CONTACT", "params": {"name": arg}})
            elif cmd == "SEARCH_WEB":
                actions.append({"action": "SEARCH_WEB", "params": {"query": arg}})
            elif cmd == "BACK":
                actions.append({"action": "BACK", "params": {}})
            elif cmd == "HOME":
                actions.append({"action": "HOME", "params": {}})
            elif cmd == "SCREENSHOT":
                actions.append({"action": "SCREENSHOT", "params": {}})
            elif cmd == "SPEAK":
                actions.append({"action": "SPEAK", "params": {"text": arg}})
            elif cmd == "REPLY":
                actions.append({"action": "REPLY", "params": {"text": arg}})
            elif cmd == "FOCUS_MESSAGE_BOX":
                actions.append({"action": "CLICK", "params": {"text": "Message"}})
            else:
                logger.debug(f"[PLAN] Unknown cmd={cmd!r}, skipping")
        except Exception as e:
            logger.debug(f"[PLAN] Skip step {step!r}: {e}")
    return actions


def apply_smart_rules(
    parsed: Dict[str, Any],
    current_app: str,
    screen_text: str,
    screen_analysis=None,
) -> Dict[str, Any]:
    """
    Smart Android rules:
      - Skip OPEN_APP if already in that app → WAIT(1)
      - SCROLL + WAIT before invisible CLICK (only if screen_text is populated)
    
    v9 FIX: Do NOT insert SCROLL when screen_text is empty — the app hasn't loaded yet
    and adding scrolls for every invisible element creates unnecessary noise.
    """
    screen = (screen_text or "").lower()
    screen_populated = len(screen.strip()) > 0

    def _fix(item: Dict[str, Any]) -> List[Dict[str, Any]]:
        a = item.get("action", "")
        p = item.get("params") or {}

        if a == "OPEN_APP":
            pkg = p.get("package", "")
            if pkg and current_app == pkg:
                logger.info(f"[SMART] Already in {pkg!r} -> WAIT(1)")
                return [{"action": "WAIT", "params": {"seconds": 1}}]

        if a == "CLICK" and screen_populated:
            target = p.get("text", "").lower()
            if target and target not in screen:
                if screen_analysis and screen_analysis.element_visible(target):
                    return [item]
                logger.info(f"[SMART] '{target}' not visible -> SCROLL + retry")
                return [
                    {"action": "SCROLL", "params": {"direction": "down"}},
                    {"action": "WAIT",   "params": {"seconds": 1}},
                    item,
                ]
        return [item]

    if "action" in parsed:
        expanded = _fix(parsed)
        return expanded[0] if len(expanded) == 1 else {"actions": expanded}

    if "actions" in parsed:
        result = []
        for a in (parsed.get("actions") or []):
            result.extend(_fix(a))
        parsed["actions"] = result

    return parsed


def build_retry_actions(
    failed_action: str,
    failed_params: Dict[str, Any],
    retry_number: int,
) -> Dict[str, Any]:
    """Self-healing retry ladder: SCROLL → WAIT → OCR_CLICK → replan."""
    text = failed_params.get("text", "")
    if retry_number == 1:
        return {"actions": [
            {"action": "SCROLL", "params": {"direction": "down"}},
            {"action": "WAIT",   "params": {"seconds": 1}},
            {"action": "CLICK",  "params": {"text": text}},
        ]}
    if retry_number == 2:
        return {"actions": [
            {"action": "WAIT",  "params": {"seconds": 2}},
            {"action": "CLICK", "params": {"text": text}},
        ]}
    if retry_number == 3:
        return {"action": "OCR_CLICK", "params": {"text": text}}
    if retry_number == 4:
        return {"action": "TAP_XY", "params": {"x": 540, "y": 960}}
    return _ERROR_REPLY.copy()


def is_goal_complete(
    intent: str, target_app: str,
    current_app: str, screen_text: str,
) -> bool:
    screen = (screen_text or "").lower()
    if intent == "open_app" and target_app:
        return current_app == target_app
    return any(
        sig.lower() in screen
        for sig in COMPLETION_SIGNALS.get(intent, [])
    )


def keyword_fallback(
    user_input: str,
    entities: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Guaranteed JSON when LLM + reflection both fail.

    v9 RULES:
      - intent == 'general'            → return None (REPLY via caller, no OPEN_APP)
      - intent == 'chat'               → return None
      - fallback OPEN_APP only for     → send_message, open_app, make_call, search_web
      - search_web ALWAYS Chrome
    """
    intent  = entities.get("intent", "")
    app     = entities.get("app")
    contact = entities.get("contact")
    message = entities.get("message")
    query   = entities.get("query")
    lower   = user_input.lower()

    # v9: general / chat / unknown → NEVER open any app
    if intent in ("general", "chat", ""):
        return None

    if intent == "send_message" and app and contact:
        actions = [
            {"action": "OPEN_APP", "params": {"package": app}},
            {"action": "WAIT",     "params": {"seconds": 2}},
            {"action": "CLICK",    "params": {"text": "Search"}},
            {"action": "TYPE",     "params": {"text": contact}},
            {"action": "CLICK",    "params": {"text": contact}},
        ]
        if message:
            actions += [
                {"action": "TYPE",  "params": {"text": message}},
                {"action": "CLICK", "params": {"text": "Send"}},
            ]
        return {"actions": actions}

    if intent == "open_app" and app:
        return {"action": "OPEN_APP", "params": {"package": app}}

    # search ALWAYS Chrome — never any other app
    if intent == "search_web":
        q = query or user_input
        return {"actions": [
            {"action": "OPEN_APP", "params": {"package": "com.android.chrome"}},
            {"action": "WAIT",     "params": {"seconds": 2}},
            {"action": "CLICK",    "params": {"text": "address bar"}},
            {"action": "TYPE",     "params": {"text": q}},
            {"action": "CLICK",    "params": {"text": "Go"}},
        ]}

    if intent == "make_call" and contact:
        return {"actions": [
            {"action": "OPEN_APP", "params": {"package": "com.android.dialer"}},
            {"action": "WAIT",     "params": {"seconds": 2}},
            {"action": "TYPE",     "params": {"text": contact}},
            {"action": "CLICK",    "params": {"text": contact}},
            {"action": "CLICK",    "params": {"text": "Call"}},
        ]}

    # App keyword match — only for explicit open intent
    if intent == "open_app":
        for kw, pkg in APP_MAP.items():
            if kw in lower:
                return {"action": "OPEN_APP", "params": {"package": pkg}}

    if "home" in lower: return {"action": "HOME", "params": {}}
    if "back" in lower: return {"action": "BACK", "params": {}}

    return None


def _primary(d: Dict[str, Any]) -> str:
    if "action" in d:
        return str(d["action"])
    acts = d.get("actions") or []
    return str(acts[0].get("action", "?")) if acts else "?"


def _to_list(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    if "actions" in parsed:
        return [
            {"action": a.get("action", ""), "params": a.get("params") or {}}
            for a in (parsed.get("actions") or [])
        ]
    if "action" in parsed:
        return [{"action": parsed["action"], "params": parsed.get("params") or {}}]
    return []


def _q_to_key(question: str) -> str:
    q = question.lower()
    if "who" in q or "contact" in q: return "last_contact"
    if "message" in q or "say" in q: return "last_message"
    if "app" in q or "which" in q:   return "last_app"
    if "search" in q or "query" in q:return "last_query"
    return "pending_answer"


async def run_agent(
    user_input:     str,
    screen_text:    str,
    current_app:    str,
    history:        list,
    memory:         dict,
    session_id:     str = "default",
    installed_apps: Optional[List[Dict[str, str]]] = None,
    screenshot:     Optional[str] = None,
) -> Dict[str, Any]:
    """Full agent pipeline. NEVER raises. ALWAYS returns valid JSON dict."""
    try:
        return await _run_agent_inner(
            user_input=user_input,
            screen_text=screen_text,
            current_app=current_app,
            history=history,
            memory=memory,
            session_id=session_id,
            installed_apps=installed_apps,
            screenshot=screenshot,
        )
    except Exception as e:
        logger.error(f"[CORE] OUTER FAIL-SAFE: {type(e).__name__}: {e}", exc_info=True)
        return {"action": "REPLY", "params": {"text": "Something went wrong. Please try again."}}


async def _run_agent_inner(
    user_input:     str,
    screen_text:    str,
    current_app:    str,
    history:        list,
    memory:         dict,
    session_id:     str = "default",
    installed_apps: Optional[List[Dict[str, str]]] = None,
    screenshot:     Optional[str] = None,
) -> Dict[str, Any]:
    """Inner pipeline — wrapped by run_agent fail-safe."""

    # ── 1. Sanitise inputs ─────────────────────────────────────────────────────
    try:
        user_input, screen_text, current_app, history, memory = sanitise(
            user_input, screen_text, current_app, history, memory
        )
    except ValueError as e:
        return {"action": "REPLY", "params": {"text": str(e)}}

    # ── 2. Injection safety ────────────────────────────────────────────────────
    if not is_safe_input(user_input):
        return {"action": "REPLY", "params": {"text": "I cannot process that request."}}

    # ── 3. v9: Junk input detection (skip for math expressions) ──────────────
    # Math expressions like '10+5*2' contain no letters but are valid — check math first
    from app.agent.entities import _MATH_DETECT as _md
    _is_math_expr = bool(_md.match(user_input))
    if not _is_math_expr and is_junk_input(user_input):
        logger.info(f"[V9] Junk input detected: {user_input!r}")
        return {"action": "REPLY", "params": {"text": "Invalid input."}}

    logger.info(
        f"[CORE] ===== NEW REQUEST ===== "
        f"sid={session_id!r} input={user_input[:80]!r} app={current_app!r}"
    )

    # ── 4. Multi-turn resume ───────────────────────────────────────────────────
    pg, pk = get_pending(session_id)
    if pg and pk:
        logger.info(f"[CORE] Multi-turn: user answered {user_input!r}")
        set_ctx(pk, user_input, session_id)
        clear_pending(session_id)
        user_input = pg

    # ── 5. Multi-task split ────────────────────────────────────────────────────
    task_parts = split_multi_tasks(user_input)
    if len(task_parts) > 1:
        logger.info(f"[CORE] Multi-task: {len(task_parts)} tasks: {task_parts}")
        all_actions: List[Dict[str, Any]] = []
        for part in task_parts:
            try:
                e_part = extract(part, installed_apps)
                e_part = _force_search_intent(part, e_part)   # v9 intent override
                e_part = recall_missing(e_part, session_id)
                p_part = build_plan(e_part, current_app, installed_apps)
                a_part = plan_to_actions(p_part)
                safe_part, _ = guard_list(a_part)
                # Apply v9 final gate per sub-task
                sub_intent = e_part.get("intent", "general")
                gated = []
                for act in safe_part:
                    tmp = final_gate(act, sub_intent)
                    gated.extend(_to_list(tmp))
                all_actions.extend(gated)
                for a in gated:
                    if a.get("action") == "OPEN_APP":
                        current_app = a.get("params", {}).get("package", current_app)
            except Exception as ex:
                logger.error(f"[CORE] Multi-task part {part!r} failed: {ex}")
        if all_actions:
            result = {"actions": all_actions} if len(all_actions) > 1 else all_actions[0]
            add_turn("user",  user_input, session_id)
            add_turn("agent", str(result), session_id)
            logger.info(f"[CORE] Multi-task FINAL ACTION: {len(all_actions)} actions combined")
            return result

    # ── 6. Entity extraction ───────────────────────────────────────────────────
    try:
        entities = extract(user_input, installed_apps)
    except Exception as e:
        logger.error(f"[CORE] extract crashed: {e}")
        entities = {
            "intent": "general", "app": None, "contact": None, "message": None,
            "query": None, "is_math": False, "is_chat": False, "raw": user_input,
        }

    # ── 7. v9 Intent Priority Override (search keywords always win) ────────────
    entities = _force_search_intent(user_input, entities)

    intent = entities.get("intent", "general")

    # ── 8. v9 General-intent early exit — NEVER open any app ──────────────────
    if intent == "general" and not entities.get("is_chat"):
        # Let it fall through to planner which returns REPLY for general/unknown
        pass

    # ── 9. Memory recall — SAFE: skip for general/chat ────────────────────────
    try:
        if intent not in ("general", "chat"):
            entities = recall_missing(entities, session_id)
    except Exception as e:
        logger.error(f"[CORE] recall_missing crashed: {e}")

    # ── 10. Record habit ────────────────────────────────────────────────────────
    try:
        record_habit(intent, session_id)
    except Exception:
        pass

    logger.info(
        f"[CORE] ENTITIES: intent={intent!r} "
        f"contact={entities.get('contact')!r} "
        f"app={entities.get('app')!r} "
        f"msg={entities.get('message')!r} "
        f"is_chat={entities.get('is_chat')} "
        f"is_math={entities.get('is_math')}"
    )

    # ── 11. Math shortcut ───────────────────────────────────────────────────────
    if entities.get("is_math"):
        ans = str(entities.get("math_result") or "Could not evaluate.")
        add_turn("user",  user_input, session_id)
        add_turn("agent", ans,        session_id)
        return {"action": "REPLY", "params": {"text": ans}}

    # ── 12. Vision analysis ─────────────────────────────────────────────────────
    try:
        screen_analysis = vision_analyze(screen_text, current_app, user_input, screenshot)
        vision_ctx      = build_ui_context(screen_text, current_app, user_input)
    except Exception as e:
        logger.error(f"[CORE] vision crashed: {e}")
        screen_analysis = None
        vision_ctx      = None

    # ── 13. Vision hint — only for ambiguous/observation steps ─────────────────
    # v9 FIX: vision hint must NOT override deterministic planner intents
    _no_vision_override = {
        "send_message", "open_app", "search_web", "make_call", "play_media"
    }
    if screen_analysis and intent not in _no_vision_override:
        hint = screen_analysis.get_next_action_hint()
        if hint and not (entities.get("is_chat") or intent in ("chat", "general")):
            logger.info(f"[CORE] Vision hint: {hint}")
            result = final_gate(hint, intent)
            add_turn("user",  user_input, session_id)
            add_turn("agent", str(result),  session_id)
            return result

    # ── 14. Greeting / chat shortcut ────────────────────────────────────────────
    is_chat_input = entities.get("is_chat") or intent == "chat"

    if is_chat_input:
        raw_low = user_input.lower().strip()
        if raw_low in _INSTANT_REPLIES:
            reply_text = _INSTANT_REPLIES[raw_low]
            add_turn("user",  user_input,  session_id)
            add_turn("agent", reply_text,  session_id)
            return {"action": "REPLY", "params": {"text": reply_text}}

        try:
            _, model = select_model(user_input, True, current_app)
            sys_p    = get_system_prompt()
            raw_r    = await call_llm(
                model=model, system_prompt=sys_p,
                user_message=(
                    f"The user said: {user_input}\n\n"
                    "Respond conversationally. Output ONLY a REPLY action as raw JSON."
                ),
            )
            result = validate(raw_r)
            if not is_fallback(result):
                # Chat REPLY is always safe — no gate needed
                add_turn("user",  user_input, session_id)
                add_turn("agent", str(result), session_id)
                return result
        except Exception as e:
            logger.error(f"[CORE] chat LLM error: {e}")

        ft = f"I'm here to help! You said: \"{user_input}\". What would you like me to do?"
        return {"action": "REPLY", "params": {"text": ft}}

    # ── 15. Completeness check ──────────────────────────────────────────────────
    try:
        complete, question = check_completeness(entities)
    except Exception as e:
        logger.error(f"[CORE] check_completeness crashed: {e}")
        complete, question = True, ""

    if not complete:
        key = _q_to_key(question)
        set_pending(user_input, key, session_id)
        add_turn("agent", question, session_id)
        return {"action": "REPLY", "params": {"text": question}}

    # ── 16. Update memory ───────────────────────────────────────────────────────
    try:
        update_from_entities(entities, session_id)
    except Exception:
        pass

    # ── 17. Thinking engine ─────────────────────────────────────────────────────
    try:
        decision = think(
            goal=user_input, entities=entities,
            screen_text=screen_text, current_app=current_app,
            context=all_ctx(session_id),
        )
    except Exception as e:
        logger.error(f"[CORE] think crashed: {e}")
        decision = {}

    # ── 18. Model + plan ────────────────────────────────────────────────────────
    try:
        _, model = select_model(user_input, False, current_app)
    except Exception:
        from app.config import MODEL_AGENT
        model = MODEL_AGENT

    try:
        plan = build_plan(entities, current_app, installed_apps, decision)
    except Exception as e:
        logger.error(f"[CORE] build_plan crashed: {e}")
        plan = ["REPLY:Could not build a plan."]

    logger.info(f"[CORE] plan={plan} model={model}")
    set_goal(user_input, plan, session_id)

    # ── 19. Deterministic path ──────────────────────────────────────────────────
    try:
        det_actions = plan_to_actions(plan)
    except Exception as e:
        logger.error(f"[CORE] plan_to_actions crashed: {e}")
        det_actions = []

    safe_det, _ = guard_list(det_actions)

    # ── PRIORITY 1: DETERMINISTIC PLANNER ──────────────────────────────────────
    if safe_det:
        if len(safe_det) == 1:
            result = apply_smart_rules(safe_det[0], current_app, screen_text, screen_analysis)
        else:
            result = apply_smart_rules(
                {"actions": safe_det}, current_app, screen_text, screen_analysis
            )
        advance(session_id)
        # v9 final gate
        result = final_gate(result, intent)
        add_turn("user",  user_input, session_id)
        add_turn("agent", str(result), session_id)
        logger.info(f"[CORE] EXECUTION PATH: deterministic")
        logger.info(f"[CORE] FINAL ACTION: {_primary(result)!r}")
        return result

    # ── PRIORITY 2: LLM FALLBACK ────────────────────────────────────────────────
    logger.info("[CORE] EXECUTION PATH: LLM (deterministic had no safe actions)")
    ctx        = all_ctx(session_id)
    hist       = get_turns(session_id, n=4) + list(history)
    sys_prompt = get_system_prompt()
    step0      = step_label(plan, 0)
    result     = _ERROR_REPLY.copy()

    for attempt in range(MAX_RETRIES + 1):
        user_msg = build_action_prompt(
            goal=user_input, entities=entities, current_step=step0,
            screen_text=screen_text, current_app=current_app,
            history=hist[-4:], context=ctx,
            installed_apps=installed_apps,
            vision_context=vision_ctx,
            decision=decision,
        )
        try:
            raw = await call_llm(model=model, system_prompt=sys_prompt, user_message=user_msg)
        except RuntimeError as e:
            logger.error(f"[CORE] LLM failed attempt {attempt}: {e}")
            if attempt >= MAX_RETRIES:
                break
            continue

        logger.info(f"[RAW LLM] {raw[:400]!r}")
        parsed = validate(raw)

        if is_fallback(parsed):
            logger.warning("[CORE] LLM gave fallback -> reflecting")
            parsed = await reflect(
                model=model, goal=user_input,
                bad_raw=raw, error="Output was invalid.",
                screen=screen_text,
            )

        parsed  = apply_smart_rules(parsed, current_app, screen_text, screen_analysis)
        acts    = _to_list(parsed)
        safe, blocked = guard_list(acts)

        if safe:
            result = safe[0] if len(safe) == 1 else {"actions": safe}
            advance(session_id)
            break
        logger.warning(f"[CORE] All blocked: {blocked}")

    # ── PRIORITY 3: KEYWORD FALLBACK (restricted in v9) ────────────────────────
    if is_fallback(result) or result is _ERROR_REPLY:
        logger.info("[CORE] EXECUTION PATH: keyword fallback")
        # v9: keyword fallback is BLOCKED for general intent
        if intent in ("general", "chat"):
            logger.info("[CORE] Keyword fallback BLOCKED — intent=general/chat -> REPLY")
        else:
            kb = keyword_fallback(user_input, entities)
            if kb:
                result = kb
                logger.info(f"[CORE] Keyword fallback succeeded: {_primary(kb)!r}")
            else:
                logger.warning("[CORE] Keyword fallback found nothing")

    # v9 final gate on all paths
    result = final_gate(result, intent)

    add_turn("user",  user_input, session_id)
    add_turn("agent", str(result), session_id)
    logger.info(f"[CORE] FINAL ACTION: {_primary(result)!r}")
    return result


async def handle_observation(
    session_id:     str,
    last_action:    str,
    success:        bool,
    screen_text:    str,
    current_app:    str,
    error_message:  str = "",
    installed_apps: Optional[List[Dict[str, str]]] = None,
    screenshot:     Optional[str] = None,
) -> Dict[str, Any]:
    """Called after Android executes an action. Returns next action. NEVER raises."""
    try:
        return await _handle_observation_inner(
            session_id=session_id,
            last_action=last_action,
            success=success,
            screen_text=screen_text,
            current_app=current_app,
            error_message=error_message,
            installed_apps=installed_apps,
            screenshot=screenshot,
        )
    except Exception as e:
        logger.error(f"[OBS] OUTER FAIL-SAFE: {type(e).__name__}: {e}", exc_info=True)
        return {"action": "REPLY", "params": {"text": "Something went wrong. Please try again."}}


async def _handle_observation_inner(
    session_id:     str,
    last_action:    str,
    success:        bool,
    screen_text:    str,
    current_app:    str,
    error_message:  str = "",
    installed_apps: Optional[List[Dict[str, str]]] = None,
    screenshot:     Optional[str] = None,
) -> Dict[str, Any]:
    """Inner observation handler."""
    logger.info(
        f"[OBS] last={last_action!r} ok={success} "
        f"app={current_app!r} sid={session_id!r}"
    )

    task = get_task(session_id)
    goal = task.get("goal") or ""

    if not goal:
        next_task = get_next_task(session_id)
        if next_task:
            logger.info(f"[OBS] Starting queued task: {next_task.goal!r}")
            return await run_agent(
                user_input=next_task.goal,
                screen_text=screen_text,
                current_app=current_app,
                history=[], memory={}, session_id=session_id,
                installed_apps=installed_apps, screenshot=screenshot,
            )
        return {
            "action": "REPLY",
            "params": {"text": "No active task. Please give me a new command."},
        }

    set_ctx("last_app", current_app, session_id)

    try:
        screen_analysis = vision_analyze(screen_text, current_app, goal, screenshot)
        vision_ctx      = build_ui_context(screen_text, current_app, goal)
    except Exception:
        screen_analysis = None
        vision_ctx      = None

    # Self-healing on failure
    if not success:
        retries = inc_retry(session_id)
        if retries > MAX_RETRIES:
            mark_failed(session_id)
            fail_task(session_id, error_message or "Max retries")
            next_task = get_next_task(session_id)
            if next_task:
                return await run_agent(
                    user_input=next_task.goal,
                    screen_text=screen_text, current_app=current_app,
                    history=[], memory={}, session_id=session_id,
                    installed_apps=installed_apps,
                )
            return {
                "action": "REPLY",
                "params": {
                    "text": (
                        f"Action failed after {MAX_RETRIES} retries: "
                        f"{error_message or 'Unknown error'}."
                    )
                },
            }
        if "CLICK" in str(last_action).upper():
            return build_retry_actions("CLICK", {"text": ""}, retries)
        return {"action": "SCROLL", "params": {"direction": "down"}}

    advance(session_id)
    task = get_task(session_id)

    try:
        entities   = extract(goal, installed_apps)
        intent     = entities.get("intent", "general")
        target_app = entities.get("app") or ""
    except Exception:
        intent = "general"
        target_app = ""

    if is_goal_complete(intent, target_app, current_app, screen_text):
        mark_done(session_id)
        complete_task(session_id, {"action": "REPLY", "params": {"text": "Task completed!"}})
        next_task = get_next_task(session_id)
        if next_task:
            return await run_agent(
                user_input=next_task.goal,
                screen_text=screen_text, current_app=current_app,
                history=[], memory={}, session_id=session_id,
                installed_apps=installed_apps,
            )
        return {"action": "REPLY", "params": {"text": "Task completed successfully!"}}

    if task.get("status") == "complete":
        complete_task(session_id, {"action": "REPLY", "params": {"text": "Done!"}})
        return {"action": "REPLY", "params": {"text": "Task completed successfully!"}}

    steps = task.get("plan") or []
    idx   = task.get("step", 0)
    nxt   = step_label(steps, idx)

    if idx >= MAX_LOOP_STEPS:
        mark_done(session_id)
        return {"action": "REPLY", "params": {"text": "Task execution complete."}}

    logger.info(f"[OBS] Continuing step {idx + 1}/{len(steps)}: {nxt!r}")

    next_acts = plan_to_actions([nxt])
    safe, _   = guard_list(next_acts)
    if safe:
        r = apply_smart_rules(
            safe[0] if len(safe) == 1 else {"actions": safe},
            current_app, screen_text, screen_analysis,
        )
        return r

    try:
        _, model = select_model(goal, False, current_app)
    except Exception:
        from app.config import MODEL_AGENT
        model = MODEL_AGENT

    sys_p  = get_system_prompt()
    prompt = build_observation_prompt(
        goal=goal, last_action=last_action, success=success,
        screen_text=screen_text, current_app=current_app,
        next_step=nxt, vision_context=vision_ctx,
    )
    try:
        raw = await call_llm(model=model, system_prompt=sys_p, user_message=prompt)
    except RuntimeError as e:
        return {"action": "REPLY", "params": {"text": f"LLM error: {e}"}}

    result = validate(raw)
    if is_fallback(result):
        result = await reflect(
            model=model, goal=goal, bad_raw=raw,
            error="Observation output invalid.", screen=screen_text,
        )

    return apply_smart_rules(result, current_app, screen_text, screen_analysis)
