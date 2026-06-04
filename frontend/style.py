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
