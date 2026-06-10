"""보스 레이드 LangGraph 디렉터.

한 라운드를 처리하는 ``StateGraph`` 를 컴파일한다. 보스 크리틱은
조건부 엣지(``add_conditional_edges``)로 다음 라운드 난이도를 분기한다.

  START → input_execution → scoring → boss_critic → end_check → END

``boss_critic`` 은 디렉터(LLM+휴리스틱)로, 제출 점수·시간·프롬프트를 보고 다음
라운드 난이도와 플레이어별 버프/디버프를 정한다.

체크포인터 없이 라운드마다 1회 ``ainvoke`` 한다. 라운드 간 캠페인 상태
(보스 HP·라운드·난이도·팀 점수·다음 효과)는 RaidServer 가 이어붙인다.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import (
    boss_critic,
    end_check,
    input_execution,
    scoring,
)
from .state import BossRaidState


def build_raid_graph():
    """보스 레이드 라운드 그래프를 빌드/컴파일한다."""
    graph = StateGraph(BossRaidState)

    graph.add_node("input_execution", input_execution)
    graph.add_node("scoring", scoring)
    graph.add_node("boss_critic", boss_critic)
    graph.add_node("end_check", end_check)

    graph.add_edge(START, "input_execution")
    graph.add_edge("input_execution", "scoring")
    graph.add_edge("scoring", "boss_critic")
    graph.add_edge("boss_critic", "end_check")
    graph.add_edge("end_check", END)

    return graph.compile()
