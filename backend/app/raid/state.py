"""보스 레이드 그래프 상태와 튜닝 상수.

LangGraph ``StateGraph`` 의 상태 스키마(``BossRaidState``)와, 디렉터의
밸런스 상수를 한곳에 모은다. 상태는 한 라운드를 ``ainvoke`` 로 1회 통과시키며,
캠페인(보스 HP·라운드·난이도·팀 점수)은 서버가 라운드 간에 이어붙인다.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from .effects import NEUTRAL, effect_to_dict

Difficulty = Literal["Low", "Mid", "High"]

# ---------------------------------------------------------------------------
# 밸런스 튜닝 상수
# ---------------------------------------------------------------------------
BOSS_MAX_HP: float = 100.0
MAX_ROUNDS: int = 6
START_DIFFICULTY: Difficulty = "Mid"

# 라운드 점수(개인) 0~1 을 보스 데미지로 환산하는 계수.
SCORE_THRESHOLD: float = 0.5     # 명세 Node3 분기 기준
HIGH_DMG: float = 12.0           # 보상(점수 > 0.5): 큰 데미지 계수
LOW_DMG: float = 5.0             # 패널티(점수 ≤ 0.5): 최소 데미지 계수
DIFFICULTY_MULT: dict[str, float] = {"Low": 0.9, "Mid": 1.0, "High": 1.2}


# ---------------------------------------------------------------------------
# 그래프 상태 스키마
# ---------------------------------------------------------------------------
class BossRaidState(TypedDict, total=False):
    # --- 캠페인 (라운드 간 유지) -----------------------------------------
    current_round: int
    max_rounds: int
    boss_hp: float
    boss_max_hp: float
    team_score: float
    current_difficulty: Difficulty

    # --- 런타임 의존성 (서버가 주입, 노드는 읽기만) ----------------------
    task: Any            # app.arena.domain.Task (이번 라운드 과제)
    model: str
    ai_client: Any       # app.arena.ai_client.AIClient
    max_retries: int
    base_char_limit: int  # 기본 글자수 제한(버프 시 복원 기준)

    # --- 이번 라운드 입력 (서버가 제출을 모아 주입) ----------------------
    p1_prompt: str
    p2_prompt: str
    p1_char_limit: int    # 이번 라운드 p1 에 적용된 글자수 제한
    p2_char_limit: int
    p1_valid: bool        # False = 타임아웃/금칙/초과 → 점수 0 강제
    p2_valid: bool
    p1_elapsed: float     # 이번 라운드 p1 제출까지 걸린 시간(초)
    p2_elapsed: float
    time_limit: float     # 이번 라운드 기준 제한시간(디렉터의 제출시간 정규화용)
    p1_effect: dict       # 이번 라운드 p1 활성 효과(직렬화 dict)
    p2_effect: dict

    # --- input_execution 산출 -------------------------------------------
    p1_grade: dict
    p2_grade: dict

    # --- scoring 산출 ----------------------------------------------------
    p1_score: float
    p2_score: float
    p1_damage: float
    p2_damage: float
    p1_next_status: str
    p2_next_status: str
    p1_next_char_limit: int
    p2_next_char_limit: int
    p1_buff: bool
    p2_buff: bool
    p1_next_effect: dict    # 디렉터가 정한 다음 라운드 p1 효과(직렬화 dict)
    p2_next_effect: dict
    director_rationale: str  # 디렉터 결정 근거(LLM/휴리스틱)
    played_difficulty: Difficulty
    round_score: float       # 팀 신호 = mean(p1_score, p2_score)
    damage_dealt: float      # = p1_damage + p2_damage

    # --- end_check 산출 --------------------------------------------------
    victory: bool
    game_over: bool
    round_log: list


def new_campaign_state(
    *,
    model: str,
    ai_client: Any,
    max_retries: int,
    base_char_limit: int,
) -> BossRaidState:
    """레이드 시작 시 캠페인 초기 상태를 만든다."""
    return BossRaidState(
        current_round=1,
        max_rounds=MAX_ROUNDS,
        boss_hp=BOSS_MAX_HP,
        boss_max_hp=BOSS_MAX_HP,
        team_score=0.0,
        current_difficulty=START_DIFFICULTY,
        model=model,
        ai_client=ai_client,
        max_retries=max_retries,
        base_char_limit=base_char_limit,
        round_log=[],
        p1_effect=effect_to_dict(NEUTRAL),
        p2_effect=effect_to_dict(NEUTRAL),
    )
