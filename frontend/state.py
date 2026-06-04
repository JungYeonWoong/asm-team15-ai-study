from __future__ import annotations

import queue
import uuid

import streamlit as st

# 네비게이션
SCREEN = "screen"

# 세션 식별
CLIENT_ID = "client_id"

# 방 정보
ROOM_CODE = "room_code"

# WebSocket
WS_THREAD = "ws_thread"
WS_QUEUE = "ws_queue"
WS_CONNECTED = "ws_connected"
WS_OBJECT = "ws_object"

# 라운드 데이터
TASK = "task"
MODEL = "model"
TIME_LIMIT = "time_limit"
ROUND_START_AT = "round_start_at"

# 결과
RESULT_PAYLOAD = "result_payload"

# 제출 상태
SUBMITTED = "submitted"


def init_state() -> None:
    defaults = {
        SCREEN: "home",
        CLIENT_ID: str(uuid.uuid4()),
        ROOM_CODE: "",
        WS_THREAD: None,
        WS_QUEUE: queue.Queue(),
        WS_CONNECTED: False,
        WS_OBJECT: None,
        TASK: "",
        MODEL: "",
        TIME_LIMIT: 180,
        ROUND_START_AT: 0.0,
        RESULT_PAYLOAD: None,
        SUBMITTED: False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def reset_game_state() -> None:
    game_keys = [
        ROOM_CODE, WS_THREAD, WS_CONNECTED, WS_OBJECT,
        TASK, MODEL, ROUND_START_AT, RESULT_PAYLOAD, SUBMITTED,
        "_show_join_input", "join_code_input",
    ]
    for key in game_keys:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state[WS_QUEUE] = queue.Queue()
