# Prompt Arena — Frontend Design Spec

**날짜:** 2026-06-04  
**작성자:** 이정현  
**대상 브랜치:** `feat/hyeon/frontend`  
**범위:** MVP 프론트엔드 (Streamlit)

---

## 1. 결정 사항 요약

| 항목 | 결정 |
|------|------|
| UI 프레임워크 | Streamlit 기본 스타일 (커스텀 CSS 없음) |
| 화면 전환 | 단일 `app.py` + `st.session_state["screen"]` |
| WS 수신 | 백그라운드 스레드 + `queue.Queue` + `st.rerun()` |
| 홈 화면 | 버튼 2개 (새 방 만들기 / 방 참여하기) |
| 아키텍처 | 모듈 분리 (screens/ + ws_client + api_client) |

---

## 2. 파일 구조

```
frontend/
├── app.py                  # 진입점 — screen 라우팅만
├── ws_client.py            # WS 연결·수신 백그라운드 스레드
├── api_client.py           # REST 호출 (방 생성, 방 조회)
├── screens/
│   ├── __init__.py
│   ├── home.py             # 홈 화면
│   ├── waiting.py          # 대기 화면
│   ├── round.py            # 프롬프트 작성 화면
│   └── result.py           # 결과 화면
├── state.py                # session_state 키 상수 + 초기화 함수
├── requirements.txt
└── .env                    # BACKEND_URL, WS_URL
```

---

## 3. 상태 관리

`state.py`에 모든 `st.session_state` 키를 상수로 정의. `init_state()`를 `app.py` 최상단에서 1회 호출.

```python
# 네비게이션
SCREEN         = "screen"           # "home" | "waiting" | "round" | "result"

# 세션 식별
CLIENT_ID      = "client_id"        # UUID (앱 최초 로드 시 생성, 유지)

# 방 정보
ROOM_CODE      = "room_code"        # 4자리 문자열

# WS
WS_THREAD      = "ws_thread"        # 백그라운드 스레드 객체
WS_QUEUE       = "ws_queue"         # queue.Queue — WS 이벤트 수신 버퍼
WS_CONNECTED   = "ws_connected"     # bool
WS_OBJECT      = "ws_object"        # websocket 객체 (send용)

# 라운드 데이터
TASK           = "task"             # ROUND_START.task 문자열
MODEL          = "model"            # ROUND_START.model
TIME_LIMIT     = "time_limit"       # 초
ROUND_START_AT = "round_start_at"   # time.time() — 남은 시간 계산 기준

# 결과
RESULT_PAYLOAD = "result_payload"   # RESULT / TIMEOUT / ERROR 이벤트 전체 dict
```

---

## 4. 화면 상태 머신

```
home ──(방 생성/입장 성공)──> waiting
waiting ──(ROUND_START 수신)──> round
round ──(RESULT 수신)──────> result
round ──(TIMEOUT 수신)─────> result
round ──(ERROR 수신)───────> result
result ──(다시 하기)─────────> home
```

화면 전환: `st.session_state[SCREEN] = "다음화면"` → `st.rerun()`

---

## 5. WS 클라이언트 설계 (`ws_client.py`)

```
[메인 스레드 - Streamlit]          [백그라운드 스레드]
                                    ws = websocket.WebSocket()
                                    ws.connect(url)
                                    send({"action": "JOIN"})
                                    loop:
                                      msg = ws.recv()
                                      queue.put(json.loads(msg))

각 화면 render() 호출 시:
  while not queue.empty():
    event = queue.get_nowait()
    → 이벤트 처리 (화면 전환 or 상태 업데이트)
  if 화면 전환 발생:
    st.rerun()
```

**공개 인터페이스:**
```python
start_ws_thread(room_code, client_id, q) → ws_object  # 스레드 시작
send_join(ws)                                           # JOIN 전송
send_submit(ws, prompt_text)                            # SUBMIT 전송
stop_ws(ws)                                             # 연결 종료
```

---

## 6. 각 화면 명세

### 6-1. 홈 (`home.py`)

