# Prompt Arena

실시간 1:1 프롬프트 대전 플랫폼. 같은 AI 모델·같은 과제 조건에서 더 효과적인 프롬프트를 작성해 승부를 겨룬다.

## 구조

```
.
├── backend/    # FastAPI 백엔드 (REST + WebSocket) — 별도 README 참고
└── frontend/   # Streamlit 프론트엔드
```

---

## 백엔드 실행 (간략)

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python run.py   # http://localhost:8000
```

> 상세 설정은 [`backend/README.md`](backend/README.md) 참고.

---

## 프론트엔드

### 설치 및 실행

```powershell
cd frontend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

`http://localhost:8501`

### 파일 구조

```
frontend/
├── app.py              # 진입점 — session_state["screen"]으로 화면 라우팅
├── state.py            # session_state 키 상수 + init_state() / reset_game_state()
├── api_client.py       # REST 호출: create_room(), get_room()
├── ws_client.py        # WebSocket 연결·수신 백그라운드 스레드
├── screens/
│   ├── home.py         # 홈 화면
│   ├── waiting.py      # 대기 화면
│   ├── round.py        # 라운드 화면
│   └── result.py       # 결과 화면
└── .env                # BACKEND_URL, WS_URL
```

### 환경 변수 (`frontend/.env`)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `BACKEND_URL` | `http://localhost:8000` | FastAPI REST 주소 |
| `WS_URL` | `ws://localhost:8000` | WebSocket 주소 |

### 화면 흐름

```
home ──(방 생성/입장)──> waiting ──(ROUND_START)──> round ──(RESULT)──> result
                                                           └──(TIMEOUT)──> result
                                                           └──(ERROR)───> result
result ──(다시 하기)──> home
```

### 각 화면 설명

#### 홈 (`screens/home.py`)
- **새 방 만들기**: `POST /api/rooms` → 방 코드 발급 → WS 연결 → 대기 화면
- **방 참여하기**: 4자리 코드 입력 → `GET /api/rooms/{code}` 확인 → WS 연결 → 대기 화면
- 에러(404, 이미 시작된 방, 서버 오류) 인라인 표시

#### 대기 (`screens/waiting.py`)
- 방 코드 크게 표시 (복사 용이)
- 0.5초마다 WS 이벤트 폴링
- `ROUND_START` 수신 시 라운드 화면으로 자동 전환
- **취소** 버튼: WS 명시적 종료 후 홈 이동

#### 라운드 (`screens/round.py`)
- 과제·모델 표시
- 타이머 카운트다운 (1초 autorefresh)
- 프롬프트 입력창 — 실시간 글자수 표시, 최대 1,200자
- 제출 후 "상대방 기다리는 중" 상태 전환
- `RESULT` / `TIMEOUT` / `ERROR` 수신 시 결과 화면 이동
- **대전 포기** 버튼: WS 명시적 종료 → 상대 즉시 부전승 처리

#### 결과 (`screens/result.py`)
- `WIN` → 초록 / `LOSE` → 빨강 / `DRAW` → 노랑 배너
- 내/상대 프롬프트 · AI 응답 · 정답수 · 점수 2열 비교
- `TIMEOUT` (시간 초과) / `ERROR` (연결 끊김, AI 오류) 별도 메시지
- **다시 하기**: WS 종료 + 상태 초기화 + 홈 이동

### WebSocket 구조

```
[Streamlit 서버]                    [백그라운드 스레드]
ws = ws_client.connect()
t  = ws_client.start_recv_thread()  → ws.recv() loop
ws_client.send_join(ws)                queue.put(event)
                                            ↓
[각 화면 render() 호출마다]
  queue.get_nowait() × N
  → 이벤트 처리 (화면 전환 or 상태 업데이트)
  → st.rerun()
```

---

## 게임 흐름

```
방 만들기 → 방 코드 공유 → 상대방 입장
→ 과제 확인 (3분 타이머)
→ 프롬프트 작성 및 제출 (최대 1,200자)
→ AI 채점 (Upstage Solar)
→ 승패 결과 + 프롬프트 비교
```

### 채점 방식

```
Score = 0.9 × (정답 수 / N) + 0.1 × √(1 − (글자수 / 1200)²)
```

정확도 90% + 간결함 10% 가중치.

---

## 테스트

### 백엔드 자동 테스트

```powershell
cd backend && pytest -q    # 24개
```

### 프론트엔드 수동 테스트

백엔드·프론트엔드 모두 실행 후 **브라우저 탭 2개**로 진행.

#### 빠른 테스트 (mock 모드 + 10초 타임아웃)

```powershell
cd backend
$env:ARENA_AI_BACKEND="mock"; $env:ARENA_TIME_LIMIT="10"; python run.py
```

#### 체크리스트

| 화면 | 확인 항목 |
|------|-----------|
| 홈 | 새 방 만들기 → 대기 화면 이동, 방 코드 표시 |
| 홈 | 방 참여하기 → 코드 입력 → 대기 화면 이동 |
| 홈 | 잘못된 코드 → 에러 메시지 |
| 대기 | 방 코드 4자리 표시 |
| 대기 | 탭 2개 입장 시 동시에 라운드 화면 전환 |
| 라운드 | 과제·모델·타이머 표시 |
| 라운드 | 타이머 1초 카운트다운 |
| 라운드 | 글자수 실시간 갱신 |
| 라운드 | 제출 후 "상대방 기다리는 중" |
| 라운드 | 양쪽 제출 완료 → 결과 화면 이동 |
| 결과 | WIN/LOSE/DRAW 배너 |
| 결과 | 내/상대 프롬프트·AI응답·정답수·점수 비교 |
| 결과 | 다시 하기 → 홈 이동, 입력창 초기화 |
| 에러 | 대전 포기 버튼 → 상대 부전승 |
| 에러 | 백엔드 종료 → 홈으로 이동 |

---

## 알려진 이슈

| 이슈 | 상태 | 문서 |
|------|------|------|
| 브라우저 탭 닫기 시 부전승 즉시 미처리 | 백엔드 작업 필요 | [`docs/issues/tab-close-disconnect.md`](docs/issues/tab-close-disconnect.md) |

규칙: [`RULES.md`](RULES.md) | Claude 가이드: [`CLAUDE.md`](CLAUDE.md)
