# Frontend 디자인 시스템 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Streamlit 프론트엔드에 크림 배경·오렌지 포인트·Noto Sans KR·카드 레이아웃 디자인 시스템 적용

**Architecture:** `style.py`에서 CSS를 전역 inject하고 `app.py`에서 1회 호출. 각 화면은 `st.container(border=True)` 카드 컴포넌트로 그룹핑하고 이모지를 제거. 로직 변경 없음.

**Tech Stack:** Streamlit 1.35+, st.container(border=True), st.markdown(unsafe_allow_html=True), Google Fonts

---

## 개발 규칙

- 태스크 하나 완료 → 버그 수정 → 테스트 가이드 제공 → 사용자 승인 → 다음 태스크
- 로직(상태 관리, WS, API 호출) 수정 금지 — CSS·레이아웃·텍스트만

---

## 파일 맵

| 파일 | 변경 내용 |
|------|-----------|
| `frontend/style.py` (신규) | `apply()` — CSS 전역 inject |
| `frontend/app.py` | `style.apply()` 1줄 추가 |
| `frontend/screens/home.py` | 카드 레이아웃 + 이모지 제거 |
| `frontend/screens/waiting.py` | 카드 레이아웃 + 이모지 제거 |
| `frontend/screens/round.py` | 카드 레이아웃 + 이모지 제거 |
| `frontend/screens/result.py` | 카드 레이아웃 + 이모지 제거 |

---

## Task 1: style.py + app.py 연결

**Files:**
- Create: `frontend/style.py`
- Modify: `frontend/app.py`

- [ ] **Step 1: style.py 생성**

```python
from __future__ import annotations

import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    background-color: #FFFBF0;
    font-family: 'Noto Sans KR', sans-serif;
}

[data-testid="stMain"] {
    background-color: #FFFBF0;
}

h1, h2, h3 {
    font-family: 'Noto Sans KR', sans-serif;
    font-weight: 700;
    color: #2D2D2D;
}

[data-testid="stBaseButton-primary"] {
    background-color: #FF8C00 !important;
    border: none !important;
    color: white !important;
}
[data-testid="stBaseButton-primary"]:hover {
    background-color: #FFB347 !important;
}

[data-testid="stBaseButton-secondary"] {
    border: 1.5px solid #FF8C00 !important;
    color: #FF8C00 !important;
}

[data-testid="stMetricLabel"] {
    color: #FF8C00;
    font-weight: 700;
}

[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px !important;
    border-color: #FFE0B2 !important;
    box-shadow: 0 2px 8px rgba(255, 140, 0, 0.08) !important;
    padding: 4px !important;
}
</style>
"""


def apply() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
```

- [ ] **Step 2: app.py에 style.apply() 추가**

`frontend/app.py` 전체:

```python
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import streamlit as st

import state as s
import style
from screens import home, waiting, result
from screens import round as round_screen

st.set_page_config(page_title="Prompt Arena", page_icon="⚔️", layout="centered")

style.apply()
s.init_state()

screen = st.session_state[s.SCREEN]

if screen == "home":
    home.render()
elif screen == "waiting":
    waiting.render()
elif screen == "round":
    round_screen.render()
elif screen == "result":
    result.render()
else:
    st.error(f"알 수 없는 화면: {screen}")
```

- [ ] **Step 3: 실행 확인**

```powershell
cd frontend
.\.venv\Scripts\Activate.ps1
streamlit run app.py
```

