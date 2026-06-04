from __future__ import annotations

import queue as q_module
import time

import streamlit as st
from streamlit_autorefresh import st_autorefresh

import state as s


def render() -> None:
    st_autorefresh(interval=500, key="waiting_refresh")

    room_code = st.session_state[s.ROOM_CODE]
    st.title("⏳ 대기 중")
    st.write("방 코드를 상대방에게 알려주세요.")
    st.code(room_code, language=None)
    st.info("상대방을 기다리는 중입니다...")

    _poll_events()


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
            pass  # 이미 대기 화면, 무시

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
