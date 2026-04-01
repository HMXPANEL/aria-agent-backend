
# AI Agent Brain - Full Stack Multi-Agent Backend

A production-ready, fully asynchronous multi-agent autonomous AI backend optimized for Render deployment. This system features a continuous cognition loop, advanced multi-layer memory, and a secure tool execution environment.

## 🚀 Key Features

- **Multi-Agent Architecture**: Specialized agents (Controller, Planner, Executor, Critic, Memory) collaborating to achieve complex goals.
- **Advanced Cognition Loop**: Implements a continuous **Observe-Think-Reason-Plan-Act-Observe-Reflect-Learn** loop.
- **Hybrid Memory System**: Uses **ChromaDB** for semantic long-term memory and **SQLite** for episodic and structured data.
- **Secure Tool System**: Sandboxed execution for Web, File, Shell, and Android control tools with a built-in safety layer.
- **Real-Time Android Control**: WebSocket-based screen streaming and command execution for remote Android device control.
- **Render Optimized**: Pre-configured `requirements.txt` and environment settings for seamless deployment on Render.

## 📁 Project Structure

```text
backend/
├── app/
│   ├── api/            # FastAPI routes and WebSocket handlers
│   ├── core/           # Core agent logic and task management
│   ├── models/         # Pydantic schemas and agent state
│   ├── services/       # External service integrations (LLM, Voice)
│   ├── tools/          # Tool registry and individual tool implementations
│   ├── utils/          # Logging and utility functions
│   ├── config.py       # Application configuration
│   └── main.py         # FastAPI application entry point
├── data/               # Persistent storage for SQLite and ChromaDB
├── sandbox/            # Restricted directory for file and shell operations
├── .env.example        # Template for environment variables
├── requirements.txt    # Pinned dependencies for production
└── README.md           # Project documentation
```

## 🛠️ Deployment on Render

1.  **Create a New Web Service**: Connect your repository to Render.
2.  **Environment Variables**: Add all variables from `.env.example` to the Render dashboard.
3.  **Build Command**: `pip install -r requirements.txt`
4.  **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5.  **Disk (Optional)**: For persistent memory, attach a Render Disk and update `SQLITE_DB_PATH` and `CHROMA_DB_PATH` to point to the mount path.

## 📱 Android Integration

The system includes a dedicated WebSocket endpoint at `/ws/device` for connecting an Android device. 
- **Secret Key**: Use the `ANDROID_WEBSOCKET_SECRET` for authentication.
- **Capabilities**: Supports real-time screen streaming (base64) and remote commands (tap, swipe, type, open_app).

## 📄 License

MIT License
=======
# ARIA v8 — Autonomous Android AI Agent Backend

**Production-grade autonomous AI agent backend** for controlling Android devices via structured JSON actions.

---

## What Was Fixed in v8

### Phase 1 — Critical Bug Fixes

| Bug | Fix Applied |
|---|---|
| `validate()` returned `None` on garbage input | Always returns `dict` with safe REPLY fallback |
| `run_agent()` crashed on unexpected input | Outer `try/except` in both `run_agent` and `handle_observation` |
| `sanitise()` crashed on `memory="{}"` (string) | Handles `str`, `dict`, `None` — parses JSON, falls back to `{}` |
| `plan_to_actions(None)` crash | `if not plan: return []` guard |
| `CLICK` with empty `text` param | Replaced with `WAIT(1)` in `guard_list()` |

### Phase 2 — Wrong Behaviour Fixed

| Problem | Fix |
|---|---|
| Unknown/garbage input (`@@@@`) opened Chrome | Last resort in planner now returns `REPLY` not browser |
| `search ai news` could route to wrong app | Search ALWAYS uses Chrome with address bar flow |
| `call mom` could use WhatsApp | `make_call` ALWAYS uses `com.android.dialer` — hardcoded |
| Multi-task only processed first task | ALL sub-tasks executed, ALL actions combined in one response |
| `send_message` had non-deterministic order | Strict locked order: OPEN→WAIT→SEARCH→TYPE→CLICK→TYPE→SEND |
| `keyword_fallback` opened random apps for unknown input | Returns `None` for unknown input, triggering safe REPLY |

