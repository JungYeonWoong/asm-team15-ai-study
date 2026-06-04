# Prompt Arena — Frontend (Streamlit)

## 구조

```
frontend/
├── app.py              # 진입점 — screen 라우팅
├── state.py            # session_state 키 상수 + init/reset
├── api_client.py       # REST 호출 (방 생성/조회)
├── ws_client.py        # WebSocket 연결·수신 스레드
├── screens/
│   ├── home.py         # 홈 화면 (방 만들기 / 참여하기)
│   ├── waiting.py      # 대기 화면 (방 코드 표시)
│   ├── round.py        # 라운드 화면 (타이머 + 프롬프트 작성)
│   └── result.py       # 결과 화면 (승패 + 비교)
├── requirements.txt
└── .env
```

## 실행

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

`http://localhost:8501`

## 환경 변수 (`.env`)

```
BACKEND_URL=http://localhost:8000
WS_URL=ws://localhost:8000
```

## 화면 흐름

```
home → waiting → round → result → home
```

화면 전환: `st.session_state["screen"]` 변경 후 `st.rerun()`

## WebSocket 구조

```
[Streamlit 서버]
  ws_client.connect()       # 게임 WS 연결
  ws_client.start_recv_thread(ws, queue)  # 백그라운드 수신
  ws_client.send_join(ws)   # JOIN 전송

[백그라운드 스레드]
  ws.recv() → queue.put(event)

[각 화면 render()]
  queue.get_nowait() → 이벤트 처리 → st.rerun()
```
