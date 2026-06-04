from __future__ import annotations

import requests
import streamlit as st

import api_client
import state as s
import ws_client


def render() -> None:
    st.title("⚔️ Prompt Arena")
    st.caption("프롬프트로 승부하라")
    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🆕 새 방 만들기", use_container_width=True):
            _create_room()

    with col2:
        if st.button("🚪 방 참여하기", use_container_width=True):
            st.session_state["_show_join_input"] = True

    if st.session_state.get("_show_join_input"):
        code = st.text_input("방 코드 입력 (4자리)", max_chars=4, key="join_code_input")
        if st.button("입장", key="join_btn"):
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