### Phase 3 — Intelligence Upgrades

| Feature | Detail |
|---|---|
| TAP_XY added to WHITELIST | Full retry ladder: CLICK→SCROLL→WAIT→OCR_CLICK→TAP_XY |
| Dynamic `installed_apps` | Exact + fuzzy matching for any installed app |
| Greeting instant replies | 30 greetings resolved without LLM |
| Vision system | Screen analysis detects buttons, errors, loading state |
| Execution priority logged | PRIORITY 1 / 2 / 3 + FINAL ACTION in every log |
| MAX_LOOP_STEPS = 10 | Infinite loop protection in observation handler |

---

## Architecture

```
aria_v8/
├── .python-version          <- Python 3.11.9 (pins Render build)
├── requirements.txt
└── app/
    ├── config.py            <- 39 apps in APP_MAP, env vars, completion signals
    ├── main.py              <- FastAPI app, WebSocket + REST, all routes
    └── agent/
        ├── core.py          <- Full pipeline: deterministic → LLM → keyword
        ├── entities.py      <- Intent + entity extraction, ANY name/message
        ├── planner.py       <- Real mobile steps, think() engine, 3-arg select_model
        ├── executor.py      <- NVIDIA API client, retry + exponential backoff
        ├── prompt.py        <- Ultra-strict system prompt with worked examples
        ├── reflection.py    <- Self-correction: reflect() + replan()
        ├── validator.py     <- JSON repair + validation, NEVER returns None
        ├── memory.py        <- 3-tier memory: short_term, task, context
        ├── safety.py        <- Guard layer, CLICK empty text → WAIT
        └── vision.py        <- Screen state analysis, smart_click()
    ├── tasks/
    │   └── queue.py         <- Multi-task queue (sequential execution)
    └── realtime/
        └── websocket.py     <- WebSocket: Android connects once, continuous loop
```

---

## Execution Priority (in `core.py`)

```
1. DETERMINISTIC PLANNER   (no LLM, instant, most reliable)
2. LLM FALLBACK            (NVIDIA llama-3.1-70b or mixtral-8x7b)
3. KEYWORD FALLBACK        (guaranteed JSON, zero LLM dependency)
4. OUTER FAIL-SAFE         (catches any exception, returns REPLY)
```

---

## Deploy on Render

**Start command:**
```
uvicorn app.main:app --host 0.0.0.0 --port 10000
```

**Required environment variables:**
```
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxx
LLM_PROVIDER=nvidia
```

**Optional:**
```
MODEL_AGENT=meta/llama-3.1-70b-instruct
MODEL_CHAT=mistralai/mixtral-8x7b-instruct-v0.1
MAX_RETRIES=2
MAX_TOKENS=1024
TEMPERATURE=0.15
MAX_LOOP_STEPS=10
PORT=10000
```

---

## API Reference

### `POST /agent/run`

**Android input format:**
```json
{
  "user_input": "send hello to aman on whatsapp",
  "screen_text": "WhatsApp Chats",
  "current_app": "com.android.launcher",
  "session_id": "device-session-1",
  "installed_apps": [
    {"name": "chatgpt",  "package": "com.openai.chatgpt"},
    {"name": "capcut",   "package": "com.lemon.lvoverseas"}
  ]
}
```

**Output — multi-step action:**
```json
{
  "actions": [
    {"action": "OPEN_APP",  "params": {"package": "com.whatsapp"}},
    {"action": "WAIT",      "params": {"seconds": 2}},
    {"action": "CLICK",     "params": {"text": "Search"}},
    {"action": "TYPE",      "params": {"text": "Aman"}},
    {"action": "CLICK",     "params": {"text": "Aman"}},
    {"action": "TYPE",      "params": {"text": "hello"}},
    {"action": "CLICK",     "params": {"text": "Send"}}
  ]
}
```

