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
