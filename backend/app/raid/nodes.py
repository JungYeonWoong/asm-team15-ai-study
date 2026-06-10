"""보스 레이드 그래프 노드.

명세의 Node1~4 를 비동기/동기 함수로 구현한다. 기존 채점/평가/점수 유틸을 재사용한다.

  Node1 input_execution : 두 플레이어 프롬프트를 같은 Base 모델에 병렬 실행
  Node2 scoring         : 개인 점수(활성 효과 배율 반영) → 개인 데미지 합산 → 보스 HP 차감
  Node3 boss_critic     : 디렉터(LLM+휴리스틱)가 다음 난이도 + 플레이어별 다음 효과 결정
  Node4 end_check       : 라운드 6 도달 또는 보스 HP 0 → 종료/승패 판정
"""

from __future__ import annotations

import asyncio

from app.arena import ai_client as ai
from app.arena.scoring import compute_score

from . import director as director_mod
from .effects import effect_from_dict, effect_to_dict
from .state import (
    DIFFICULTY_MULT,
    HIGH_DMG,
    LOW_DMG,
    SCORE_THRESHOLD,
    BossRaidState,
)


# ---------------------------------------------------------------------------
# Node 1 — 입력 & 실행
# ---------------------------------------------------------------------------
async def input_execution(state: BossRaidState) -> dict:
    """두 플레이어의 프롬프트를 같은 모델/과제에 병렬로 실행해 채점 결과를 만든다.

    빈/무효 프롬프트는 AI 를 호출하지 않는다(비용 방어). AI 호출이 재시도 끝에
    실패하면 :class:`ai.AICallError` 가 전파되어 서버가 라운드 재시도를 안내한다.
    """
    task = state["task"]
    client = state["ai_client"]
    model = state["model"]
    retries = state["max_retries"]

    async def run_one(prompt: str, valid: bool) -> dict:
        empty_result = {
            "correct_count": 0,
            "total_count": task.total_count,
            "ai_response": "",
            "test_case_results": [],
            "prompt_evaluation": "",
        }
        if not valid or not prompt.strip():
            return empty_result
        correct, total, sample, cases = await ai.grade(
            client, model, prompt, task.test_cases, max_retries=retries
        )
        outputs = [c["actual"] for c in cases]
        evaluation = await ai.evaluate_prompt(
            client, model, prompt, task.test_cases, outputs, max_retries=retries
        )
        return {
            "correct_count": correct,
            "total_count": total,
            "ai_response": sample,
            "test_case_results": cases,
            "prompt_evaluation": evaluation,
        }

    g1, g2 = await asyncio.gather(
        run_one(state.get("p1_prompt", ""), state.get("p1_valid", True)),
        run_one(state.get("p2_prompt", ""), state.get("p2_valid", True)),
    )
    return {"p1_grade": g1, "p2_grade": g2}


# ---------------------------------------------------------------------------
# Node 2 — 채점 (개인 점수 → 개인 데미지 합산, 이번 라운드 활성 효과 배율 반영)
# ---------------------------------------------------------------------------
def _eval_player(
    grade: dict,
    prompt: str,
    char_limit: int,
    valid: bool,
    difficulty: str,
    effect_data: dict,
) -> dict:
    """한 플레이어의 점수·데미지를 계산한다(활성 효과 배율 반영)."""
    effect = effect_from_dict(effect_data)
    if not valid:
        score = 0.0
    else:
        score = compute_score(
            grade["correct_count"], grade["total_count"], len(prompt), char_limit
        )
        # 활성 효과의 점수 배율 적용(0~1 로 clamp).
        score = max(0.0, min(score * effect.score_multiplier, 1.0))

    base_dmg = HIGH_DMG if score > SCORE_THRESHOLD else LOW_DMG
    damage = score * base_dmg * DIFFICULTY_MULT.get(difficulty, 1.0)
    damage *= effect.damage_multiplier
    return {"score": round(score, 4), "damage": round(damage, 2)}


def scoring(state: BossRaidState) -> dict:
    diff = state["current_difficulty"]
    base = state["base_char_limit"]

    e1 = _eval_player(
        state["p1_grade"], state.get("p1_prompt", ""),
        state.get("p1_char_limit", base), state.get("p1_valid", True),
        diff, state.get("p1_effect", {}),
    )
    e2 = _eval_player(
        state["p2_grade"], state.get("p2_prompt", ""),
        state.get("p2_char_limit", base), state.get("p2_valid", True),
        diff, state.get("p2_effect", {}),
    )

    damage_dealt = e1["damage"] + e2["damage"]
    boss_hp = max(0.0, state["boss_hp"] - damage_dealt)
    round_score = round((e1["score"] + e2["score"]) / 2, 4)
    team_score = round(state.get("team_score", 0.0) + e1["score"] + e2["score"], 4)

    return {
        "p1_score": e1["score"], "p2_score": e2["score"],
        "p1_damage": e1["damage"], "p2_damage": e2["damage"],
        "played_difficulty": diff,
        "round_score": round_score,
        "damage_dealt": round(damage_dealt, 2),
        "boss_hp": round(boss_hp, 2),
        "team_score": team_score,
    }


# ---------------------------------------------------------------------------
# Node 3 — 보스 크리틱 (디렉터: 다음 난이도 + 플레이어별 다음 효과)
# ---------------------------------------------------------------------------
async def boss_critic(state: BossRaidState) -> dict:
    """디렉터를 호출해 다음 라운드 난이도와 플레이어별 효과를 정한다.

    제출 점수·시간·프롬프트를 근거로 LLM 이 판단하며, 불가/실패 시 휴리스틱으로
    폴백한다. 효과에서 다음 라운드 글자수 제한/상태 라벨/버프 여부를 파생한다.
    """
    base = state["base_char_limit"]
    decision = await director_mod.decide_next(
        state.get("ai_client"),
        state.get("model", ""),
        state,
        max_retries=state.get("max_retries", 2),
    )

    e1, e2 = decision.p1_effect, decision.p2_effect
    return {
        "current_difficulty": decision.next_difficulty,
        "p1_next_effect": effect_to_dict(e1),
        "p2_next_effect": effect_to_dict(e2),
        "p1_next_status": e1.label,
        "p2_next_status": e2.label,
        "p1_next_char_limit": max(1, int(base * e1.char_limit_factor)),
        "p2_next_char_limit": max(1, int(base * e2.char_limit_factor)),
        "p1_buff": e1.kind == "buff",
        "p2_buff": e2.kind == "buff",
        "director_rationale": decision.rationale,
    }


# ---------------------------------------------------------------------------
# Node 4 — 종료 조건 판정
# ---------------------------------------------------------------------------
def end_check(state: BossRaidState) -> dict:
    boss_hp = state["boss_hp"]
    rnd = state["current_round"]
    max_rounds = state["max_rounds"]

    victory = boss_hp <= 0
    game_over = victory or rnd >= max_rounds

    log = list(state.get("round_log", []))
    log.append({
        "round": rnd,
        "difficulty": state.get("played_difficulty", state["current_difficulty"]),
        "round_score": state["round_score"],
        "damage_dealt": state["damage_dealt"],
        "boss_hp": boss_hp,
        "p1_score": state["p1_score"],
        "p2_score": state["p2_score"],
    })

    out = {"victory": victory, "game_over": game_over, "round_log": log}
    if not game_over:
        out["current_round"] = rnd + 1
    return out
