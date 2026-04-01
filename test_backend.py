"""
test_backend.py — ARIA v9 FINAL PRODUCTION TEST SUITE

RULES:
  - NO mocking
  - NO patching internals
  - ONLY run_agent() and handle_observation()
  - Real Android-format payloads throughout
  - Full pipeline: input -> entities -> planner -> actions -> output
  - FAIL LOUDLY with exact output on any failure
  - FAIL_FAST = False to collect ALL failures before reporting

TARGET: 107+ assertions, 0 failures
"""
import asyncio
import json
import sys
import traceback

sys.path.insert(0, ".")

from app.agent.core import run_agent, handle_observation

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

PASS = 0
FAIL = 0
FAIL_FAST = False   # collect all failures, report at end


# ── Helpers ────────────────────────────────────────────────────────────────────

def log_section(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'='*65}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'='*65}{RESET}")


def log_input(p: dict) -> None:
    print(f"  {YELLOW}INPUT      →{RESET} {p['user_input']!r}")
    if p.get("current_app"):
        print(f"  {YELLOW}CURRENT_APP→{RESET} {p['current_app']!r}")
    if p.get("screen_text"):
        print(f"  {YELLOW}SCREEN     →{RESET} {p['screen_text'][:80]!r}")
    if p.get("installed_apps"):
        apps = [a["name"] for a in p["installed_apps"]]
        print(f"  {YELLOW}INST_APPS  →{RESET} {apps}")


def log_output(r: dict) -> None:
    if "actions" in r:
        print(f"  {CYAN}OUTPUT     →{RESET} multi-step ({len(r['actions'])} actions):")
        for i, a in enumerate(r["actions"]):
            p = a.get("params", {})
            detail = (p.get("package") or p.get("text") or
                      p.get("query") or p.get("direction") or "")
            print(f"               [{i+1}] {a['action']}  {detail!r}")
    else:
        a   = r.get("action", "?")
        p   = r.get("params", {})
        det = p.get("package") or (p.get("text", "")[:60]) or ""
        print(f"  {CYAN}OUTPUT     →{RESET} {a}  {det!r}")


def assert_fail(name: str, msg: str, r: dict) -> None:
    global FAIL
    FAIL += 1
    print(f"\n  {RED}{BOLD}FAIL: {name}{RESET}")
    print(f"  {RED}     REASON  : {msg}{RESET}")
    print(f"  {RED}     RESPONSE: {json.dumps(r, indent=4)}{RESET}")
    if FAIL_FAST:
        print(f"\n{RED}{BOLD}STOPPING (fail-fast){RESET}")
        sys.exit(1)


def assert_pass(name: str, detail: str = "") -> None:
    global PASS
    PASS += 1
    sfx = f"  ({detail})" if detail else ""
    print(f"  {GREEN}PASS{RESET}  {name}{sfx}")


def check(name: str, cond: bool, msg: str, r: dict, detail: str = "") -> None:
    if cond:
        assert_pass(name, detail)
    else:
        assert_fail(name, msg, r)


def get_all_actions(r: dict) -> list:
    if "actions" in r:
        return r["actions"]
    if "action" in r:
        return [{"action": r["action"], "params": r.get("params", {})}]
    return []


def has_action(r: dict, action_name: str, pkg: str = None, text: str = None) -> bool:
    for a in get_all_actions(r):
        if a.get("action") != action_name:
            continue
        p = a.get("params", {})
        if pkg  and pkg.lower()  not in str(p.get("package", "")).lower(): continue
        if text and text.lower() not in str(p.get("text", "")).lower():    continue
        return True
    return False


def payload(
    user_input:     str,
    screen_text:    str  = "",
    current_app:    str  = "",
    session_id:     str  = "e2e-test",
    installed_apps: list = None,
) -> dict:
    return {
        "user_input":     user_input,
        "screen_text":    screen_text,
        "current_app":    current_app,
        "session_id":     session_id,
        "history":        [],
        "memory":         {},
        "installed_apps": installed_apps or [],
    }


