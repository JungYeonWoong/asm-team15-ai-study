# v1.1-MVP 변경 영향 분석

> **기준 브랜치:** `main` (v1.0-MVP)
> **변경 브랜치:** `feat/auth-and-extensions`
> **작성일:** 2026-06

---

## 요약

v1.1-MVP 는 인증 시스템, 결과 기록, 과제 목록, 헬스체크, 프롬프트 안전 필터를
MVP 코어에 통합한 빌드입니다. 기존 `X-Client-ID` 기반 흐름은 그대로 유지되므로
대부분의 변경은 **비파괴적(additive)** 이지만, SUBMIT 안전 필터와 GET /api/me
응답 구조 변경은 **프론트엔드 대응이 필요**합니다.

---

## 1. 신규 엔드포인트

### 인증 (`app/auth/`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/auth/dev-login` | 개발용 즉시 로그인, 토큰 발급 |
| `POST` | `/api/auth/login` | 닉네임 기반 로그인, 토큰 발급 |
| `POST` | `/api/auth/logout` | Bearer 토큰 폐기 |
| `POST` | `/api/auth/social/{provider}` | 소셜 로그인 stub — 항상 `501` |

**영향:** 프론트엔드에서 로그인 UI를 구현할 경우 이 엔드포인트를 사용합니다.
기존 X-Client-ID 방식은 폴백으로 계속 동작합니다.

---

### 결과 기록 (`app/history/`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/me/history?limit=20` | 본인 최근 라운드 결과 (최대 50건, 메모리) |

**영향:** 랭킹/전적 화면 구현 시 이 엔드포인트 사용. 인증 헤더 필요.

---

### 과제 목록 (`app/arena/tasks_router.py`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/tasks` | 과제 풀 메타데이터 (정답 비공개) |

**영향:** 과제 목록 화면 또는 프리뷰 UI 구현 시 활용.

---

### 헬스체크 (`app/health/`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/healthz` | 서버/세션 스토어 상태 |

**영향:** 모니터링·배포 파이프라인에서 헬스 프로브로 사용.

---

## 2. 기존 엔드포인트 변경

### GET /api/me — 응답 구조 변경

**Before**
```json
{ "client_id": "uuid", "status": "active" }
```

**After**
```json
{
  "client_id": "u_abc123... 또는 uuid",
  "status": "active",
  "nickname": "player1",   ← 신규 (nullable)
  "provider": "nickname"  ← 신규 (nullable)
}
```

**영향:**
- 기존 코드에서 `client_id`, `status` 만 읽는 경우 무영향 (필드 추가).
- `client_id` 값이 달라질 수 있음: Bearer 토큰으로 로그인한 경우 UUID 대신 `u_<hash16>` 형태로 반환.
- X-Client-ID 폴백 시에는 `nickname: null`, `provider: "client-id"`.

---

### POST /api/rooms — 인증 헤더 확장

**Before:** `X-Client-ID` 필수

**After:** `Authorization: Bearer <token>` 우선, `X-Client-ID` 폴백. 둘 다 없으면 `400`.

**영향:**
- X-Client-ID 만 사용하는 기존 클라이언트는 그대로 동작.
- Bearer 토큰 사용 시 `created_by` 값이 `u_<hash16>` 형태로 변경.

---

### WS /ws/arena/{room_code} — SUBMIT 안전 필터 추가

SUBMIT 시 프롬프트가 다음 조건을 위반하면 **자동 패배** 처리됩니다.

| 조건 | 기존 동작 | 변경 후 동작 |
|------|-----------|-------------|
| 글자 수 초과 (1200자+) | ERROR + 자동 패배 | 동일 |
| **빈 문자열/공백만 입력** | 무시 또는 채점 | ERROR + 자동 패배 (신규) |
| **금칙어 포함** | 없음 | ERROR + 자동 패배 (신규) |
| **프롬프트 인젝션 패턴** | 없음 | ERROR + 자동 패배 (신규) |

**영향:** 프론트엔드에서 빈 입력 방지 처리가 없다면 의도치 않은 자동 패배가 발생할 수 있습니다.

---

## 3. 인증 방식 변경

### 전역 의존성 업데이트 (`app/core/deps.py`)

모든 인증이 필요한 엔드포인트가 `get_current_user` 의존성을 사용하도록 통합되었습니다.

| 우선순위 | 헤더 | 결과 |
|----------|------|------|
| 1 | `Authorization: Bearer <token>` (유효) | `user_id = u_<hash>`, `nickname` 포함 |
| 2 | `X-Client-ID` | `user_id = UUID`, `nickname = null` |
| - | Bearer 있으나 만료 | `401` |
| - | 둘 다 없음 | `400` |

---

## 4. 설정/환경 변수 추가

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `REDIS_URL` | `` | Redis 연결 URL (비어있으면 InMemory) |
| `SESSION_TTL_SECONDS` | `86400` | 세션 토큰 TTL(초) |
| `ARENA_BANNED_WORDS` | `` | 추가 금칙어 (콤마 구분) |
| `ARENA_DEFAULT_MODEL` | `solar-pro3` | 기본 AI 모델명 |

**영향:** `.env` 또는 배포 환경에 위 변수가 없으면 기본값으로 동작합니다 (하위 호환).

---

## 5. 내부 구조 변경 (프론트엔드 무영향)

| 모듈 | 변경 내용 |
|------|-----------|
| `app/auth/session_store.py` | InMemory / Redis 세션 스토어 구현 추가 |
| `app/auth/providers.py` | Dev / Nickname / Social Provider 구현 |
| `app/arena/safety.py` | 금칙어·인젝션 패턴 검사기 |
| `app/history/store.py` | `InMemoryHistoryStore` (deque, maxlen=50) |
| `app/core/config.py` | Redis, 세션 TTL, 금칙어, 기본 모델 설정 추가 |
| `app/main.py` | 버전 `v1.0-MVP` → `v1.1-MVP`, 신규 라우터 등록 |

---

## 6. 테스트 영향

신규 테스트 파일:

| 파일 | 검증 범위 |
|------|-----------|
| `tests/test_auth.py` | 인증 엔드포인트 전체 |
| `tests/test_health.py` | `/healthz` |
| `tests/test_history.py` | `/api/me/history` |
| `tests/test_safety.py` | `PromptSafety` 단위 테스트 |
| `tests/test_tasks_endpoint.py` | `GET /api/tasks` |
| `tests/integration/` | 통합 테스트 (E2E 흐름) |

기존 `tests/test_rest.py` 는 `GET /api/me` 응답에 `nickname`, `provider` 필드가
추가됨에 따라 **응답 검증 로직을 업데이트해야 할 수 있습니다**.

---

## 7. 파괴적 변경 없음 확인

| 항목 | 판정 |
|------|------|
| 기존 X-Client-ID 기반 흐름 | ✅ 호환 유지 |
| WebSocket 프로토콜 (action/event 구조) | ✅ 호환 유지 |
| `GET /api/rooms/{room_code}` 응답 | ✅ 변경 없음 |
| `POST /api/rooms` 응답 | ✅ 변경 없음 (필드 추가 없음) |
| `GET /api/me` 응답 | ⚠️ 필드 추가 (비파괴적), `client_id` 값 형식 변경 가능 |
| SUBMIT 자동 패배 조건 | ⚠️ 조건 추가 (빈 입력·금칙어·인젝션 패턴) |
