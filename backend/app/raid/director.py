"""보스 레이드 디렉터 — 다음 라운드 난이도 + 플레이어별 버프/디버프 결정.

핵심 아이디어: "이 사람의 프롬프트를 보니 이렇게 했으니, 이런 문제/효과를 줘야겠다."

- **LLM 경로**: 실제 모델에게 각 플레이어의 프롬프트·점수·제출시간과 효과 카탈로그를
  보여주고 ``{"difficulty","p1_effect_id","p2_effect_id","rationale"}`` JSON 을 받는다.
- **휴리스틱 폴백**: MockAIClient 이거나 LLM 호출/파싱이 실패하면, 점수×제출시간
  2×2 매트릭스로 결정론적으로 정한다(테스트/오프라인에서도 일관).

scoring 노드가 아니라 별도 ``boss_critic`` 노드(async)에서 호출된다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.arena import ai_client as ai
from app.arena.ai_client import AICallError, MockAIClient

from .effects import (
    ALL_EFFECTS,
    BUFF_IDS,
    DEBUFF_IDS,
    NEUTRAL,
    Effect,
    effect_from_id,
)
from .state import SCORE_THRESHOLD, BossRaidState, Difficulty

VALID_DIFFICULTIES: tuple[Difficulty, ...] = ("Low", "Mid", "High")

# 휴리스틱: 제출시간 비율이 이 값보다 작으면 "빠름"으로 본다.
FAST_RATIO: float = 0.5


@dataclass
class Decision:
    """디렉터의 한 라운드 결정."""

    next_difficulty: Difficulty
    p1_effect: Effect
    p2_effect: Effect
    rationale: str = ""


# ---------------------------------------------------------------------------
# 휴리스틱 (결정론적 폴백)
# ---------------------------------------------------------------------------
def _time_ratio(elapsed: float | None, time_limit: float | None) -> float:
    """0(빠름)~1(느림). 정보가 없으면 1.0(느림)으로 보수적으로 본다."""
    if not time_limit or time_limit <= 0:
        return 1.0
    if elapsed is None:
        return 1.0
    return max(0.0, min(elapsed / time_limit, 1.0))


def _heuristic_effect(score: float, elapsed: float | None, time_limit: float | None) -> Effect:
    """개인 점수×제출시간으로 다음 효과를 고른다.

    - 강함+빠름 → power_strike (정확하고 빠른 보상)
    - 강함+느림 → hint_reveal (잘했지만 시간 소모 → 다음 문제 힌트로 가속)
    - 약함+빠름 → time_pressure (서두르다 틀림 → 시간 압박 패널티)
    - 약함+느림 → char_squeeze (헤맴 → 글자수 제한으로 핵심만)
    """
    strong = score > SCORE_THRESHOLD
    fast = _time_ratio(elapsed, time_limit) < FAST_RATIO
    if strong and fast:
        return ALL_EFFECTS["power_strike"]
    if strong and not fast:
        return ALL_EFFECTS["hint_reveal"]
    if not strong and fast:
        return ALL_EFFECTS["time_pressure"]
    return ALL_EFFECTS["char_squeeze"]


def _heuristic_difficulty(
    round_score: float,
    p1_elapsed: float | None,
    p2_elapsed: float | None,
    time_limit: float | None,
) -> Difficulty:
    """팀 라운드 점수(+평균 제출시간)로 다음 난이도를 정한다."""
    if round_score > SCORE_THRESHOLD:
        avg_ratio = (
            _time_ratio(p1_elapsed, time_limit) + _time_ratio(p2_elapsed, time_limit)
        ) / 2
        # 잘하고 빠르면 더 강하게(High), 잘했지만 느리면 Mid 로 완만히 상승.
        return "High" if avg_ratio < FAST_RATIO else "Mid"
    return "Low"


def heuristic_decision(state: BossRaidState) -> Decision:
    """LLM 없이 결정론적으로 다음 라운드를 정한다."""
    time_limit = state.get("time_limit")
    p1_eff = _heuristic_effect(
        state.get("p1_score", 0.0), state.get("p1_elapsed"), time_limit
    )
    p2_eff = _heuristic_effect(
        state.get("p2_score", 0.0), state.get("p2_elapsed"), time_limit
    )
    diff = _heuristic_difficulty(
        state.get("round_score", 0.0),
        state.get("p1_elapsed"),
        state.get("p2_elapsed"),
        time_limit,
    )
    return Decision(
        next_difficulty=diff,
        p1_effect=p1_eff,
        p2_effect=p2_eff,
        rationale="휴리스틱(점수×제출시간) 기반 결정",
    )


# ---------------------------------------------------------------------------
# LLM 경로
# ---------------------------------------------------------------------------
DIRECTOR_SYSTEM = (
    "당신은 협동 보스 레이드의 게임 디렉터입니다. 두 참가자가 같은 문제에 프롬프트를 "
    "제출했고, 각자의 점수(0~1)와 제출에 걸린 시간이 주어집니다. 참가자의 프롬프트 "
    "내용·점수·제출 속도를 함께 보고, 다음 라운드의 난이도와 참가자별 버프/디버프를 "
    "정하세요. 잘하고 빠른 참가자는 보상(버프), 못하거나 서두른 참가자는 패널티(디버프)를 "
    "주는 것이 기본이며, 프롬프트의 강점·약점을 근거로 가장 적절한 효과를 고르세요. "
    "반드시 아래 형식의 JSON 한 개만 출력하세요. 다른 설명은 출력하지 마세요.\n"
    '{"difficulty":"Low|Mid|High","p1_effect_id":"<id>","p2_effect_id":"<id>",'
    '"rationale":"<한 줄 근거>"}'
)


def _catalog_brief() -> str:
    lines = ["[버프]"]
    for eid in BUFF_IDS:
        lines.append(f"  {eid}: {ALL_EFFECTS[eid].label}")
    lines.append("[디버프]")
    for eid in DEBUFF_IDS:
        lines.append(f"  {eid}: {ALL_EFFECTS[eid].label}")
    lines.append(f"[중립]\n  {NEUTRAL.id}: {NEUTRAL.label}")
    return "\n".join(lines)


def _build_user_message(state: BossRaidState) -> str:
    time_limit = state.get("time_limit") or 0
    def fmt(slot: str) -> str:
        elapsed = state.get(f"{slot}_elapsed")
        elapsed_s = f"{elapsed:.1f}s" if elapsed is not None else "미상"
        prompt = state.get(f"{slot}_prompt", "") or "(빈 프롬프트)"
        return (
            f"- {slot.upper()}: 점수={state.get(f'{slot}_score', 0.0):.3f}, "
            f"제출시간={elapsed_s}/{time_limit:.0f}s\n"
            f"  프롬프트: {prompt}"
        )
    return (
        f"현재 난이도: {state.get('current_difficulty', 'Mid')}\n"
        f"팀 라운드 점수: {state.get('round_score', 0.0):.3f}\n\n"
        f"{fmt('p1')}\n{fmt('p2')}\n\n"
        f"고를 수 있는 효과 목록:\n{_catalog_brief()}\n\n"
        "위를 근거로 다음 라운드 난이도와 P1/P2 효과를 JSON 으로 정하세요."
    )


def _extract_json(text: str) -> dict | None:
    """모델 응답에서 첫 JSON 객체를 추출/파싱한다(실패 시 None)."""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _decision_from_json(data: dict, fallback: Decision) -> Decision:
    """LLM JSON 을 Decision 으로 검증·변환. 누락/무효 필드는 폴백 값을 쓴다."""
    diff = data.get("difficulty")
    next_diff = diff if diff in VALID_DIFFICULTIES else fallback.next_difficulty

    def pick(slot_id: str, fb: Effect) -> Effect:
        eid = data.get(slot_id)
        return ALL_EFFECTS[eid] if eid in ALL_EFFECTS else fb

    return Decision(
        next_difficulty=next_diff,
        p1_effect=pick("p1_effect_id", fallback.p1_effect),
        p2_effect=pick("p2_effect_id", fallback.p2_effect),
        rationale=str(data.get("rationale", ""))[:200] or fallback.rationale,
    )


async def decide_next(
    client,
    model: str,
    state: BossRaidState,
    *,
    max_retries: int = 2,
) -> Decision:
    """다음 라운드 난이도/효과를 결정한다(LLM 우선, 실패 시 휴리스틱).

    MockAIClient 는 추론을 못 하므로 휴리스틱으로 직행한다. 실제 모델은 호출 후
    JSON 을 파싱하되, 실패하면 휴리스틱 결과로 자연 폴백한다.
    """
    fallback = heuristic_decision(state)
    if client is None or isinstance(client, MockAIClient):
        return fallback
    try:
        raw = await ai._call_with_retry(
            client, model, DIRECTOR_SYSTEM, _build_user_message(state), max_retries
        )
    except AICallError:
        return fallback
    data = _extract_json(raw)
    if data is None:
        return fallback
    return _decision_from_json(data, fallback)