# ══════════════════════════════════════════════════════════════════════════════
async def run_all_tests() -> None:

    # ──────────────────────────────────────────────────────────────────────────
    # T1 — Greeting → REPLY only, no device action
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T1: Greeting — 'hi'")
    p = payload("hi", session_id="t1")
    log_input(p); r = await run_agent(**p); log_output(r)

    check("T1-a: not None",            r is not None,                         "None response",              r)
    check("T1-b: is dict",             isinstance(r, dict),                   "not a dict",                 r)
    check("T1-c: has action",          "action" in r or "actions" in r,       "missing action key",         r)
    check("T1-d: action=REPLY",        r.get("action") == "REPLY",            "not REPLY",                  r, r.get("action"))
    check("T1-e: no OPEN_APP",         not has_action(r, "OPEN_APP"),         "OPEN_APP on greeting",       r)
    check("T1-f: reply text nonempty", bool(r.get("params",{}).get("text")),  "empty reply text",           r)

    # ──────────────────────────────────────────────────────────────────────────
    # T2 — "hello" → REPLY, no OPEN_APP
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T2: Greeting — 'hello'")
    p = payload("hello", session_id="t2")
    log_input(p); r = await run_agent(**p); log_output(r)

    check("T2-a: action=REPLY",        r.get("action") == "REPLY",            "not REPLY",                  r)
    check("T2-b: no OPEN_APP",         not has_action(r, "OPEN_APP"),         "OPEN_APP on hello",          r)
    check("T2-c: reply nonempty",      bool(r.get("params",{}).get("text")),  "empty reply",                r)

    # ──────────────────────────────────────────────────────────────────────────
    # T3 — Open app → correct package
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T3: Open App — 'open youtube'")
    p = payload("open youtube", session_id="t3")
    log_input(p); r = await run_agent(**p); log_output(r)

    check("T3-a: has OPEN_APP",        has_action(r, "OPEN_APP"),             "no OPEN_APP",                r)
    check("T3-b: youtube package",     has_action(r, "OPEN_APP", pkg="youtube"), "wrong package",           r)
    check("T3-c: not chrome",          not has_action(r,"OPEN_APP",pkg="chrome"), "chrome opened for youtube",r)

    # ──────────────────────────────────────────────────────────────────────────
    # T4 — Open Instagram → com.instagram.android
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T4: Open App — 'open instagram'")
    p = payload("open instagram", session_id="t4")
    log_input(p); r = await run_agent(**p); log_output(r)

    check("T4-a: has OPEN_APP",        has_action(r, "OPEN_APP"),              "no OPEN_APP",               r)
    check("T4-b: instagram package",   has_action(r,"OPEN_APP",pkg="instagram"),"wrong package",            r)

    # ──────────────────────────────────────────────────────────────────────────
    # T5 — Dynamic installed app (ChatGPT)
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T5: Dynamic App — 'open chatgpt'")
    inst = [{"name": "ChatGPT", "package": "com.openai.chatgpt"},
            {"name": "CapCut",  "package": "com.lemon.lvoverseas"}]
    p = payload("open chatgpt", installed_apps=inst, session_id="t5")
    log_input(p); r = await run_agent(**p); log_output(r)

    check("T5-a: has OPEN_APP",        has_action(r, "OPEN_APP"),              "no OPEN_APP",               r)
    check("T5-b: chatgpt package",     has_action(r,"OPEN_APP",pkg="com.openai.chatgpt"), "wrong package",  r)
    check("T5-c: not youtube",         not has_action(r,"OPEN_APP",pkg="youtube"),"opened youtube",         r)

    # ──────────────────────────────────────────────────────────────────────────
    # T6 — Send message → full WhatsApp flow
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T6: Send Message — 'send hi to aman'")
    p = payload("send hi to aman", session_id="t6")
    log_input(p); r = await run_agent(**p); log_output(r)

    acts = get_all_actions(r)
    check("T6-a: multi-step",          "actions" in r,                         "not multi-step",            r)
    check("T6-b: >=5 actions",         len(acts) >= 5,                         f"{len(acts)} actions",      r)
    check("T6-c: OPEN_APP first",      acts and acts[0]["action"]=="OPEN_APP", "first not OPEN_APP",        r)
    check("T6-d: whatsapp package",    has_action(r,"OPEN_APP",pkg="whatsapp"),"wrong app",                 r)
    check("T6-e: WAIT after open",     len(acts)>1 and acts[1]["action"]=="WAIT","no WAIT after open",      r)
    check("T6-f: TYPE Aman",           has_action(r,"TYPE",text="Aman"),        "TYPE Aman missing",        r)
    check("T6-g: TYPE hi",             has_action(r,"TYPE",text="hi"),          "TYPE hi missing",          r)
    check("T6-h: CLICK Send",          has_action(r,"CLICK",text="Send"),       "CLICK Send missing",       r)
    check("T6-i: Send is last",
          acts and acts[-1]["action"]=="CLICK" and acts[-1].get("params",{}).get("text")=="Send",
          "Send not last action", r)
    check("T6-j: no dialer opened",    not has_action(r,"OPEN_APP",pkg="dialer"),"dialer opened",           r)
    check("T6-k: not chrome",          not has_action(r,"OPEN_APP",pkg="chrome"),"chrome opened for msg",   r)

    # ──────────────────────────────────────────────────────────────────────────
    # T7 — Send message to different contact
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T7: Send Message — 'send bye to riya'")
    p = payload("send bye to riya", session_id="t7")
    log_input(p); r = await run_agent(**p); log_output(r)

    check("T7-a: multi-step",          "actions" in r,                         "not multi-step",            r)
    check("T7-b: whatsapp",            has_action(r,"OPEN_APP",pkg="whatsapp"),"wrong app",                 r)
    check("T7-c: TYPE Riya",           has_action(r,"TYPE",text="Riya"),        "TYPE Riya missing",        r)
    check("T7-d: TYPE bye",            has_action(r,"TYPE",text="bye"),         "TYPE bye missing",         r)
    check("T7-e: CLICK Send",          has_action(r,"CLICK",text="Send"),       "CLICK Send missing",       r)

    # ──────────────────────────────────────────────────────────────────────────
    # T8 — Multi-task → ALL actions in ONE response
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T8: Multi-task — 'open youtube and send hi to aman'")
    p = payload("open youtube and send hi to aman", session_id="t8")
    log_input(p); r = await run_agent(**p); log_output(r)

    acts = get_all_actions(r)
    check("T8-a: has actions list",    "actions" in r,                         "not multi-step",            r)
    check("T8-b: >=6 actions",         len(acts) >= 6,                         f"{len(acts)} actions",      r)
    check("T8-c: youtube first",
          acts and acts[0]["action"]=="OPEN_APP" and "youtube" in acts[0].get("params",{}).get("package",""),
          "youtube not first", r)
    check("T8-d: whatsapp in list",    has_action(r,"OPEN_APP",pkg="whatsapp"), "no whatsapp",              r)
    check("T8-e: TYPE hi",             has_action(r,"TYPE",text="hi"),           "TYPE hi missing",         r)
    check("T8-f: CLICK Send",          has_action(r,"CLICK",text="Send"),        "CLICK Send missing",      r)
    check("T8-g: no chrome for msg",   not has_action(r,"OPEN_APP",pkg="chrome"),"chrome in multi-task",   r)

    # ──────────────────────────────────────────────────────────────────────────
    # T9 — Call → Dialer, NEVER WhatsApp
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T9: Call — 'call mom'")
    p = payload("call mom", session_id="t9")
    log_input(p); r = await run_agent(**p); log_output(r)

    check("T9-a: opens dialer",        has_action(r,"OPEN_APP",pkg="dialer"),   "dialer not opened",       r)
    check("T9-b: never whatsapp",      not has_action(r,"OPEN_APP",pkg="whatsapp"),"whatsapp opened",      r)
    check("T9-c: CLICK Call",          has_action(r,"CLICK",text="Call"),        "CLICK Call missing",     r)

    # ──────────────────────────────────────────────────────────────────────────
    # T10 — Search → Chrome ONLY, address bar flow
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T10: Search — 'search ai news'")
    p = payload("search ai news", session_id="t10")
    log_input(p); r = await run_agent(**p); log_output(r)

    acts = get_all_actions(r)
    check("T10-a: opens chrome",       has_action(r,"OPEN_APP",pkg="chrome"),   "chrome not opened",       r)
    check("T10-b: never whatsapp",     not has_action(r,"OPEN_APP",pkg="whatsapp"),"whatsapp for search",  r)
    check("T10-c: CLICK address bar",  has_action(r,"CLICK",text="address bar"),"no address bar click",    r)
    check("T10-d: TYPE query",         has_action(r,"TYPE"),                     "no TYPE",                 r)
    type_acts = [a for a in acts if a["action"]=="TYPE"]
    query_ok = any("ai" in a.get("params",{}).get("text","").lower() and
                   "news" in a.get("params",{}).get("text","").lower()
                   for a in type_acts)
    check("T10-e: query text correct", query_ok,                                "query text wrong",        r)
    check("T10-f: CLICK Go",           has_action(r,"CLICK",text="Go"),         "CLICK Go missing",        r)

    # ──────────────────────────────────────────────────────────────────────────
    # T11 — "google something" → Chrome (intent override)
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T11: Search — 'google latest news'")
    p = payload("google latest news", session_id="t11")
    log_input(p); r = await run_agent(**p); log_output(r)

    check("T11-a: opens chrome",       has_action(r,"OPEN_APP",pkg="chrome"),   "chrome not opened",       r)
    check("T11-b: never whatsapp",     not has_action(r,"OPEN_APP",pkg="whatsapp"),"whatsapp for search",  r)
    check("T11-c: TYPE query",         has_action(r,"TYPE"),                     "no TYPE",                 r)

    # ──────────────────────────────────────────────────────────────────────────
    # T12 — "find restaurants near me" → Chrome (find = search)
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T12: Search — 'find restaurants near me'")
    p = payload("find restaurants near me", session_id="t12")
    log_input(p); r = await run_agent(**p); log_output(r)

    check("T12-a: opens chrome",       has_action(r,"OPEN_APP",pkg="chrome"),   "chrome not opened",       r)
    check("T12-b: never whatsapp",     not has_action(r,"OPEN_APP",pkg="whatsapp"),"whatsapp opened",      r)
    check("T12-c: no dialer",          not has_action(r,"OPEN_APP",pkg="dialer"),"dialer for search",      r)

    # ──────────────────────────────────────────────────────────────────────────
    # T13 — Long search query → full query preserved, no split on 'and'
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T13: Long Search — 'search latest war between us and iran'")
    p = payload("search latest war between us and iran", session_id="t13")
    log_input(p); r = await run_agent(**p); log_output(r)

    acts = get_all_actions(r)
    check("T13-a: opens chrome",       has_action(r,"OPEN_APP",pkg="chrome"),   "chrome not opened",       r)
    type_acts = [a for a in acts if a["action"]=="TYPE"]
    full_q = any(
        "war" in a.get("params",{}).get("text","").lower() and
        "iran" in a.get("params",{}).get("text","").lower()
        for a in type_acts
    )
    check("T13-b: full query kept",    full_q,                                  "query truncated",         r)
    check("T13-c: CLICK Go",           has_action(r,"CLICK",text="Go"),         "CLICK Go missing",        r)

    # ──────────────────────────────────────────────────────────────────────────
    # T14 — Broken input: symbols only → REPLY, NO OPEN_APP
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T14: Broken Input — '@@@@@@@'")
    p = payload("@@@@@@@", session_id="t14")
    log_input(p); r = await run_agent(**p); log_output(r)

    check("T14-a: is dict",            isinstance(r, dict),                    "not dict",                  r)
    check("T14-b: action=REPLY",       r.get("action") == "REPLY",             "not REPLY",                 r)
    check("T14-c: no OPEN_APP",        not has_action(r,"OPEN_APP"),           "OPEN_APP on junk",          r)
    check("T14-d: reply nonempty",     bool(r.get("params",{}).get("text")),   "empty reply",               r)

    # ──────────────────────────────────────────────────────────────────────────
    # T15 — Broken input: repeated chars
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T15: Broken Input — 'aaaaaaa'")
    p = payload("aaaaaaa", session_id="t15")
    log_input(p); r = await run_agent(**p); log_output(r)

    check("T15-a: action=REPLY",       r.get("action") == "REPLY",             "not REPLY",                 r)
    check("T15-b: no OPEN_APP",        not has_action(r,"OPEN_APP"),           "OPEN_APP on repeat junk",   r)

    # ──────────────────────────────────────────────────────────────────────────
    # T16 — Broken input: exclamation symbols
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T16: Broken Input — '!!!!!!!'")
    p = payload("!!!!!!!", session_id="t16")
    log_input(p); r = await run_agent(**p); log_output(r)

    check("T16-a: action=REPLY",       r.get("action") == "REPLY",             "not REPLY",                 r)
    check("T16-b: no OPEN_APP",        not has_action(r,"OPEN_APP"),           "OPEN_APP on ! input",       r)

    # ──────────────────────────────────────────────────────────────────────────
    # T17 — Ambiguous/random → REPLY, never open any app
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T17: Safety — 'do something random'")
    p = payload("do something random", session_id="t17")
    log_input(p); r = await run_agent(**p); log_output(r)

    check("T17-a: action=REPLY",       r.get("action") == "REPLY",             "not REPLY for random",      r)
    check("T17-b: no OPEN_APP",        not has_action(r,"OPEN_APP"),           "OPEN_APP on vague cmd",     r)

    # ──────────────────────────────────────────────────────────────────────────
    # T18 — "just do it" → REPLY, never open any app
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T18: Safety — 'just do it'")
    p = payload("just do it", session_id="t18")
    log_input(p); r = await run_agent(**p); log_output(r)

    check("T18-a: action=REPLY",       r.get("action") == "REPLY",             "not REPLY",                 r)
    check("T18-b: no OPEN_APP",        not has_action(r,"OPEN_APP"),           "OPEN_APP on vague cmd",     r)

    # ──────────────────────────────────────────────────────────────────────────
    # T19 — Missing contact → ask who
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T19: Incomplete — 'send message on whatsapp'")
    p = payload("send message on whatsapp", session_id="t19")
    log_input(p); r = await run_agent(**p); log_output(r)

    check("T19-a: action=REPLY",       r.get("action") == "REPLY",             "not REPLY",                 r)
    reply_t = r.get("params",{}).get("text","").lower()
    check("T19-b: asks who",           "who" in reply_t or "send" in reply_t,  "didn't ask for contact",    r)

    # ──────────────────────────────────────────────────────────────────────────
    # T20 — Math → correct result
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T20: Math — '10+5*2'")
    p = payload("10+5*2", session_id="t20")
    log_input(p); r = await run_agent(**p); log_output(r)

    check("T20-a: action=REPLY",       r.get("action") == "REPLY",             "not REPLY",                 r)
    math_t = r.get("params",{}).get("text","")
    check("T20-b: result=20",          "20" in math_t,                         f"wrong: {math_t!r}",        r)

    # ──────────────────────────────────────────────────────────────────────────
    # T21 — Math 2
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T21: Math — '100/4'")
    p = payload("100/4", session_id="t21")
    log_input(p); r = await run_agent(**p); log_output(r)

    check("T21-a: action=REPLY",       r.get("action") == "REPLY",             "not REPLY",                 r)
    check("T21-b: result=25",          "25" in r.get("params",{}).get("text",""), "wrong math result",      r)

    # ──────────────────────────────────────────────────────────────────────────
    # T22 — Observer loop: CLICK fail → self-healing
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T22: Observe — CLICK failure self-healing")
    setup = payload("send hi to aman", session_id="obs-test-22")
    await run_agent(**setup)
    obs = {
        "session_id": "obs-test-22",
        "last_action": "CLICK",
        "success": False,
        "screen_text": "no button found",
        "current_app": "com.whatsapp",
        "error_message": "element not found",
        "installed_apps": [],
    }
    r = await handle_observation(**obs)
    log_output(r)

    check("T22-a: is dict",            isinstance(r, dict),                    "not dict",                  r)
    check("T22-b: has action",         "action" in r or "actions" in r,        "missing key",               r)
    has_heal = has_action(r,"SCROLL") or has_action(r,"WAIT") or has_action(r,"OCR_CLICK")
    check("T22-c: self-heal action",   has_heal,                               "no self-heal action",       r)

    # ──────────────────────────────────────────────────────────────────────────
    # T23 — search_web intent must NEVER route to WhatsApp in any scenario
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T23: Search Safety — 'search python tutorial'")
    p = payload("search python tutorial", session_id="t23")
    log_input(p); r = await run_agent(**p); log_output(r)

    check("T23-a: opens chrome",       has_action(r,"OPEN_APP",pkg="chrome"),  "chrome not opened",         r)
    check("T23-b: NOT whatsapp",       not has_action(r,"OPEN_APP",pkg="whatsapp"), "whatsapp for search",  r)
    check("T23-c: NOT youtube",        not has_action(r,"OPEN_APP",pkg="youtube"),  "youtube for search",   r)
    check("T23-d: NOT instagram",      not has_action(r,"OPEN_APP",pkg="instagram"),"instagram for search", r)

    # ──────────────────────────────────────────────────────────────────────────
    # T24 — Search with 'look up' phrasing
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T24: Search — 'look up best android phones 2025'")
    p = payload("look up best android phones 2025", session_id="t24")
    log_input(p); r = await run_agent(**p); log_output(r)

    check("T24-a: opens chrome",       has_action(r,"OPEN_APP",pkg="chrome"),  "chrome not opened",         r)
    check("T24-b: not whatsapp",       not has_action(r,"OPEN_APP",pkg="whatsapp"),"whatsapp for search",   r)

    # ──────────────────────────────────────────────────────────────────────────
    # T25 — Already in app → no redundant OPEN_APP, get WAIT or continue
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T25: Already In App — 'open youtube' when youtube running")
    p = payload("open youtube",
                current_app="com.google.android.youtube",
                session_id="t25")
    log_input(p); r = await run_agent(**p); log_output(r)

    # Should not open youtube again (already inside) → REPLY or WAIT
    acts = get_all_actions(r)
    open_youtube = [a for a in acts
                    if a["action"]=="OPEN_APP"
                    and "youtube" in a.get("params",{}).get("package","")]
    check("T25-a: no duplicate open",  len(open_youtube) == 0,
          "opened youtube when already inside", r)

    # ──────────────────────────────────────────────────────────────────────────
    # T26 — Memory safety: broken input after valid session MUST NOT inherit app
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T26: Memory Safety — junk after real task")
    # First do a valid task to set memory
    p_real = payload("send hello to alice", session_id="memsafe-26")
    await run_agent(**p_real)
    # Now send junk — must NOT open whatsapp or any app
    p_junk = payload("@@@", session_id="memsafe-26")
    log_input(p_junk); r = await run_agent(**p_junk); log_output(r)

    check("T26-a: REPLY on junk",      r.get("action") == "REPLY",             "not REPLY",                 r)
    check("T26-b: no OPEN_APP",        not has_action(r,"OPEN_APP"),           "OPEN_APP from memory leak", r)

    # ──────────────────────────────────────────────────────────────────────────
    # T27 — Memory safety: general intent after session MUST NOT open last app
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T27: Memory Safety — vague cmd after valid task")
    p_real = payload("open instagram", session_id="memsafe-27")
    await run_agent(**p_real)
    p_vague = payload("do something", session_id="memsafe-27")
    log_input(p_vague); r = await run_agent(**p_vague); log_output(r)

    check("T27-a: REPLY",              r.get("action") == "REPLY",             "not REPLY",                 r)
    check("T27-b: no OPEN_APP",        not has_action(r,"OPEN_APP"),           "OPEN_APP from memory leak", r)

    # ──────────────────────────────────────────────────────────────────────────
    # T28 — Valid JSON always: every response must be parseable
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T28: JSON Validity — multiple responses")
    tests_28 = [
        "search python",
        "open maps",
        "call dad",
        "send test to bob",
        "hi",
        "@@@",
        "do whatever",
    ]
    for i, inp in enumerate(tests_28):
        p = payload(inp, session_id=f"json-{i}")
        r = await run_agent(**p)
        try:
            json.dumps(r)
            parseable = True
        except Exception:
            parseable = False
        check(f"T28-{chr(ord('a')+i)}: JSON valid for {inp!r}", parseable, "not serialisable", r)
        check(f"T28-{chr(ord('a')+i)}-key: has action/actions for {inp!r}",
              "action" in r or "actions" in r, "missing key", r)

    # ──────────────────────────────────────────────────────────────────────────
    # T29 — No action is ever empty string
    # ──────────────────────────────────────────────────────────────────────────
    log_section("T29: Action names non-empty")
    for i, inp in enumerate(["send hi to riya", "open chrome", "search dogs", "call mom"]):
        p = payload(inp, session_id=f"nonempty-{i}")
        r = await run_agent(**p)
        for act in get_all_actions(r):
            check(f"T29-{i}: action name nonempty in {inp!r}",
                  bool(str(act.get("action","")).strip()),
                  f"empty action in {inp!r}", r)

    # ──────────────────────────────────────────────────────────────────────────
    # SUMMARY
    # ──────────────────────────────────────────────────────────────────────────
    total = PASS + FAIL
    print(f"\n{BOLD}{'='*65}{RESET}")
    if FAIL == 0:
        print(f"{GREEN}{BOLD}  ✔ {total}/{total} PASSED — ARIA v9 FINAL VERIFIED{RESET}")
    else:
        print(f"{RED}{BOLD}  ❌ {FAIL} FAILED / {total} TOTAL — FIX REQUIRED{RESET}")
    print(f"{BOLD}{'='*65}{RESET}\n")
    return FAIL == 0


if __name__ == "__main__":
    print(f"\n{BOLD}ARIA v9 — FINAL PRODUCTION TEST SUITE{RESET}")
    print("NO mocking. Full pipeline only. run_agent() and handle_observation().\n")
    try:
        ok = asyncio.run(run_all_tests())
        sys.exit(0 if ok else 1)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