### `POST /agent/observe`

Android calls this after executing each action:
```json
{
  "session_id": "device-session-1",
  "last_action": "OPEN_APP",
  "success": true,
  "screen_text": "WhatsApp Chats",
  "current_app": "com.whatsapp"
}
```

### `WebSocket /ws/{session_id}`

Real-time persistent connection. No HTTP polling needed.

**Android → Backend:**
```json
{"type": "task", "user_input": "send hi to aman", "screen_text": "...", "current_app": "..."}
{"type": "observe", "last_action": "CLICK", "success": true, "screen_text": "..."}
{"type": "ping"}
{"type": "disconnect"}
```

**Backend → Android:**
```json
{"type": "action",   "data": {"action": "OPEN_APP", "params": {"package": "..."}}}
{"type": "reply",    "text": "Hi there! How can I help?"}
{"type": "complete", "message": "Task completed successfully!"}
{"type": "pong"}
```

---

## Supported Actions

| Action | Required Params | Description |
|---|---|---|
| `OPEN_APP` | `package` | Open app by Android package name |
| `CLICK` | `text` | Tap element by visible text |
| `OCR_CLICK` | `text` | Tap via OCR fallback |
| `TAP_XY` | `x`, `y` | Tap by pixel coordinates |
| `TOUCH_XY` | `x`, `y` | Alias for TAP_XY |
| `TYPE` | `text` | Type into focused input |
| `SCROLL` | `direction` | up / down / left / right |
| `SWIPE_XY` | `x1`,`y1`,`x2`,`y2` | Swipe between two points |
| `LONG_PRESS` | `text` | Long press element |
| `BACK` | - | Android Back button |
| `HOME` | - | Android Home button |
| `WAIT` | `seconds` | Pause (1–10 seconds) |
| `SEARCH_CONTACT` | `name` | Search contact in messaging app |
| `SEARCH_WEB` | `query` | Browser web search |
| `SCREENSHOT` | - | Capture screen |
| `SPEAK` | `text` | TTS — say text aloud |
| `REPLY` | `text` | Text reply to user (chat/questions only) |

---

## Self-Healing Retry Ladder

When an action fails, the system automatically retries:

```
Retry 1:  SCROLL down + CLICK again
Retry 2:  WAIT(2s) + CLICK again
Retry 3:  OCR_CLICK (text-based OCR fallback)
Retry 4:  TAP_XY (coordinate fallback, center screen)
Retry 5+: REPLY with error message
```

---

## Key Behaviours Verified

| Input | Expected Output |
|---|---|
| `"hi"` | `REPLY: "Hi there! How can I help you?"` |
| `"open youtube"` | `OPEN_APP com.google.android.youtube` |
| `"open chatgpt"` (installed) | `OPEN_APP com.openai.chatgpt` |
| `"send hi to aman"` | 7-step WhatsApp flow |
| `"open youtube and send hi to aman"` | ALL actions combined in one response |
| `"call mom"` | Dialer app, TYPE mom, CLICK Call |
| `"search ai news"` | Chrome, address bar, TYPE query, CLICK Go |
| `"10+5*2"` | `REPLY: "20"` (deterministic math) |
| `"@@@@@@@@"` (broken) | `REPLY: "I didn't understand..."` |
| `"send message"` (no contact) | `REPLY: "Who should I send it to?"` |

---

## Termux / Android Install

```bash
# In Termux
cd ~/
unzip aria-agent-v8-final.zip
cd aria_v8

pip install -r requirements.txt

# Set env vars
export NVIDIA_API_KEY="nvapi-xxxx"
export LLM_PROVIDER="nvidia"

# Run
uvicorn app.main:app --host 0.0.0.0 --port 10000
```

---

## GitHub Push

```bash
git init
git add .
git commit -m "ARIA v8 - production-grade autonomous agent"
git branch -M main
git remote add origin https://TOKEN@github.com/USERNAME/aria-agent-v8.git
git push -u origin main
```
