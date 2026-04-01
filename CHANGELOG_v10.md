# ARIA v10 FINAL PRODUCTION — CHANGELOG

## v10.0.0 — FINAL PRODUCTION UPGRADE

All T1–T29 tests pass (123/123 assertions). Zero failures. Zero regressions.

---

### CORE CHANGES (core.py)

1. **Action Deduplication** (`_dedup_actions`)
   - Consecutive WAIT actions merged into one (max 10s)
   - Consecutive identical SCROLL direction → keep one
   - Consecutive identical OPEN_APP → keep one
   - Back-to-back identical TYPE of same value → keep one
   - Required WAIT after OPEN_APP always preserved (never consecutive)

2. **Multi-Task Always Wraps** (`{"actions": [...]}`)
   - Even a single action in multi-task context returns `{"actions": [action]}`
   - Strict task isolation: each sub-task uses its own fresh `extract()` result
   - No entity bleed between sub-tasks

3. **Intent Lock**
   - `_force_search_intent()` locks intent once after extraction
   - No subsequent code can override a locked search intent

4. **Observation App Sync**
   - After OPEN_APP in multi-task loop, `_current_app` is updated immediately
   - Prevents duplicate OPEN_APP for next sub-task in same sequence

5. **Fail-Safe Final Return** (Mandatory)
   - Every return path guarded: `if not result or not isinstance(result, dict)`
   - Returns `_SAFE_REPLY` instead of None or invalid structures

6. **Loop Prevention** (handle_observation)
   - If `retries >= 3`: stop, return `"I am unable to complete this task."`
   - `last_action` normalized to uppercase via `str(last_action).upper()`

---

### ENTITIES CHANGES (entities.py)

7. **Contact Normalization**
   - `_normalize_contact()`: `aman` / `AMAN` → `Aman` (Title Case enforced)
   - Applied before storage and before TYPE action

8. **Message Cleaning** (`_clean_message`)
   - Trim leading/trailing spaces
   - Collapse internal whitespace sequences
   - Prevents `"   hi   "` → `"hi"`

9. **Query Sanitization** (`_sanitize_query`)
   - Strips leading search-verb prefix: `"search for python"` → `"python"`
   - Strips: `search`, `search for`, `google`, `find`, `look up`, `browse`

10. **Duplicate Task Prevention**
    - `split_multi_tasks()` collapses exact-duplicate task strings
    - `"open youtube open youtube"` → one OPEN_APP, not two

---

### SAFETY CHANGES (safety.py)

11. **TYPE Empty String Blocked**
    - `guard_list()` now also blocks `TYPE` with empty `text` param
    - Previously only CLICK/OCR_CLICK were guarded this way

12. **Type Safety — Coordinates**
    - `guard_action()` coerces TAP_XY/TOUCH_XY `x`, `y` to `int`
    - Prevents string numbers like `"540"` from passing through

13. **WAIT Type Safety**
    - WAIT `seconds` always coerced via `int(float(str(...)))` — handles `"2"`, `2.0`

14. **Hardened `final_gate()`**
    - Added `not isinstance(result, dict)` guard at entry
    - Returns `_SAFE_REPLY` for None, non-dict, or structurally invalid results

---

### VALIDATOR CHANGES (validator.py)

15. **Action Normalization Layer**
    - `_normalize_action()`: always returns uppercase stripped string
    - `_normalize_params()`: always returns dict (replaces invalid types with `{}`)
    - `_coerce_types()`: WAIT → int seconds; TAP_XY/TOUCH_XY → int x/y

16. **Empty Action Rejection**
    - Empty string action names unconditionally rejected before whitelist check

---

### PLANNER CHANGES (planner.py)

17. **Intent Lock in Strategy**
    - `think()` derives strategy exclusively from locked intent
    - Screen-state adjustments only change strategy, never intent

18. **make_call Always Opens Dialer**
    - Even when `app` entity is None, dialer is always opened
    - Dialer package hardcoded: `com.android.dialer`

---

### MEMORY CHANGES (memory.py)

19. **`sync_current_app()`** (new)
    - Called after every OPEN_APP action in observation loop
    - Keeps `current_app` context in sync with device state

20. **Strict `recall_missing()` Isolation**
    - Hard early-return for `intent in ("general", "chat", "")`
    - Guarantees zero memory leak for junk/chat/general inputs

---

### PROMPT CHANGES (prompt.py)

21. **System Prompt Updated**
    - Rule 11: WAIT seconds must be integer (1-10)
    - Rule 12: Contact names must be Title Case
    - Version bumped to ARIA v10

---

### PRESERVED (unchanged, zero regressions)

- WebSocket flow (`websocket.py`) — untouched
- Task queue (`queue.py`) — untouched
- Vision system (`vision.py`) — untouched
- Reflection engine (`reflection.py`) — untouched
- LLM executor (`executor.py`) — untouched
- Greeting shortcuts — all instant replies preserved
- Math evaluation — sandboxed eval preserved
- Call flow — always dialer, never WhatsApp
- Search flow — always Chrome, address bar flow preserved
- Multi-turn pending — set/get/clear_pending preserved

---

### TEST RESULTS

```
✔ 123/123 PASSED — ARIA v10 FINAL VERIFIED
0 failures | 0 crashes | 0 invalid JSON
```
