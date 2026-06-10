"""보스 레이드 버프/디버프 효과 카탈로그.

디렉터(:mod:`app.raid.director`)가 제출 점수·시간·프롬프트를 보고 **다음 라운드**에
부여할 효과를 이 카탈로그에서 고른다. 각 효과는 라운드 메커니즘에 실제로 작용하는
배율/플래그를 담는다.

  - char_limit_factor : 다음 라운드 글자수 제한 배수 (>1 완화, <1 강화)
  - time_factor       : 다음 라운드 제한시간 배수
  - damage_multiplier : 다음 라운드 보스 데미지 배수
  - score_multiplier  : 다음 라운드 점수 배수 (0~1 로 clamp 되어 적용)
  - reveal_hint       : 다음 라운드 예시 힌트 공개 여부

활성 효과(active effect)는 서버가 ROUND_START 시 적용하고, scoring 노드가
배율을 반영한다. 라운드 1 의 기본값은 :data:`NEUTRAL`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Effect:
    """한 플레이어에게 한 라운드 동안 부여되는 상태효과."""

    id: str
    kind: str  # "buff" | "debuff" | "neutral"
    label: str  # 이모지 + 한국어 표시 문자열 (WS status_effect)
    char_limit_factor: float = 1.0
    time_factor: float = 1.0
    damage_multiplier: float = 1.0
    score_multiplier: float = 1.0
    reveal_hint: bool = False


# ---------------------------------------------------------------------------
# 카탈로그
# ---------------------------------------------------------------------------
NEUTRAL = Effect(
    id="steady",
    kind="neutral",
    label="⚪ 평온 · 특수 효과 없음",
)

BUFFS: tuple[Effect, ...] = (
    Effect(
        id="hint_reveal",
        kind="buff",
        label="🟢 버프 · 다음 문제 예시 힌트 공개",
        reveal_hint=True,
    ),
    Effect(
        id="free_length",
        kind="buff",
        label="🟢 버프 · 글자수 제한 2배 완화",
        char_limit_factor=2.0,
    ),
    Effect(
        id="time_bonus",
        kind="buff",
        label="🟢 버프 · 제한시간 1.5배",
        time_factor=1.5,
    ),
    Effect(
        id="power_strike",
        kind="buff",
        label="🟢 버프 · 다음 공격 데미지 1.5배",
        damage_multiplier=1.5,
    ),
    Effect(
        id="score_surge",
        kind="buff",
        label="🟢 버프 · 다음 점수 1.2배",
        score_multiplier=1.2,
    ),
)

DEBUFFS: tuple[Effect, ...] = (
    Effect(
        id="char_squeeze",
        kind="debuff",
        label="🔴 디버프 · 글자수 제한 절반",
        char_limit_factor=0.5,
    ),
    Effect(
        id="char_crush",
        kind="debuff",
        label="🔴 디버프 · 글자수 제한 1/4",
        char_limit_factor=0.25,
    ),
    Effect(
        id="time_pressure",
        kind="debuff",
        label="🔴 디버프 · 제한시간 0.6배",
        time_factor=0.6,
    ),
    Effect(
        id="weak_strike",
        kind="debuff",
        label="🔴 디버프 · 다음 공격 데미지 0.7배",
        damage_multiplier=0.7,
    ),
    Effect(
        id="fog",
        kind="debuff",
        label="🔴 디버프 · 다음 점수 0.9배",
        score_multiplier=0.9,
    ),
)

ALL_EFFECTS: dict[str, Effect] = {
    e.id: e for e in (NEUTRAL, *BUFFS, *DEBUFFS)
}
BUFF_IDS: tuple[str, ...] = tuple(e.id for e in BUFFS)
DEBUFF_IDS: tuple[str, ...] = tuple(e.id for e in DEBUFFS)


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def effect_from_id(effect_id: str | None) -> Effect:
    """id 로 효과를 찾는다. 미지/누락 시 :data:`NEUTRAL`."""
    if not effect_id:
        return NEUTRAL
    return ALL_EFFECTS.get(effect_id, NEUTRAL)


def effect_to_dict(effect: Effect) -> dict:
    """상태/WS 직렬화용 dict 로 변환한다."""
    return {
        "id": effect.id,
        "kind": effect.kind,
        "label": effect.label,
        "char_limit_factor": effect.char_limit_factor,
        "time_factor": effect.time_factor,
        "damage_multiplier": effect.damage_multiplier,
        "score_multiplier": effect.score_multiplier,
        "reveal_hint": effect.reveal_hint,
    }


def effect_from_dict(data: dict | None) -> Effect:
    """state 에 저장된 dict 를 Effect 로 복원한다(없으면 NEUTRAL)."""
    if not data:
        return NEUTRAL
    # id 가 카탈로그에 있으면 정본을 쓰고, 아니면 dict 값으로 구성.
    eid = data.get("id")
    if eid in ALL_EFFECTS:
        return ALL_EFFECTS[eid]
    return Effect(
        id=eid or "steady",
        kind=data.get("kind", "neutral"),
        label=data.get("label", NEUTRAL.label),
        char_limit_factor=data.get("char_limit_factor", 1.0),
        time_factor=data.get("time_factor", 1.0),
        damage_multiplier=data.get("damage_multiplier", 1.0),
        score_multiplier=data.get("score_multiplier", 1.0),
        reveal_hint=data.get("reveal_hint", False),
    )