```
제목: "Prompt Arena"
부제: "프롬프트로 승부하라"

[새 방 만들기] 버튼
  → POST /api/rooms (X-Client-ID 헤더)
  → room_code 저장
  → WS 연결 + JOIN
  → screen = "waiting"

[방 참여하기] 버튼
  → 4자리 코드 text_input 노출
  → GET /api/rooms/{code} 상태 확인 (WAITING인지)
  → WS 연결 + JOIN
  → screen = "waiting"

에러 케이스:
  - 방 없음 (404) → st.error("존재하지 않는 방 코드입니다.")
  - 이미 진행중 (PLAYING) → st.error("이미 시작된 방입니다.")
  - 네트워크 오류 → st.error("서버에 연결할 수 없습니다.")
```

### 6-2. 대기 (`waiting.py`)

```
방 코드: [1234]   ← st.code() (복사 용이)
st.spinner("상대방을 기다리는 중...")

← ROUND_START 수신 시:
  task, model, time_limit 저장
  round_start_at = time.time()
  screen = "round"
```

### 6-3. 라운드 (`round.py`)

```
st.info(task)           # 과제
st.caption(f"모델: {model}")

# 타이머 (st_autorefresh 1초마다 rerun)
elapsed = time.time() - round_start_at
remaining = time_limit - elapsed
"남은 시간: M:SS"

# 프롬프트 입력
prompt = st.text_area("프롬프트를 작성하세요", height=200)
f"글자수: {len(prompt)} / 1200"

# 제출 버튼
submitted 상태 아닐 때: [제출] 버튼 → send_submit(ws, prompt)
submitted 상태일 때: st.info("상대방 기다리는 중...")

# 타임아웃
remaining <= 0 → TIMEOUT 처리 → screen = "result"

# WS 이벤트 처리
RESULT → result_payload 저장 → screen = "result"
TIMEOUT → result_payload 저장 → screen = "result"
ERROR → result_payload 저장 → screen = "result"
```

### 6-4. 결과 (`result.py`)

`result_payload`에는 두 가지 형태가 올 수 있음:

- **RESULT 이벤트** → `{ result, winner_id, my_data, opponent_data }` (정상 종료)
- **TIMEOUT 이벤트** → `{ event: "TIMEOUT", result: "LOSE", message }` (my_data 없음)
- **ERROR 이벤트** → `{ event: "ERROR", code, message }` (연결 끊김 등)

```
# 승패 배너 (event 타입으로 분기)
RESULT 이벤트:
  WIN  → st.success("승리!")
  LOSE → st.error("패배...")
  DRAW → st.warning("무승부")

TIMEOUT 이벤트:
  st.error("시간 초과 — 자동 패배")

ERROR 이벤트:
  code == OPPONENT_DISCONNECTED → st.success("상대 연결 끊김 — 부전승")
  code == AI_CALL_FAILED        → st.warning("AI 호출 실패 — 라운드 무효")
  기타                           → st.error(message)

# 비교 테이블 (RESULT 이벤트이고 my_data 있을 때만)
col1, col2 = st.columns(2)
col1 [나]:
  프롬프트 원문
  AI 응답
  정답: correct_count / total_count
  점수: score

col2 [상대]:
  동일 구조

# 하단
[다시 하기] → session_state 초기화 → screen = "home"
```

---

## 7. API 클라이언트 (`api_client.py`)

```python
def create_room(client_id: str) -> str:       # room_code 반환
def get_room(room_code: str) -> dict:          # {status, current_players, ...}
```

`BACKEND_URL` 환경 변수 참조. `requests` 라이브러리.

---

## 8. 의존성

```
streamlit>=1.35.0
streamlit-autorefresh>=1.0.1
requests>=2.31.0
websocket-client>=1.8.0
python-dotenv>=1.0.0
```

---

## 9. 개발 순서 (단계별 승인 방식)

각 단계 완료 후 → 테스트 가이드 제공 → 사용자 테스트 → 승인 → 다음 단계.

| 단계 | 내용 |
|------|------|
| 1 | 프로젝트 뼈대 (app.py, state.py, requirements.txt, .env) |
| 2 | api_client.py + 홈 화면 (방 생성/참여 REST 연동) |
| 3 | ws_client.py (WS 연결·수신 스레드) |
| 4 | 대기 화면 (WS WAITING → ROUND_START 전환) |
| 5 | 라운드 화면 (타이머 + 글자수 + 제출) |
| 6 | 결과 화면 (승패 + 비교 표시) |
| 7 | 에러/엣지케이스 처리 (disconnect, timeout, over-length) |
