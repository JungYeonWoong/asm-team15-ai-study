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
| `ARENA_DEFAULT_MODEL` | `solar-pro3` | 과제 풀 기본 모델명 |
| `ARENA_BANNED_WORDS` | `""` | 추가 금칙어 (콤마 구분) |
| `UPSTAGE_API_KEY` | `""` | Upstage Solar API 키 (`upstage` 사용 시) |
| `UPSTAGE_BASE_URL` | `https://api.upstage.ai/v1/solar` | Upstage API Base URL |
| `REDIS_URL` | `""` | Redis 세션 스토어 URL. 비어있으면 InMemory 폴백 |
| `SESSION_TTL_SECONDS` | `86400` | 세션 토큰 TTL (초) |

> 기본값(`mock`)은 API 키 없이 실행되는 결정론적 더미 AI 입니다. 실제 채점은
> `ARENA_AI_BACKEND=upstage` + `UPSTAGE_API_KEY` 설정 시 동작합니다.

## API 요약

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/auth/dev-login` | 개발용 즉시 로그인 (닉네임 선택) |
| POST | `/api/auth/login` | 닉네임 로그인 |
| POST | `/api/auth/logout` | Bearer 토큰 폐기 |
| POST | `/api/auth/social/{provider}` | OAuth stub (v1.1 예정) |
| GET | `/api/me` | 세션 확인 |
| GET | `/api/me/history` | 본인 최근 라운드 결과 |
| POST | `/api/rooms` | 방 생성 |
| GET | `/api/rooms/{room_code}` | 방 상태 조회 |
| GET | `/api/tasks` | 과제 풀 메타 (정답 비공개) |
| WS | `/ws/arena/{room_code}?client_id=` | 실시간 대전 |
| GET | `/healthz` | 서버/세션 스토어 상태 |

인증은 `Authorization: Bearer <token>` (auth 엔드포인트로 발급) 또는 기존 호환의
`X-Client-ID` UUID 헤더 중 하나로 제공한다. 정확한 요청/응답 및 이벤트 규격은
[`API_SPEC.md`](./API_SPEC.md) 를 참고.

## 빠른 사용 예 (curl)

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/auth/dev-login \
  -H 'content-type: application/json' -d '{"nickname":"host"}' | jq -r .token)

curl -s -X POST localhost:8000/api/rooms -H "Authorization: Bearer $TOKEN"
curl -s localhost:8000/api/tasks | jq '.[0]'
curl -s localhost:8000/healthz
```

## 테스트

```bash
pytest -q                            # 기본 (Mock + InMemory)
RUN_INTEGRATION=1 pytest -m integration   # 실제 Upstage API 호출 (1회)
```

## Redis 로 세션 스토어 띄우기 (선택)

기본은 InMemory 폴백이라 추가 설정 없이 동작한다. 다중 워커 / 재시작 내성이
필요하면 동봉된 `docker-compose.yml` 로 Redis 컨테이너를 띄운다.

```bash
docker compose up -d redis           # 컨테이너 기동
docker compose ps                    # healthy 확인
docker compose exec redis redis-cli ping  # PONG

# .env 에 다음 줄을 추가하거나 환경변수로 export
# REDIS_URL=redis://localhost:6379/0
python run.py

curl localhost:8000/healthz          # {"redis":"ok", ...} 확인
```

종료/정리:

```bash
docker compose down                  # 정지 (볼륨 유지)
docker compose down -v               # 정지 + 데이터까지 삭제
```
