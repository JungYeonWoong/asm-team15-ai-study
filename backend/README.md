# Prompt Arena — Backend (FastAPI)

`prompt_arena_api_spec.md` 의 MVP 대전 흐름(방 생성 → 매칭 → 대전 → 결과)을
FastAPI 로 구현한 백엔드입니다.

## 기능별 패키지 구조

```
backend/
├─ app/
│  ├─ main.py            # FastAPI 진입점 (라우터 조립)
│  ├─ core/              # 공용: 설정, 의존성
│  │  ├─ config.py       #   Settings (환경 변수)
│  │  └─ deps.py         #   GameServer 의존성 주입
│  ├─ session/           # [기능] 세션 확인  GET /api/me
│  │  ├─ router.py
│  │  └─ schemas.py
│  ├─ rooms/             # [기능] 방 생성/조회  /api/rooms
│  │  ├─ router.py
│  │  ├─ schemas.py
│  │  └─ domain.py       #   Room, Player, RoomManager, RoomStatus
│  └─ arena/             # [기능] WebSocket 대전  /ws/arena/{room_code}
│     ├─ router.py       #   WS 엔드포인트 + 연결 거부
│     ├─ game.py         #   GameServer (라운드 오케스트레이션)
│     ├─ domain.py       #   Task, TestCase, RoundResult, PlayerResult
│     ├─ scoring.py      #   채점 수식
│     ├─ ai_client.py    #   AI 모델 호출(Upstage/Mock/Callable) + 채점
│     └─ tasks.py        #   사전 정의 과제 풀
├─ tests/                # pytest (24 케이스)
├─ requirements.txt
├─ pytest.ini
└─ run.py                # 개발 서버 실행
```

## 빠른 시작

### 1. 가상환경 + 의존성

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # (bash: source .venv/Scripts/activate)
pip install -r requirements.txt
```

### 2. 서버 실행

```powershell
python run.py
# 또는
uvicorn app.main:app --reload --port 8000
```

- Base URL: `http://localhost:8000`
- Swagger 문서: `http://localhost:8000/docs`

### 3. 테스트

```powershell
pytest -q
```

## 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `ARENA_TIME_LIMIT` | `180` | 프롬프트 작성 제한 시간(초) |
| `ARENA_MAX_PROMPT_LENGTH` | `1200` | 프롬프트 최대 글자 수 |
| `ARENA_AI_MAX_RETRIES` | `3` | AI 호출 재시도 횟수 |
| `ARENA_AI_BACKEND` | `mock` | `mock` \| `upstage` |
| `UPSTAGE_API_KEY` | `""` | Upstage Solar API 키 (`upstage` 사용 시) |
| `UPSTAGE_BASE_URL` | `https://api.upstage.ai/v1/solar` | Upstage API Base URL |

> 기본값(`mock`)은 API 키 없이 실행되는 결정론적 더미 AI 입니다. 실제 채점은
> `ARENA_AI_BACKEND=upstage` + `UPSTAGE_API_KEY` 설정 시 동작합니다.

## API 요약

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/me` | 세션 확인 |
| POST | `/api/rooms` | 방 생성 |
| GET | `/api/rooms/{room_code}` | 방 상태 조회 |
| WS | `/ws/arena/{room_code}?client_id=` | 실시간 대전 |

정확한 요청/응답 및 이벤트 규격은 [`API_SPEC.md`](./API_SPEC.md) 를 참고하세요.
