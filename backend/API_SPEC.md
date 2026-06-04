# Prompt Arena — API 명세서 (구현 정합본)

> **버전:** v1.1-MVP (구현 반영)
> **최종 수정:** 2026-06
> **범위:** 인증·대전 전체 흐름 (로그인 → 방 생성 → 매칭 → 대전 → 결과 → 기록)
> **기준:** 본 문서는 `backend/` 의 실제 FastAPI 구현과 1:1로 일치하도록 정리한
> 명세입니다. 원본 요구 명세를 기준으로 하되, 구현 결정에 맞춰 기술합니다.

---

## 공통 사항

| 항목 | 내용 |
|------|------|
| Base URL | `http://localhost:8000` |
| 인증 방식 | `Authorization: Bearer <token>` 우선 / `X-Client-ID` 폴백 (MVP 호환) |
| 데이터 형식 | JSON |
| 문자 인코딩 | UTF-8 |
| Swagger | `GET /docs` |

**인증 헤더 우선순위**

1. `Authorization: Bearer <token>` — 로그인으로 발급된 세션 토큰 사용
2. `X-Client-ID` — 프론트엔드가 생성한 UUID (Bearer 없을 때 폴백, MVP 호환)

두 헤더가 모두 없으면 `400`, Bearer 토큰이 있으나 만료/무효이면 `401`.

---

## REST API

### 1. 세션 확인 — `GET /api/me`

현재 클라이언트의 세션 상태를 확인합니다.

**Request Headers**

| 헤더 | 필수 | 설명 |
|------|------|------|
| `Authorization` | △ | `Bearer <token>` (로그인 토큰 우선) |
| `X-Client-ID` | △ | 프론트엔드가 생성한 UUID (Bearer 없을 때 폴백) |

`Authorization` 또는 `X-Client-ID` 중 하나 이상 필요.

**Response (200 OK)**

