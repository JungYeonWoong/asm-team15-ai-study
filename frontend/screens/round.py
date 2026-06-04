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

    st.title("✍️ 프롬프트 대전")
    st.info(f"**과제:** {task}")
    st.caption(f"모델: {model}")
    st.divider()

    if remaining <= 0:
        st.error("⏰ 시간 초과! 서버 처리 중...")
        return

    st.metric("남은 시간", f"{minutes:02d}:{seconds:02d}")
    st.divider()

    if submitted:
        st.success("✅ 제출 완료! 상대방을 기다리는 중...")
        return

    prompt = st.text_area(
        "프롬프트를 작성하세요",
        height=200,
        max_chars=1200,
        key="prompt_input",
        placeholder="여기에 프롬프트를 작성하세요...",
    )
    char_count = len(prompt)
    st.caption(f"글자수: {char_count} / 1200")

    if st.button("📤 제출", type="primary", use_container_width=True):
        if char_count == 0:
            st.warning("프롬프트를 입력해주세요.")
        else:
            ws = st.session_state[s.WS_OBJECT]
            ws_client.send_submit(ws, prompt)
            st.session_state[s.SUBMITTED] = True
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
            pass  # 제출 후 상대 대기 중, 무시

    if changed:
        st.rerun()
