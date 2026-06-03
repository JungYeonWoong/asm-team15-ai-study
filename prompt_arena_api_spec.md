# Prompt Arena — API 명세서 (확정본)

> **버전:** v1.0-MVP  
> **최종 수정:** 2025-06  
> **범위:** MVP 핵심 대전 흐름 (방 생성 → 매칭 → 대전 → 결과)

---

## 공통 사항

| 항목 | 내용 |
|------|------|
| Base URL | `http://localhost:8000` |
| 인증 방식 | 세션 기반 (소셜 로그인은 v1.1에서 추가, MVP는 세션 UUID만 사용) |
| 데이터 형식 | JSON |
| 문자 인코딩 | UTF-8 |

---

## REST API

### 1. 세션 확인

현재 클라이언트의 세션 상태를 확인합니다. 소셜 로그인 구현 전 MVP 단계에서는 프론트엔드가 생성한 UUID를 세션 식별자로 사용합니다.

```
GET /api/me
```

**Request Headers**

| 헤더 | 필수 | 설명 |
|------|------|------|
| `X-Client-ID` | ✅ | 프론트엔드가 생성한 UUID |

**Response (200 OK)**

```json
{
  "client_id": "a1b2c3d4-...",
  "status": "active"
}
```

---

### 2. 방 생성

대전 방을 새로 만듭니다. 방을 만든 사람이 호스트가 되며, 방 코드를 상대방에게 공유합니다.

```
POST /api/rooms
```

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

**에러 응답**

| 상태코드 | 사유 |
|----------|------|
| `400` | X-Client-ID 누락 |
| `409` | 이미 다른 방에 참여 중인 클라이언트 |

---

### 3. 방 상태 조회

WebSocket 연결 전, 방이 입장 가능한지 사전 확인합니다.

```
GET /api/rooms/{room_code}
```

**Request Path Parameters**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `room_code` | String | 조회할 방 코드 (예: `"1234"`) |

**Response (200 OK)**

```json
{
  "room_code": "1234",
  "status": "WAITING",
  "current_players": 1
}
```

**`status` 값 정의**

| 값 | 설명 |
|----|------|
| `WAITING` | 1명 대기 중, 입장 가능 |
| `FULL` | 2명 모두 입장, 대기 중 |
| `PLAYING` | 게임 진행 중, 입장 불가 |
| `CLOSED` | 종료된 방 |

**에러 응답**

| 상태코드 | 사유 |
|----------|------|
| `404` | 존재하지 않는 방 코드 |

---

## WebSocket API

게임의 모든 실시간 진행은 이 WebSocket 연결 하나로 처리됩니다.

```
WS /ws/arena/{room_code}?client_id={uuid}
```

**Query Parameters**

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| `client_id` | ✅ | 프론트엔드가 생성한 UUID (`/api/me`와 동일한 값) |
| `room_code` | ✅ (Path) | 입장할 방 코드 |

**연결 거부 조건**

- 존재하지 않는 `room_code`
- `status`가 `PLAYING` 또는 `CLOSED`인 방
- `client_id` 누락

---

### Client → Server (프론트엔드가 보내는 액션)

모든 메시지는 `action` 필드로 구분합니다.

#### 1. 방 입장 (JOIN)

WebSocket 연결 직후 즉시 전송합니다.

```json
{
  "action": "JOIN"
}
```

#### 2. 프롬프트 제출 (SUBMIT)

제한 시간 내에 작성을 완료하고 제출합니다.

```json
{
  "action": "SUBMIT",
  "prompt_text": "사용자가 작성한 프롬프트 내용"
}
```

**제약 조건**

| 항목 | 값 |
|------|-----|
| 최대 글자 수 | 1,200자 |
| 제한 시간 | 180초 (ROUND_START 이벤트 수신 시점 기준) |
| 초과 시 처리 | 서버에서 제출 거부, 자동 패배 처리 |

---

### Server → Client (서버가 보내는 이벤트)

모든 메시지는 `event` 필드로 구분합니다.

#### 1. 대기 상태 안내 (WAITING)

다음 두 상황에서 발생합니다.
- 첫 번째 플레이어가 JOIN 후 상대를 기다리는 중
- 프롬프트 제출 완료 후 상대방 제출을 기다리는 중

```json
{
  "event": "WAITING",
  "message": "상대방을 기다리는 중입니다..."
}
```

---

#### 2. 라운드 시작 (ROUND_START)

2명이 모두 JOIN하면 서버가 양쪽에 동시 발송합니다.  
프론트엔드는 이 이벤트 수신 시 180초 타이머를 시작하고 입력창을 활성화합니다.

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
| `task` | String | 이번 라운드 과제 (서버에서 사전 정의된 과제 풀에서 배정) |
| `model` | String | 사용할 Base AI 모델명 |
| `time_limit` | Integer | 프롬프트 작성 제한 시간 (초) |

---

#### 3. 채점 결과 발표 (RESULT)

양쪽 모두 SUBMIT 완료 후, 서버가 AI 호출 및 수식 채점을 마치면 양쪽에 동시 발송합니다.