```json
{
  "client_id": "u_abc123def456...",
  "status": "active",
  "nickname": "player1",
  "provider": "nickname"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `client_id` | String | 인증된 사용자 ID (Bearer 기반: `u_<hash16>`, X-Client-ID: UUID 그대로) |
| `status` | String | 항상 `"active"` |
| `nickname` | String\|null | 로그인 닉네임 (X-Client-ID 폴백이면 `null`) |
| `provider` | String\|null | `"dev"` / `"nickname"` / `"client-id"` |

**에러**

| 상태코드 | 사유 |
|----------|------|
| `400` | 두 헤더 모두 누락 |
| `401` | Bearer 토큰 만료/무효 |

---

### 2. 방 생성 — `POST /api/rooms`

방을 만든 사람이 호스트가 되고, 호스트는 즉시 멤버로 등록되어
`current_players` 가 1이 됩니다.

**Request Headers**

| 헤더 | 필수 | 설명 |
|------|------|------|
| `Authorization` | △ | `Bearer <token>` |
| `X-Client-ID` | △ | 프론트엔드가 생성한 UUID (폴백) |

**Request Body** — 없음

**Response (201 Created)**

```json
{
  "room_code": "1234",
  "status": "WAITING",
  "current_players": 1,
  "created_by": "u_abc123..."
}
```

- `room_code`: 4자리 숫자 문자열 (`"0000"`~`"9999"`), 서버가 중복 없이 발급.

**에러**

| 상태코드 | 사유 |
|----------|------|
| `400` | 인증 헤더 누락 |
| `401` | Bearer 토큰 만료/무효 |
| `409` | 이미 (종료되지 않은) 다른 방에 참여 중인 클라이언트 |

---

### 3. 방 상태 조회 — `GET /api/rooms/{room_code}`

WebSocket 연결 전, 방이 입장 가능한지 사전 확인합니다. 인증 헤더 불필요.

**Path Parameters**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `room_code` | String | 조회할 방 코드 |

**Response (200 OK)**

```json
{ "room_code": "1234", "status": "WAITING", "current_players": 1 }
```

**`status` 값 정의**

| 값 | 설명 |
|----|------|
| `WAITING` | 1명 대기 중, 입장 가능 |
| `FULL` | 2명 모두 입장(예약), 대기 중 |
| `PLAYING` | 게임 진행 중, 입장 불가 |
| `CLOSED` | 종료된 방 |

**에러**

| 상태코드 | 사유 |
|----------|------|
| `404` | 존재하지 않는 방 코드 |

> 구현 노트: 방이 종료되면 즉시 저장소에서 제거되므로, 종료된 방 코드 조회는
> 실질적으로 `404` 로 응답합니다.

---

### 4. 인증 — `POST /api/auth/*`

로그인 후 발급된 토큰을 이후 요청에서 `Authorization: Bearer <token>` 으로 전달합니다.

#### 4.1 개발용 즉시 로그인 — `POST /api/auth/dev-login`

어떤 입력이든 거부하지 않는 개발용 엔드포인트입니다.

**Request Body** (선택)

```json
{ "nickname": "원하는닉네임" }
```

닉네임을 생략하면 `dev-XXXXXX` 형태로 자동 부여됩니다.

**Response (200 OK)**

```json
{
  "token": "랜덤32바이트urlsafe",
  "user_id": "u_abc123def456...",
  "nickname": "dev-a1b2c3",
  "provider": "dev"
}
```

**에러**

| 상태코드 | 사유 |
|----------|------|
| `400` | 요청 형식 오류 |

#### 4.2 닉네임 로그인 — `POST /api/auth/login`

**Request Body**

```json
{ "nickname": "player1" }
```

닉네임 형식: 2~20자 영문/숫자/한글/`_`/`-`. 동일 닉네임은 동일 `user_id` 로 매핑됩니다 (결정론적).

**Response (200 OK)**

```json
{
  "token": "랜덤32바이트urlsafe",
  "user_id": "u_abc123def456...",
  "nickname": "player1",
  "provider": "nickname"
}
```

**에러**

| 상태코드 | 사유 |
|----------|------|
| `400` | 닉네임 누락 또는 형식 불일치 |

#### 4.3 로그아웃 — `POST /api/auth/logout`

Bearer 토큰을 폐기합니다. 토큰이 없거나 만료여도 항상 성공으로 응답합니다.

**Request Headers**

| 헤더 | 필수 | 설명 |
|------|------|------|
| `Authorization` | △ | `Bearer <token>` |

**Response (200 OK)**

```json
{ "status": "ok" }
```

#### 4.4 소셜 로그인 — `POST /api/auth/social/{provider}`

| Path | 설명 |
|------|------|
| `provider` | `google`, `kakao` 등 |

v1.1 구현 예정. 현재는 라우트만 노출합니다.

**Response**

`501 Not Implemented`

---

### 5. 결과 기록 조회 — `GET /api/me/history`

본인의 최근 라운드 결과를 최신순으로 반환합니다. 인증 필요.

**Query Parameters**

| 파라미터 | 기본값 | 범위 | 설명 |
|----------|--------|------|------|
| `limit` | 20 | 1~50 | 최대 조회 건수 |

**Request Headers** — §1 인증 헤더 참조

**Response (200 OK)**

```json
[
  {
    "user_id": "u_abc123...",
    "room_code": "1234",
    "task_id": "translate-positive",
    "result": "WIN",
    "winner_id": "u_abc123...",
    "my_score": 0.92,
    "opponent_score": 0.85,
    "correct_count": 8,
    "total_count": 10,
    "prompt_length": 340,
    "timestamp": 1717430400.0
  }
]
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `user_id` | String | 기록 소유자 ID |
| `room_code` | String | 방 코드 |
| `task_id` | String | 과제 ID |
| `result` | String | `WIN` / `LOSE` / `DRAW` |
| `winner_id` | String\|null | 승자 ID (무승부 시 `null`) |
| `my_score` | Float | 내 최종 점수 |
| `opponent_score` | Float | 상대 최종 점수 |
| `correct_count` | Integer | 내 정답 수 |
| `total_count` | Integer | 전체 TC 수 (N) |
| `prompt_length` | Integer | 내 프롬프트 글자 수 |
| `timestamp` | Float | 기록 시각 (Unix epoch) |

> 메모리 저장 (최대 50건/사용자), 서버 재시작 시 휘발됩니다. v1.2 에서 영속화 예정.

**에러**

| 상태코드 | 사유 |
|----------|------|
| `400` | 인증 헤더 누락 |
| `401` | Bearer 토큰 만료/무효 |

---

### 6. 과제 목록 — `GET /api/tasks`

사전 정의된 과제 풀의 메타데이터를 반환합니다. 정답은 포함되지 않습니다.

**Response (200 OK)**

```json
[
  {
    "id": "translate-positive",
    "description": "다음 문장을 긍정적인 톤으로 번역하시오.",
    "model": "solar-pro3",
    "total_count": 5
  }
]
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | String | 과제 고유 ID |
| `description` | String | 과제 설명 |
| `model` | String | 사용 AI 모델명 |
| `total_count` | Integer | 테스트 케이스 수 |

현재 과제 풀: `translate-positive`, `extract-number`, `classify-sentiment`,
`to-uppercase`, `count-vowels`, `json-keys` (총 6종, 각 5개 TC)

---

### 7. 헬스체크 — `GET /healthz`

서버 및 세션 스토어 상태를 반환합니다. 인증 불필요.

**Response (200 OK)**

```json
{
  "status": "ok",
  "session_backend": "memory",
  "redis": "disabled"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `status` | String | 항상 `"ok"` |
| `session_backend` | String | `"memory"` 또는 `"redis"` |
| `redis` | String | `"ok"` / `"down"` / `"disabled"` (memory 백엔드 사용 시) |

---

## WebSocket API — `WS /ws/arena/{room_code}?client_id={uuid}`

게임의 모든 실시간 진행은 이 WebSocket 연결 하나로 처리됩니다.

**Parameters**

| 파라미터 | 위치 | 필수 | 설명 |
|----------|------|------|------|
| `room_code` | Path | ✅ | 입장할 방 코드 |
| `client_id` | Query | ✅ | 프론트가 생성한 UUID (`/api/me` 와 동일 값) |

**연결 거부 조건 (close code)**

| close code | 조건 |
|------------|------|
| `4001` | `client_id` 누락 |
| `4004` | 존재하지 않는 방 / `PLAYING`·`CLOSED` 상태 방 / 이미 2명이 찬 방 |

연결이 수립되면(accept) 클라이언트는 곧바로 `JOIN` 액션을 보내야 합니다.

---

### Client → Server (action)

모든 메시지는 `action` 필드로 구분합니다.

#### JOIN — 방 입장

WebSocket 연결 직후 즉시 전송합니다.

```json
{ "action": "JOIN" }
```

#### SUBMIT — 프롬프트 제출

```json
{ "action": "SUBMIT", "prompt_text": "사용자가 작성한 프롬프트 내용" }
```

| 항목 | 값 |
|------|-----|
| 최대 글자 수 | 1,200자 |
| 제한 시간 | 180초 (`ROUND_START` 수신 시점 기준) |
| 글자 수 초과 시 | 제출 거부 + 자동 패배 |
| 금칙어/인젝션 패턴 포함 시 | 제출 거부 + 자동 패배 |
| 중복/지연 제출 | 무시 |

**SUBMIT 안전성 검증**

서버는 `SUBMIT` 수신 시 다음 순서로 검사하며, 위반 시 `ERROR(code: SERVER_ERROR)` 를 발송하고 자동 패배 처리합니다.

| 검사 항목 | 위반 조건 |
|-----------|-----------|
| 빈 입력 | 공백만으로 구성된 프롬프트 |
| 글자 수 초과 | 1,200자 초과 |
| 금칙어 | 욕설·혐오 표현 부분 일치 (대소문자 무시). `ARENA_BANNED_WORDS` 환경 변수로 추가 가능 |
| 프롬프트 인젝션 패턴 | `"ignore previous instructions"`, `"system prompt:"` 등 |

---

### Server → Client (event)

모든 메시지는 `event` 필드로 구분합니다.

#### WAITING — 대기 안내

- 첫 번째 플레이어가 `JOIN` 후 상대를 기다리는 중
- 프롬프트 제출 완료 후 상대방 제출을 기다리는 중

```json
{ "event": "WAITING", "message": "상대방을 기다리는 중입니다..." }
```

#### ROUND_START — 라운드 시작

2명이 모두 `JOIN` 하면 서버가 양쪽에 동시 발송합니다.

```json
{
  "event": "ROUND_START",
  "task": "다음 문장을 긍정적인 톤으로 번역하시오.",
  "model": "solar-pro3",
  "time_limit": 180
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `task` | String | 이번 라운드 과제 (서버 과제 풀에서 배정) |
| `model` | String | 사용할 Base AI 모델명 |
| `time_limit` | Integer | 프롬프트 작성 제한 시간(초) |

#### RESULT — 채점 결과 발표

양쪽 채점이 끝나면 각 플레이어에게 발송합니다.

> **채점 방식:** 사용자 프롬프트를 Base AI 모델에 입력 → N개 테스트 케이스 병렬
> 호출 → 정답과 이진 비교 → 수식 산출
> `Score = 0.9 × (정답 수 / N) + 0.1 × √(1 − (L / 1200)²)`

```json
{
  "event": "RESULT",
  "result": "WIN",
  "winner_id": "승리한 유저의 UUID",
  "my_data": {
    "client_id": "내 UUID",
    "prompt": "내가 쓴 프롬프트",
    "ai_response": "내 프롬프트로 생성된 AI 응답(대표 1개)",
    "correct_count": 8,
    "total_count": 10,
    "prompt_length": 340,
    "score": 0.92
  },
  "opponent_data": {
    "client_id": "상대 UUID",
    "prompt": "상대가 쓴 프롬프트",
    "ai_response": "상대 프롬프트로 생성된 AI 응답",
    "correct_count": 7,
    "total_count": 10,
    "prompt_length": 520,
    "score": 0.85
  }
}
```

**`result` 값**

| 값 | 설명 |
|----|------|
| `WIN` | 내가 승리 |
| `LOSE` | 내가 패배 |
| `DRAW` | 무승부 (점수 동일) |

- `winner_id` 는 무승부 시 `null`.
- 점수가 같으면 `DRAW`. 한쪽만 자동 패배(타임아웃/글자수 초과/안전 필터 위반)면 점수와 무관하게 상대가 `WIN`.

**`my_data` / `opponent_data` 필드**

| 필드 | 타입 | 설명 |
|------|------|------|
| `client_id` | String | 플레이어 UUID |
| `prompt` | String | 제출 프롬프트 원문 |
| `ai_response` | String | 대표 AI 응답 1개 |
| `correct_count` | Integer | 정답 테스트 케이스 수 |
| `total_count` | Integer | 전체 테스트 케이스 수 (N) |
| `prompt_length` | Integer | 프롬프트 글자 수 (L) |
| `score` | Float | 최종 점수 (0.0 ~ 1.0, 소수 4자리) |

#### TIMEOUT — 타임아웃

제한 시간 내 `SUBMIT` 하지 않은 플레이어에게 발송하며, 자동 패배 처리됩니다.

```json
{
  "event": "TIMEOUT",
  "message": "제한 시간이 초과되었습니다. 자동 패배 처리됩니다.",
  "result": "LOSE"
}
```

> 제때 제출한 상대는 `RESULT (result: "WIN")` 를 받으며, 그 `opponent_data.score`
> 는 `0` 입니다. 양쪽 모두 타임아웃이면 둘 다 `TIMEOUT(result: "LOSE")` 을 받습니다.

#### ERROR — 에러 및 강제 처리

```json
{
  "event": "ERROR",
  "code": "OPPONENT_DISCONNECTED",
  "message": "상대방의 연결이 끊어졌습니다. 부전승 처리됩니다.",
  "action_required": "GO_TO_HOME"
}
```

**`code` 값**

| 코드 | 설명 |
|------|------|
| `OPPONENT_DISCONNECTED` | 상대 연결 끊김, 부전승 처리 |
| `AI_CALL_FAILED` | AI 호출 N회(기본 3회) 모두 실패, 라운드 무효 |
| `SERVER_ERROR` | 글자 수 초과·금칙어·인젝션 패턴 등 기타 처리 |

**`action_required` 값**

| 값 | 설명 |
|----|------|
| `GO_TO_HOME` | 홈으로 이동 |
| `RETRY_ROUND` | 라운드 재시도 (AI 호출 실패 시) |

---

## 전체 이벤트 흐름 요약

```
[Player A]                    [Server]                    [Player B]
    |── POST /api/auth/login ──>|                            |
    |<─ 200 { token, user_id } ─|                            |
    |── POST /api/rooms ────────>|                            |
    |<─ 201 { room_code: 1234 } ─|                            |
    |── GET /api/rooms/1234 ─────────────────────────────────>|
    |                            |<─ 200 { status: WAITING } ─|
    |── WS /ws/arena/1234 ──────>|<── WS /ws/arena/1234 ──────|
    |── { action: JOIN } ───────>|<── { action: JOIN } ───────|
    |<── ROUND_START ────────────|──── ROUND_START ──────────>|
    |── { action: SUBMIT } ─────>|                            |
    |<── WAITING ────────────────|                            |
    |                            |<── { action: SUBMIT } ─────|
    |<── RESULT (WIN/LOSE/DRAW) ─|──── RESULT (WIN/LOSE/DRAW)>|
    |── GET /api/me/history ─────>|                           |
    |<─ 200 [{ result: "WIN" }] ──|                           |
```

---

## 부록 A — 원본 명세 대비 구현 명확화

원본 명세에서 동작이 명시되지 않았던 부분을 다음과 같이 구현했습니다.

| 항목 | 구현 결정 |
|------|-----------|
| WS 연결 거부 신호 | HTTP 가 아닌 WebSocket close code 로 통지 (`4001` client_id 누락, `4004` 입장 불가) |
| 글자 수 초과 제출 | 해당 제출 거부 + 자동 패배. 본인에게 `ERROR(code: SERVER_ERROR, action: GO_TO_HOME)` 발송 후 `RESULT(result: LOSE, score: 0)` 발송 |
| 금칙어/인젝션 패턴 위반 | 글자 수 초과 처리와 동일하게 자동 패배 처리 |
| 양쪽 모두 타임아웃 | 둘 다 `TIMEOUT(result: LOSE)` (무승부 아님) |
| 자동 패배 + 동점 | 자동 패배(타임아웃/초과/필터 위반) 사유가 있으면 점수가 같아도 상대가 `WIN` |
| 점수 반올림 | 소수점 4자리 |
| 종료된 방 | 저장소에서 제거 → 조회 시 `404` |
| AI 백엔드 | 기본 `mock`(키 불필요·결정론적), `upstage` 설정 시 실제 Solar API 호출 |
| `FULL` 상태 | 현재 구현에서는 발생하지 않음. 2명이 모두 `JOIN` 하면 `WAITING → PLAYING` 으로 즉시 전환되므로 `GET /api/rooms` 응답에 `FULL` 이 노출되지 않는다. 예약 상태로 정의만 유지한다. |
| 세션 스토어 | 기본 InMemory, `REDIS_URL` 설정 시 Redis 사용 |
| 토큰 TTL | 기본 24h (`SESSION_TTL_SECONDS` 환경 변수로 조정) |
| user_id 생성 | 닉네임 기반 결정론적 SHA-256 해시 (`u_<hash16>`) — DB 없는 MVP |

---

## 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `ARENA_TIME_LIMIT` | `180` | 프롬프트 작성 제한 시간(초) |
| `ARENA_MAX_PROMPT_LENGTH` | `1200` | 프롬프트 최대 글자 수 |
| `ARENA_AI_MAX_RETRIES` | `3` | AI 호출 최대 재시도 횟수 |
| `ARENA_AI_BACKEND` | `mock` | AI 백엔드: `mock` / `upstage` |
| `UPSTAGE_API_KEY` | `` | Upstage Solar API 키 |
| `UPSTAGE_BASE_URL` | `https://api.upstage.ai/v1/solar` | Upstage 엔드포인트 |
| `ARENA_DEFAULT_MODEL` | `solar-pro3` | ROUND_START 에 사용할 기본 모델명 |
| `REDIS_URL` | `` | Redis 연결 URL (빈 문자열 시 InMemory 사용) |
| `SESSION_TTL_SECONDS` | `86400` | 세션 토큰 유효 기간(초) |
| `ARENA_BANNED_WORDS` | `` | 추가 금칙어 (콤마 구분) |

---

## 미구현 예정 (v1.2 이후)

| 기능 | 예정 버전 | 비고 |
|------|----------|------|
| 소셜 로그인 실구현 (Google/Kakao) | v1.1 | stub 라우트는 본 빌드에서 노출 (`501`) |
| LLM 피드백 생성 | v1.1 | |
| 랭킹 / 전적 영속화 | v1.2 | 간이 메모리 history는 본 빌드에서 제공 |
| 토큰 정산 API | v1.2 | |
| 악성 입력 고도화 필터링 | v1.3 | MVP 수준 필터는 본 빌드에서 적용 |
