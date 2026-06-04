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
            st.write("")
            st.markdown("#### 새 방 만들기")
            st.caption("방을 생성하면 4자리 코드가 발급됩니다.")
            st.caption("상대방에게 코드를 공유하고 입장을 기다리세요.")
            st.write("")
            st.write("")
            if st.button("새 방 만들기", use_container_width=True, type="primary"):
                _create_room()
            st.write("")

    with col2:
        with st.container(border=True):
            st.write("")
            st.markdown("#### 방 참여하기")
            st.caption("상대방에게 받은 4자리 코드를 입력하세요.")
            st.write("")
            code = st.text_input(
                "방 코드",
                max_chars=4,
                key="join_code_input",
                placeholder="0000",
            )
            if st.button("입장", use_container_width=True, type="secondary"):
                if len(code) == 4:
                    _join_room(code)
                else:
                    st.error("방 코드는 4자리 숫자입니다.")
            st.write("")


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
