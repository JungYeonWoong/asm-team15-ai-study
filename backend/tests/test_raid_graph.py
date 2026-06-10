"""보스 레이드 LangGraph 디렉터(노드/조건부 엣지) 단위 테스트.

한 라운드를 그래프로 통과시켜 개인 점수·합산 데미지·난이도 분기·상태효과·
종료 조건을 결정론적으로 검증한다.
"""

from __future__ import annotations

from app.arena.ai_client import MockAIClient
from app.raid.graph import build_raid_graph
from app.raid.state import BOSS_MAX_HP, new_campaign_state

from .conftest import ANSWER_KEY, TEST_TASK, make_scripted_ai

GRAPH = build_raid_graph()


def make_state(client, **over) -> dict:
    st = new_campaign_state(
        model="M", ai_client=client, max_retries=2, base_char_limit=1200
    )
    st.update({
        "task": TEST_TASK,
        "model": TEST_TASK.model,
        "ai_client": client,
        "p1_prompt": "do", "p2_prompt": "go",
        "p1_char_limit": 1200, "p2_char_limit": 1200,
        "p1_valid": True, "p2_valid": True,
        # 디렉터 제출시간 정규화용: 기본은 '느리게'(time_limit 만큼 소요).
        "time_limit": 10.0,
        "p1_elapsed": 10.0, "p2_elapsed": 10.0,
    })
    st.update(over)
    return st


async def test_strong_fast_round_raises_difficulty_and_power_buff():
    client = MockAIClient(answer_key=ANSWER_KEY, accuracy=1.0)
    # 빠르게 제출(시간 비율 < 0.5) + 정확 → 보상 분기.
    out = await GRAPH.ainvoke(make_state(client, p1_elapsed=2.0, p2_elapsed=2.0))

    assert out["p1_score"] > 0.5 and out["p2_score"] > 0.5
    assert out["damage_dealt"] > 0
    assert out["boss_hp"] < BOSS_MAX_HP
    assert out["current_difficulty"] == "High"      # 빠르고 강함 → High
    assert out["p1_buff"] is True and out["p2_buff"] is True
    assert out["p1_next_effect"]["id"] == "power_strike"
    assert out["game_over"] is False
    assert out["current_round"] == 2                # 다음 라운드로 진행


async def test_strong_slow_round_gives_mid_and_hint_buff():
    client = MockAIClient(answer_key=ANSWER_KEY, accuracy=1.0)
    # 정확하지만 느리게 제출 → 완만 상승(Mid) + 힌트 버프.
    out = await GRAPH.ainvoke(make_state(client))

    assert out["p1_score"] > 0.5 and out["p2_score"] > 0.5
    assert out["current_difficulty"] == "Mid"
    assert out["p1_buff"] is True
    assert out["p1_next_effect"]["id"] == "hint_reveal"


async def test_weak_fast_round_applies_time_pressure_debuff():
    client = MockAIClient(answer_key=ANSWER_KEY, accuracy=0.0)
    # 빠르게 제출했지만 틀림 → 시간 압박 디버프.
    out = await GRAPH.ainvoke(
        make_state(
            client, p1_prompt="x" * 100, p2_prompt="y" * 100,
            p1_elapsed=1.0, p2_elapsed=1.0,
        )
    )

    assert out["round_score"] <= 0.5
    assert out["current_difficulty"] == "Low"
    assert out["p1_buff"] is False
    assert out["p1_next_effect"]["id"] == "time_pressure"


async def test_weak_round_lowers_difficulty_and_applies_debuff():
    client = MockAIClient(answer_key=ANSWER_KEY, accuracy=0.0)
    out = await GRAPH.ainvoke(
        make_state(client, p1_prompt="x" * 100, p2_prompt="y" * 100)
    )

    assert out["round_score"] <= 0.5
    assert out["current_difficulty"] == "Low"       # 패널티 분기
    assert out["p1_buff"] is False and out["p2_buff"] is False
    assert out["p1_next_char_limit"] == 600          # 1200 * 0.5 디버프
    assert out["damage_dealt"] < 5                    # 최소 데미지


async def test_boss_defeated_sets_victory():
    client = MockAIClient(answer_key=ANSWER_KEY, accuracy=1.0)
    out = await GRAPH.ainvoke(make_state(client, boss_hp=5.0))

    assert out["boss_hp"] == 0
    assert out["victory"] is True
    assert out["game_over"] is True
    assert out["current_round"] == 1                 # 종료 시 증가하지 않음


async def test_round_six_defeat_if_boss_alive():
    client = MockAIClient(answer_key=ANSWER_KEY, accuracy=0.0)
    out = await GRAPH.ainvoke(
        make_state(client, current_round=6, p1_prompt="x" * 50, p2_prompt="y" * 50)
    )

    assert out["game_over"] is True
    assert out["victory"] is False
    assert out["boss_hp"] > 0


async def test_one_strong_one_weak_still_progresses():
    client = make_scripted_ai({"STRONG": ["a", "b", "c", "d"]})
    out = await GRAPH.ainvoke(
        make_state(client, p1_prompt="STRONG", p2_prompt="WEAK")
    )

    assert out["p1_score"] > 0.5 and out["p2_score"] <= 0.5
    assert out["p1_damage"] > out["p2_damage"]       # 잘하는 사람 기여 보장
    assert out["p1_buff"] is True and out["p2_buff"] is False
    assert out["damage_dealt"] > 0                    # 약한 팀원에 발목 안 잡힘


async def test_invalid_submission_scores_zero():
    client = MockAIClient(answer_key=ANSWER_KEY, accuracy=1.0)
    out = await GRAPH.ainvoke(
        make_state(client, p2_valid=False, p2_prompt="")
    )

    assert out["p2_score"] == 0.0
    assert out["p2_damage"] == 0.0
    assert out["p1_score"] > 0.5                      # 유효한 동료는 정상 채점
