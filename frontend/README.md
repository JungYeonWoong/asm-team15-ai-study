# PROMPT ARENA — Streamlit 프론트엔드

15조 불꽃청년 백엔드(FastAPI + WebSocket)에 그대로 붙는 프론트엔드입니다.
`prompt_arena_api_spec.md` 명세(방 생성 → 매칭 → 대전 → 결과)를 따릅니다.

## 1. 준비 (frontend 폴더에서)

```bash
pip install -r requirements.txt
```

필요 패키지: `streamlit`, `websocket-client`, `requests`, `streamlit-autorefresh`

## 2. 실행 (백엔드 먼저!)

**① 백엔드 실행** — 레포의 `backend/` 폴더에서:

```bash
cd backend
pip install -r requirements.txt
python run.py            # http://localhost:8000 에서 실행
```

> AI 모델 키 없이도 동작합니다. 기본값 `ARENA_AI_BACKEND=mock` 이라 정답표를 아는
> 목(mock) 모델이 약 70% 확률로 정답을 냅니다. 실제 Upstage Solar 로 채점하려면:
> `ARENA_AI_BACKEND=upstage UPSTAGE_API_KEY=... python run.py`
> (이때만 결과 화면의 **AI 총평**이 진짜 LLM 평가로 채워집니다.)

streamlit run app.py**② 프론트엔드 실행**:  (터미널에서 Email: 나오면 엔터 누르면 돼요~)

```bash
     # http://localhost:8501
```

백엔드 주소가 다르면, 로그인 화면의 **⚙️ 백엔드 서버 주소 설정** 에서 바꿀 수 있어요.

## 3. 둘이서 대전해보기

대전은 1:1 실시간입니다. 두 개의 세션이 필요해요.

1. **브라우저 탭/창 2개**(또는 서로 다른 두 사람)로 `http://localhost:8501` 접속
2. 각자 닉네임 입력 → 대전 시작
3. A: **방 만들기** → 나온 **4자리 코드**를 B에게 공유
4. B: **친구랑 붙기** 칸에 그 코드 입력 → **입장하기**
5. 둘 다 모이면 자동으로 라운드 시작 → 3분 안에 프롬프트 작성 → 제출
6. 양쪽 제출이 끝나면 채점 후 승패·점수·문제별 정오가 동시에 표시됩니다

> 같은 브라우저의 두 탭은 각각 독립 세션(독립 client_id)으로 동작하므로 혼자서도 테스트할 수 있어요.

## 4. 백엔드와의 매핑

| 화면 | 호출 |
|------|------|
| 로그인 / 전적 | `GET /api/me`, `GET /api/me/history` (X-Client-ID) |
| 방 만들기 | `POST /api/rooms` → 4자리 `room_code` |
| 방 입장 | `GET /api/rooms/{code}` 로 상태 확인 후 WS 연결 |
| 매칭~결과 | `WS /ws/arena/{code}?client_id=…` — `JOIN`/`SUBMIT` 전송, `WAITING`/`ROUND_START`/`RESULT`/`TIMEOUT`/`ERROR` 수신 |

- **신원**: MVP 명세대로 프론트가 만든 UUID 를 `X-Client-ID` 헤더로 사용합니다. (소셜 로그인은 백엔드 v1.1 예정)
- **채점식**: `Score = 0.9 × (정답 수 / N) + 0.1 × √(1 − (L/1200)²)` — 점수 분해를 결과 화면에 그대로 보여줍니다.
- **제한**: 1,200자 / 180초. 초과·미제출은 서버가 자동 패배 처리합니다.

## 5. 구조

WebSocket 은 백그라운드 스레드가 잡고 수신 이벤트를 큐에 쌓습니다.
대기/채점 화면은 `streamlit-autorefresh` 로 폴링하며 큐를 비우고 화면을 갱신합니다.
프롬프트 작성 화면의 타이머·글자수 막대는 입력을 방해하지 않도록 JS 로 매끄럽게 돌아갑니다.

## 참고

- mock 모드에서는 모델의 "대표 출력"이 placeholder 문자열일 수 있고, AI 총평은
  실제 LLM 연결 시에만 표시됩니다(그 외에는 규칙 기반 한 줄 피드백으로 대체).
- 백엔드 v1.2 에서 추가될 토큰 정산/랭킹은 아직 화면에 없습니다(명세 기준).