> **채점 방식:** 백엔드에서 사용자 프롬프트를 Base AI 모델에 입력 → N개의 테스트 케이스 병렬 호출 → 정답과 이진 비교 → 수식 자동 산출  
> `Score = 0.9 × (정답 수 / N) + 0.1 × √(1 - (L / 1200)²)`

```json
{
  "event": "RESULT",
  "result": "WIN",
  "winner_id": "승리한 유저의 UUID",
  "my_data": {
    "client_id": "내 UUID",
    "prompt": "내가 쓴 프롬프트",
    "ai_response": "내 프롬프트로 생성된 AI 응답",
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

**`result` 값 정의**

| 값 | 설명 |
|----|------|
| `"WIN"` | 내가 승리 |
| `"LOSE"` | 내가 패배 |
| `"DRAW"` | 무승부 (점수 동일) |

> `winner_id`는 무승부 시 `null`로 반환합니다.

**`my_data` / `opponent_data` 필드**

| 필드 | 타입 | 설명 |
|------|------|------|
| `client_id` | String | 해당 플레이어의 UUID |
| `prompt` | String | 제출한 프롬프트 원문 |
| `ai_response` | String | 프롬프트 실행 결과 (대표 응답 1개) |
| `correct_count` | Integer | 정답 처리된 테스트 케이스 수 |
| `total_count` | Integer | 전체 테스트 케이스 수 (N) |
| `prompt_length` | Integer | 프롬프트 글자 수 (L) |
| `score` | Float | 최종 점수 (0.0 ~ 1.0) |

---

#### 4. 타임아웃 (TIMEOUT)

제한 시간(180초) 내 SUBMIT을 하지 않은 플레이어에게 발송합니다.  
해당 플레이어는 자동 패배 처리됩니다.

```json
{
  "event": "TIMEOUT",
  "message": "제한 시간이 초과되었습니다. 자동 패배 처리됩니다.",
  "result": "LOSE"
}
```

> 상대방(제때 제출한 플레이어)에게는 별도로 RESULT 이벤트가 발송됩니다. 이때 `result: "WIN"`, 상대 데이터의 `score`는 `0`으로 처리합니다.

---

#### 5. 에러 및 강제 처리 (ERROR)

다음 상황에서 발생합니다.
- 상대방 연결 끊김 (부전승)
- AI 모델 호출 3회 재시도 실패
- 기타 서버 오류

```json
{
  "event": "ERROR",
  "code": "OPPONENT_DISCONNECTED",
  "message": "상대방의 연결이 끊어졌습니다. 부전승 처리됩니다.",
  "action_required": "GO_TO_HOME"
}
```

**`code` 값 정의**

| 코드 | 설명 |
|------|------|
| `OPPONENT_DISCONNECTED` | 상대방 연결 끊김, 부전승 처리 |
| `AI_CALL_FAILED` | AI 모델 호출 3회 모두 실패, 라운드 무효 처리 |
| `SERVER_ERROR` | 기타 내부 오류 |

**`action_required` 값 정의**

| 값 | 설명 |
|----|------|
| `GO_TO_HOME` | 홈으로 이동 |
| `RETRY_ROUND` | 라운드 재시도 (AI 호출 실패 시) |

---

## 전체 이벤트 흐름 요약

```
[Player A]                    [Server]                    [Player B]
    |                            |                            |
    |── POST /api/rooms ────────>|                            |
    |<─ 201 { room_code: 1234 } ─|                            |
    |                            |                            |
    |── GET /api/rooms/1234 ─────────────────────────────────>|
    |                            |<─ 200 { status: WAITING } ─|
    |                            |                            |
    |── WS /ws/arena/1234 ──────>|<── WS /ws/arena/1234 ──────|
    |── { action: JOIN } ───────>|<── { action: JOIN } ───────|
    |                            |                            |
    |<── ROUND_START ────────────|──── ROUND_START ──────────>|
    |    (타이머 시작)            |    (타이머 시작)            |
    |                            |                            |
    |── { action: SUBMIT } ─────>|                            |
    |<── WAITING ────────────────|                            |
    |                            |<── { action: SUBMIT } ─────|
    |                            |                            |
    |      (AI 호출 + 채점)       |      (AI 호출 + 채점)       |
    |                            |                            |
    |<── RESULT (WIN/LOSE/DRAW) ─|──── RESULT (WIN/LOSE/DRAW)>|
```

---

## 변경 이력

| 버전 | 날짜 | 내용 |
|------|------|------|
| v1.0-MVP | 2025-06 | 초안 확정. 방 생성/조회, 세션 확인, WebSocket 대전 흐름 정의 |

---

## 미구현 예정 (v1.1 이후)

| 기능 | 예정 버전 |
|------|----------|
| 소셜 로그인 / JWT 인증 | v1.1 |
| LLM 피드백 생성 | v1.1 |
| 랭킹 / 전적 조회 | v1.2 |
| 토큰 정산 API | v1.2 |
| 악성 입력 고도화 필터링 | v1.3 |
