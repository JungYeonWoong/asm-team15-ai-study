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
