"""보스 레이드 디렉터(LLM + 휴리스틱) 단위 테스트."""

from __future__ import annotations

from app.arena.ai_client import CallableAIClient, MockAIClient
from app.raid.director import (
    Decision,
    decide_next,
    heuristic_decision,
)


def _state(**over) -> dict:
    st = {
        "time_limit": 10.0,
        "current_difficulty": "Mid",
        "p1_prompt": "p1", "p2_prompt": "p2",
        "p1_score": 0.0, "p2_score": 0.0,
        "p1_elapsed": 10.0, "p2_elapsed": 10.0,
        "round_score": 0.0,
        "max_retries": 2,
    }
    st.update(over)
    return st


# ---------------------------------------------------------------------------
# 휴리스틱 2×2 매트릭스 (점수 × 제출시간)
# ---------------------------------------------------------------------------
def test_strong_fast_player_gets_power_strike():
    d = heuristic_decision(_state(p1_score=0.9, p1_elapsed=2.0))
    assert d.p1_effect.id == "power_strike"
    assert d.p1_effect.kind == "buff"


def test_strong_slow_player_gets_hint_reveal():
    d = heuristic_decision(_state(p1_score=0.9, p1_elapsed=9.5))
    assert d.p1_effect.id == "hint_reveal"


def test_weak_fast_player_gets_time_pressure():
    d = heuristic_decision(_state(p1_score=0.1, p1_elapsed=1.0))
    assert d.p1_effect.id == "time_pressure"
    assert d.p1_effect.kind == "debuff"


def test_weak_slow_player_gets_char_squeeze():
    d = heuristic_decision(_state(p1_score=0.1, p1_elapsed=10.0))
    assert d.p1_effect.id == "char_squeeze"


def test_difficulty_scales_with_team_score_and_speed():
    # 빠르고 강한 팀 → High
    fast_strong = heuristic_decision(
        _state(round_score=0.9, p1_elapsed=2.0, p2_elapsed=2.0)
    )
    assert fast_strong.next_difficulty == "High"
    # 강하지만 느린 팀 → Mid (완만 상승)
    slow_strong = heuristic_decision(_state(round_score=0.9))
    assert slow_strong.next_difficulty == "Mid"
    # 약한 팀 → Low
    weak = heuristic_decision(_state(round_score=0.2))
    assert weak.next_difficulty == "Low"


def test_missing_time_treated_as_slow():
    # 제출시간 정보가 없으면 보수적으로 '느림'으로 본다.
    d = heuristic_decision(
        {"p1_score": 0.9, "p2_score": 0.9, "round_score": 0.9}
    )
    assert d.next_difficulty == "Mid"
    assert d.p1_effect.id == "hint_reveal"


# ---------------------------------------------------------------------------
# decide_next: MockAIClient → 휴리스틱 직행
# ---------------------------------------------------------------------------
async def test_mock_client_uses_heuristic():
    client = MockAIClient()
    d = await decide_next(client, "M", _state(p1_score=0.9, p1_elapsed=2.0))
    assert d.p1_effect.id == "power_strike"


# ---------------------------------------------------------------------------
# decide_next: 실제(콜러블) LLM 경로
# ---------------------------------------------------------------------------
async def test_llm_json_decision_is_used():
    payload = (
        '여기 결정입니다: {"difficulty":"High","p1_effect_id":"free_length",'
        '"p2_effect_id":"score_surge","rationale":"P1 프롬프트가 길어 글자 완화"} 끝.'
    )
    client = CallableAIClient(lambda m, p, t: payload)
    d = await decide_next(client, "M", _state(p1_score=0.1))  # 휴리스틱과 다른 값
    assert d.next_difficulty == "High"
    assert d.p1_effect.id == "free_length"
    assert d.p2_effect.id == "score_surge"
    assert "글자" in d.rationale


async def test_llm_invalid_json_falls_back_to_heuristic():
    client = CallableAIClient(lambda m, p, t: "그냥 잡담, JSON 아님")
    d = await decide_next(
        client, "M", _state(p1_score=0.9, p1_elapsed=2.0)
    )
    # 파싱 실패 → 휴리스틱(빠르고 강함 → power_strike)
    assert d.p1_effect.id == "power_strike"


async def test_llm_unknown_effect_id_falls_back_per_field():
    # difficulty 는 유효, p1_effect_id 는 무효 → 해당 필드만 휴리스틱 폴백.
    client = CallableAIClient(
        lambda m, p, t: '{"difficulty":"Low","p1_effect_id":"bogus",'
        '"p2_effect_id":"hint_reveal"}'
    )
    d = await decide_next(client, "M", _state(p1_score=0.1, p1_elapsed=1.0))
    assert isinstance(d, Decision)
    assert d.next_difficulty == "Low"
    assert d.p1_effect.id == "time_pressure"   # 휴리스틱 폴백(약함+빠름)
    assert d.p2_effect.id == "hint_reveal"      # LLM 값 유지
