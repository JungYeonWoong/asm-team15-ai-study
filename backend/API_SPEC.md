# Prompt Arena — API 명세서 (구현 정합본)

> **버전:** v1.0-MVP (구현 반영)
> **최종 수정:** 2026-06
> **범위:** MVP 핵심 대전 흐름 (방 생성 → 매칭 → 대전 → 결과)
> **기준:** 본 문서는 `backend/` 의 실제 FastAPI 구현과 1:1로 일치하도록 정리한
> 명세입니다. 원본 요구 명세(`prompt_arena_api_spec.md`)를 기준으로 하되,
> 모호했던 부분을 구현 결정에 맞춰 정확히 기술합니다. (§부록 A 참조)

---

## 공통 사항

| 항목 | 내용 |
|------|------|
| Base URL | `http://localhost:8000` |
| 인증 방식 | 세션 기반 (MVP 는 프론트가 생성한 `X-Client-ID` UUID 만 사용) |
| 데이터 형식 | JSON |
| 문자 인코딩 | UTF-8 |
| Swagger | `GET /docs` |

---

## REST API

### 1. 세션 확인 — `GET /api/me`

현재 클라이언트의 세션 상태를 확인합니다.

**Request Headers**

| 헤더 | 필수 | 설명 |
|------|------|------|
| `X-Client-ID` | ✅ | 프론트엔드가 생성한 UUID |

**Response (200 OK)**

```json
{ "client_id": "a1b2c3d4-...", "status": "active" }
```

**에러**

| 상태코드 | 사유 |
|----------|------|
| `400` | `X-Client-ID` 누락 |

---

### 2. 방 생성 — `POST /api/rooms`

방을 만든 사람이 호스트가 되고, 호스트는 즉시 멤버로 등록되어
`current_players` 가 1이 됩니다.

**Request Headers**

| 헤더 | 필수 | 설명 |
|------|------|------|
| `X-Client-ID` | ✅ | 프론트엔드가 생성한 UUID |

**Request Body** — 없음

**Response (201 Created)**

```json
{
  "room_code": "1234",
  "status": "WAITING",
  "current_players": 1,
  "created_by": "a1b2c3d4-..."
}
```

- `room_code`: 4자리 숫자 문자열 (`"0000"`~`"9999"`), 서버가 중복 없이 발급.

**에러**

| 상태코드 | 사유 |
|----------|------|
| `400` | `X-Client-ID` 누락 |
| `409` | 이미 (종료되지 않은) 다른 방에 참여 중인 클라이언트 |

---

### 3. 방 상태 조회 — `GET /api/rooms/{room_code}`

WebSocket 연결 전, 방이 입장 가능한지 사전 확인합니다.

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
| 글자 수 초과 시 | 제출 거부 + 자동 패배 (아래 §부록 A 참조) |
| 중복/지연 제출 | 무시 |

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
  "model": "Upstage-Solar-Pro",
  "time_limit": 180
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `task` | String | 이번 라운드 과제 (서버 과제 풀에서 배정) |
| `model` | String | 사용할 Base AI 모델명 |
| `time_limit` | Integer | 프롬프트 작성 제한 시간(초) |

#### RESULT — 채점 결과 발표

양쪽 채점이 끝나면 (타임아웃이 아닌) 각 플레이어에게 발송합니다.

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
- 점수가 같으면 `DRAW`. 한쪽만 자동 패배(타임아웃/글자수 초과)면 점수와 무관하게
  상대가 `WIN`.

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
| `SERVER_ERROR` | 글자 수 초과 등 기타 처리 |

**`action_required` 값**

| 값 | 설명 |
|----|------|
| `GO_TO_HOME` | 홈으로 이동 |
| `RETRY_ROUND` | 라운드 재시도 (AI 호출 실패 시) |

---

## 전체 이벤트 흐름 요약

```
[Player A]                    [Server]                    [Player B]
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
```

---

## 부록 A — 원본 명세 대비 구현 명확화

원본 명세에서 동작이 명시되지 않았던 부분을 다음과 같이 구현했습니다.

| 항목 | 구현 결정 |
|------|-----------|
| WS 연결 거부 신호 | HTTP 가 아닌 WebSocket close code 로 통지 (`4001` client_id 누락, `4004` 입장 불가) |
| 글자 수 초과 제출 | 해당 제출 거부 + 자동 패배. 본인에게 `ERROR(code: SERVER_ERROR, action: GO_TO_HOME)` 발송 후, 라운드 종료 시 `RESULT(result: LOSE, score: 0)` 발송 |
| 양쪽 모두 타임아웃 | 둘 다 `TIMEOUT(result: LOSE)` (무승부 아님) |
| 자동 패배 + 동점 | 자동 패배(타임아웃/초과) 사유가 있으면 점수가 같아도 상대가 `WIN` |
| 점수 반올림 | 소수점 4자리 |
| 종료된 방 | 저장소에서 제거 → 조회 시 `404` |
| AI 백엔드 | 기본 `mock`(키 불필요·결정론적), `upstage` 설정 시 실제 Solar API 호출 |
| `FULL` 상태 | 현재 구현에서는 발생하지 않음. 2명이 모두 `JOIN` 하면 `WAITING → PLAYING` 으로 즉시 전환되므로 `GET /api/rooms` 응답에 `FULL` 이 노출되지 않는다. 예약 상태로 정의만 유지한다. |

---

## 미구현 예정 (v1.1 이후)

| 기능 | 예정 버전 |
|------|----------|
| 소셜 로그인 / JWT 인증 | v1.1 |
| LLM 피드백 생성 | v1.1 |
| 랭킹 / 전적 조회 | v1.2 |
| 토큰 정산 API | v1.2 |
| 악성 입력 고도화 필터링 | v1.3 |
