# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Prompt Arena** — 2-player real-time prompt engineering battle game. Players submit prompts to an AI model; the better prompt (higher test-case accuracy + brevity bonus) wins.

Tech stack: FastAPI backend + Streamlit frontend + Upstage Solar API.

See `RULES.md` for branch naming, commit format, and team conventions.

## Commands

### Backend

All commands run from `backend/` with venv activated.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Run (loads .env automatically via python-dotenv if added, else set env vars manually)
python run.py
# or
uvicorn app.main:app --reload --port 8000

# Tests
pytest -q
pytest tests/test_game.py -q
pytest tests/test_game.py::test_normal_win -q
```

Swagger UI: `http://localhost:8000/docs`

### Frontend (Streamlit)

```powershell
cd frontend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

streamlit run app.py
```

Frontend runs on `http://localhost:8501` by default.

## Environment Setup

Copy `backend/.env` values or set manually:

| Variable | Value |
|----------|-------|
| `ARENA_AI_BACKEND` | `upstage` (prod) / `mock` (dev without key) |
| `UPSTAGE_API_KEY` | See `.env` (never commit) |
| `UPSTAGE_BASE_URL` | `https://api.upstage.ai/v1/solar` |
| `ARENA_TIME_LIMIT` | `180` |
| `ARENA_MAX_PROMPT_LENGTH` | `1200` |

Frontend env vars (in `frontend/.env`):

| Variable | Value |
|----------|-------|
| `BACKEND_URL` | `http://localhost:8000` |
| `WS_URL` | `ws://localhost:8000` |

## Architecture

### Request flow
```
REST:  Streamlit → HTTP → FastAPI router → RoomManager (in-memory)
WS:    Streamlit → WebSocket → arena/router.py → GameServer.handle_*()
```

### Backend singleton state
`app.state.server` is one `GameServer` instance at startup (`main.py:create_app`). Owns `RoomManager` (all rooms in memory, no DB). Routers access it via `app.core.deps.get_game_server`.

### Game state machine
```
WAITING → (2 players JOIN) → PLAYING → (both done) → [score] → RESULT/TIMEOUT
                                      → (disconnect)           → ERROR (forfeit)
```
`Room.lock` (asyncio.Lock) guards all state transitions.

### AI backend — Upstage Solar
- `ARENA_AI_BACKEND=upstage` → `UpstageAIClient` → `POST /v1/solar/chat/completions`
- Model: `solar-pro` (configured in `backend/app/arena/tasks.py:DEFAULT_MODEL`)
- System prompt = user's submitted prompt; user message = test case input
- N test cases called in parallel via `asyncio.gather` in `ai_client.grade()`
- `ARENA_AI_BACKEND=mock` → `MockAIClient` (deterministic, no API key needed)

### Scoring formula
`Score = 0.9 × (correct/N) + 0.1 × √(1 − (L/1200)²)` — rounded to 4 decimal places.
Forced-loss (timeout, over-length) → score 0, always loses.

### Frontend screens (MVP)
```
HomeScreen      → 방 생성 or 방 코드 입력
WaitingScreen   → 상대 대기 (WS WAITING event)
RoundScreen     → 과제 표시 + 프롬프트 작성 + 타이머 + 글자수
ResultScreen    → 승패 + 내/상대 점수 + 프롬프트 비교
```

### Frontend WebSocket flow
```python
# 연결 후 즉시 JOIN 전송
ws.send({"action": "JOIN"})

# 서버 이벤트 처리
ROUND_START → RoundScreen (task, time_limit)
WAITING     → 대기 메시지 표시
RESULT      → ResultScreen
TIMEOUT     → 자동 패배 표시
ERROR       → 오류 메시지 + 홈으로
```

## Key files

| File | Role |
|------|------|
| `backend/app/arena/game.py` | Game logic: JOIN/SUBMIT/disconnect/timeout/scoring |
| `backend/app/arena/scoring.py` | Scoring formula |
| `backend/app/arena/tasks.py` | Task pool + `DEFAULT_MODEL` |
| `backend/app/arena/ai_client.py` | AI abstraction + `grade()` (parallel calls) |
| `backend/app/rooms/domain.py` | `Room`, `Player`, `RoomManager`, `RoomStatus` |
| `backend/app/core/config.py` | `Settings` dataclass — all env vars |
| `backend/tests/conftest.py` | `FakeWebSocket`, `make_server()`, `make_scripted_ai()` |
| `frontend/app.py` | Streamlit entry point |
| `frontend/ws_client.py` | WebSocket client logic |

## Testing patterns

Tests use `fastapi.testclient.TestClient` (sync, works with async WS). Override `GameServer` attributes in tests:
- `server.time_limit` — set low (e.g. `1`) for timeout tests
- `server.task_override` — inject deterministic `Task`
- `server.ai_client` — inject `CallableAIClient` to control per-prompt answers

`FakeWebSocket` in conftest records `send_json` calls; use `.events`, `.has()`, `.last_of()`.

## WebSocket API quick reference

**Client → Server:**
```json
{ "action": "JOIN" }
{ "action": "SUBMIT", "prompt_text": "..." }
```

**Server → Client events:**
```
ROUND_START  { task, model, time_limit }
WAITING      { message }
RESULT       { result, winner_id, my_data, opponent_data }
TIMEOUT      { message, result: "LOSE" }
ERROR        { code, message, action_required }
```

WS endpoint: `ws://localhost:8000/ws/arena/{room_code}?client_id={uuid}`
Close codes: `4001` = missing client_id, `4004` = room unavailable