확인:
- 배경색 크림(#FFFBF0) 적용 여부
- Noto Sans KR 폰트 로드 여부 (브라우저 개발자도구 → Network → fonts.googleapis.com)
- 제목 색상 #2D2D2D 적용 여부

- [ ] **Step 4: 커밋**

```bash
git add frontend/style.py frontend/app.py
git commit -m "feat: 디자인 시스템 style.py 추가 및 app.py 연결"
```

---

## Task 2: 홈 화면 카드 레이아웃

**Files:**
- Modify: `frontend/screens/home.py`

- [ ] **Step 1: home.py 전체 교체**

```python
from __future__ import annotations

import requests
import streamlit as st

import api_client
import state as s
import ws_client


def render() -> None:
    st.title("Prompt Arena")
    st.caption("프롬프트로 승부하라")
    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.write("**새 방 만들기**")
            st.caption("방을 생성하고 코드를 상대에게 공유하세요.")
            if st.button("새 방 만들기", use_container_width=True, type="primary"):
                _create_room()

    with col2:
        with st.container(border=True):
            st.write("**방 참여하기**")
            st.caption("상대방에게 받은 4자리 코드를 입력하세요.")
            code = st.text_input(
                "방 코드",
                max_chars=4,
                key="join_code_input",
                label_visibility="collapsed",
                placeholder="0000",
            )
            if st.button("입장", use_container_width=True, type="secondary"):
                if len(code) == 4:
                    _join_room(code)
                else:
                    st.error("방 코드는 4자리 숫자입니다.")


def _create_room() -> None:
    client_id = st.session_state[s.CLIENT_ID]
    try:
        room_code = api_client.create_room(client_id)
        st.session_state[s.ROOM_CODE] = room_code
        _connect_ws_and_go_waiting()
    except Exception as e:
        st.error(f"방 생성 실패: {e}")


def _join_room(room_code: str) -> None:
    try:
        room = api_client.get_room(room_code)
        if room["status"] not in ("WAITING",):
            st.error("입장할 수 없는 방입니다. (이미 시작되었거나 존재하지 않음)")
            return
        st.session_state[s.ROOM_CODE] = room_code
        _connect_ws_and_go_waiting()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            st.error("존재하지 않는 방 코드입니다.")
        else:
            st.error(f"오류: {e}")
    except Exception as e:
        st.error(f"서버에 연결할 수 없습니다: {e}")


def _connect_ws_and_go_waiting() -> None:
    client_id = st.session_state[s.CLIENT_ID]
    room_code = st.session_state[s.ROOM_CODE]
    q = st.session_state[s.WS_QUEUE]
    try:
        ws = ws_client.connect(room_code, client_id)
        t = ws_client.start_recv_thread(ws, q)
        ws_client.send_join(ws)
        st.session_state[s.WS_OBJECT] = ws
        st.session_state[s.WS_THREAD] = t
        st.session_state[s.WS_CONNECTED] = True
        st.session_state[s.SCREEN] = "waiting"
        st.rerun()
    except Exception as e:
        st.error(f"게임 서버 연결 실패: {e}")
```

- [ ] **Step 2: 커밋**

```bash
git add frontend/screens/home.py
git commit -m "design: 홈 화면 카드 레이아웃 + 이모지 제거"
```

---

## Task 3: 대기 화면 카드 레이아웃

**Files:**
- Modify: `frontend/screens/waiting.py`

- [ ] **Step 1: waiting.py 전체 교체**

```python
from __future__ import annotations

import queue as q_module
import time

import streamlit as st
from streamlit_autorefresh import st_autorefresh

import state as s
import ws_client


def render() -> None:
    st_autorefresh(interval=500, key="waiting_refresh")

    room_code = st.session_state[s.ROOM_CODE]
    st.title("대기 중")
    st.divider()

    with st.container(border=True):
        st.write("**방 코드**")
        st.code(room_code, language=None)
        st.caption("상대방에게 이 코드를 알려주세요.")

    st.info("상대방을 기다리는 중입니다...")

    if st.button("취소", use_container_width=True, type="secondary"):
        _leave()
        return

    _poll_events()


def _leave() -> None:
    ws = st.session_state.get(s.WS_OBJECT)
    if ws:
        ws_client.close(ws)
    s.reset_game_state()
    st.session_state[s.SCREEN] = "home"
    st.rerun()


def _poll_events() -> None:
    ws_queue: q_module.Queue = st.session_state[s.WS_QUEUE]
    changed = False

    while True:
        try:
            event = ws_queue.get_nowait()
        except q_module.Empty:
            break

        ev = event.get("event")

        if ev == "ROUND_START":
            st.session_state[s.TASK] = event["task"]
            st.session_state[s.MODEL] = event["model"]
            st.session_state[s.TIME_LIMIT] = event["time_limit"]
            st.session_state[s.ROUND_START_AT] = time.time()
            st.session_state[s.SCREEN] = "round"
            changed = True

        elif ev == "WAITING":
            pass

        elif ev == "WS_CLOSED":
            st.error("서버 연결이 끊어졌습니다.")
            st.session_state[s.SCREEN] = "home"
            s.reset_game_state()
            changed = True

        elif ev == "ERROR":
            st.error(event.get("message", "오류가 발생했습니다."))
            st.session_state[s.SCREEN] = "home"
            s.reset_game_state()
            changed = True

    if changed:
        st.rerun()
```

- [ ] **Step 2: 커밋**

```bash
git add frontend/screens/waiting.py
git commit -m "design: 대기 화면 카드 레이아웃 + 이모지 제거"
```

---

## Task 4: 라운드 화면 카드 레이아웃

**Files:**
- Modify: `frontend/screens/round.py`

- [ ] **Step 1: round.py 전체 교체**

```python
from __future__ import annotations

import queue as q_module
import time

import streamlit as st
from streamlit_autorefresh import st_autorefresh

import state as s
import ws_client


def render() -> None:
    st_autorefresh(interval=1000, key="round_refresh")

    _poll_events()

    task = st.session_state[s.TASK]
    model = st.session_state[s.MODEL]
    time_limit = st.session_state[s.TIME_LIMIT]
    start_at = st.session_state[s.ROUND_START_AT]
    submitted = st.session_state[s.SUBMITTED]

    elapsed = time.time() - start_at
    remaining = max(0.0, time_limit - elapsed)
    minutes = int(remaining) // 60
    seconds = int(remaining) % 60

    st.title("프롬프트 대전")

    with st.container(border=True):
        st.info(f"**과제:** {task}")
        st.caption(f"모델: {model}")

    st.divider()

    if remaining <= 0:
        st.error("시간 초과! 서버 처리 중...")
        return

    st.metric("남은 시간", f"{minutes:02d}:{seconds:02d}")
    st.divider()

    if submitted:
        st.success("제출 완료! 상대방을 기다리는 중...")
        return

    with st.container(border=True):
        prompt = st.text_area(
            "프롬프트를 작성하세요",
            height=220,
            max_chars=1200,
            key="prompt_input",
            placeholder="여기에 프롬프트를 작성하세요...",
        )
        char_count = len(prompt)
        _, right = st.columns([3, 1])
        with right:
            st.caption(f"{char_count} / 1200")

        if st.button("제출", type="primary", use_container_width=True):
            if char_count == 0:
                st.warning("프롬프트를 입력해주세요.")
            else:
                ws = st.session_state[s.WS_OBJECT]
                ws_client.send_submit(ws, prompt)
                st.session_state[s.SUBMITTED] = True
                st.rerun()

    with st.expander("⚙️ 기타"):
        if st.button("대전 포기", type="secondary"):
            _leave()
            return


def _leave() -> None:
    ws = st.session_state.get(s.WS_OBJECT)
    if ws:
        ws_client.close(ws)
    s.reset_game_state()
    st.session_state[s.SCREEN] = "home"
    st.rerun()


def _poll_events() -> None:
    ws_queue: q_module.Queue = st.session_state[s.WS_QUEUE]
    changed = False

    while True:
        try:
            event = ws_queue.get_nowait()
        except q_module.Empty:
            break

        ev = event.get("event")

        if ev in ("RESULT", "TIMEOUT", "ERROR"):
            st.session_state[s.RESULT_PAYLOAD] = event
            st.session_state[s.SCREEN] = "result"
            changed = True

        elif ev == "WS_CLOSED":
            st.session_state[s.RESULT_PAYLOAD] = {
                "event": "ERROR",
                "code": "WS_CLOSED",
                "message": "서버 연결이 끊어졌습니다.",
            }
            st.session_state[s.SCREEN] = "result"
            changed = True

        elif ev == "WAITING":
            pass

    if changed:
        st.rerun()
```

- [ ] **Step 2: 커밋**

```bash
git add frontend/screens/round.py
git commit -m "design: 라운드 화면 카드 레이아웃 + 글자수 우측 정렬 + 이모지 제거"
```

---

## Task 5: 결과 화면 카드 레이아웃

**Files:**
- Modify: `frontend/screens/result.py`

- [ ] **Step 1: result.py 전체 교체**

```python
from __future__ import annotations

import streamlit as st

import state as s
import ws_client


def render() -> None:
    payload = st.session_state.get(s.RESULT_PAYLOAD) or {}
    event_type = payload.get("event", "RESULT")

    _show_banner(event_type, payload)

    if event_type == "RESULT" and payload.get("my_data"):
        st.divider()
        _show_comparison(payload)

    st.divider()
    if st.button("다시 하기", use_container_width=True, type="primary"):
        _go_home()


def _show_banner(event_type: str, payload: dict) -> None:
    if event_type == "RESULT":
        result = payload.get("result", "")
        if result == "WIN":
            st.success("🏆 승리!")
        elif result == "LOSE":
            st.error("패배")
        elif result == "DRAW":
            st.warning("무승부")
        else:
            st.info("결과를 불러오는 중...")

    elif event_type == "TIMEOUT":
        st.error("시간 초과 — 자동 패배")

    elif event_type == "ERROR":
        code = payload.get("code", "")
        msg = payload.get("message", "오류가 발생했습니다.")
        if code == "OPPONENT_DISCONNECTED":
            st.success("상대방 연결 끊김 — 부전승")
        elif code == "AI_CALL_FAILED":
            st.warning(f"AI 호출 실패 — 라운드 무효\n{msg}")
        elif code == "WS_CLOSED":
            st.error("서버 연결이 끊어졌습니다. 다시 시도해주세요.")
        else:
            st.error(msg)

    else:
        st.info("결과를 불러오는 중...")


def _show_comparison(payload: dict) -> None:
    my = payload.get("my_data") or {}
    opp = payload.get("opponent_data") or {}

    st.subheader("결과 비교")
    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("**나**")
            st.text_area(
                "내 프롬프트",
                value=my.get("prompt", ""),
                height=150,
                disabled=True,
                key="my_prompt",
            )
            st.text_area(
                "AI 응답",
                value=my.get("ai_response", ""),
                height=100,
                disabled=True,
                key="my_response",
            )
            st.metric("정답", f"{my.get('correct_count', 0)} / {my.get('total_count', 0)}")
            st.metric("점수", f"{my.get('score', 0):.4f}")

    with col2:
        with st.container(border=True):
            st.markdown("**상대**")
            st.text_area(
                "상대 프롬프트",
                value=opp.get("prompt", ""),
                height=150,
                disabled=True,
                key="opp_prompt",
            )
            st.text_area(
                "AI 응답",
                value=opp.get("ai_response", ""),
                height=100,
                disabled=True,
                key="opp_response",
            )
            st.metric("정답", f"{opp.get('correct_count', 0)} / {opp.get('total_count', 0)}")
            st.metric("점수", f"{opp.get('score', 0):.4f}")


def _go_home() -> None:
    ws = st.session_state.get(s.WS_OBJECT)
    if ws:
        ws_client.close(ws)
    s.reset_game_state()
    st.session_state[s.SCREEN] = "home"
    st.rerun()
```

- [ ] **Step 2: 커밋**

```bash
git add frontend/screens/result.py
git commit -m "design: 결과 화면 카드 레이아웃 + 이모지 제거 (WIN 🏆만 유지)"
```
