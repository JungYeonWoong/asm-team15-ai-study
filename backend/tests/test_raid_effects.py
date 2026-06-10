"""버프/디버프 효과 카탈로그 단위 테스트."""

from __future__ import annotations

from app.raid.effects import (
    ALL_EFFECTS,
    BUFF_IDS,
    DEBUFF_IDS,
    NEUTRAL,
    effect_from_dict,
    effect_from_id,
    effect_to_dict,
)


def test_catalog_kinds_consistent():
    for eid in BUFF_IDS:
        assert ALL_EFFECTS[eid].kind == "buff"
    for eid in DEBUFF_IDS:
        assert ALL_EFFECTS[eid].kind == "debuff"
    assert NEUTRAL.kind == "neutral"
    # 카탈로그는 다양한 효과를 충분히(>=8) 제공한다.
    assert len(BUFF_IDS) >= 4 and len(DEBUFF_IDS) >= 4


def test_buffs_are_favorable_debuffs_are_harsh():
    # 버프는 적어도 한 축에서 유리(>1 또는 힌트 공개), 디버프는 한 축에서 불리(<1).
    for eid in BUFF_IDS:
        e = ALL_EFFECTS[eid]
        favorable = (
            e.char_limit_factor > 1.0
            or e.time_factor > 1.0
            or e.damage_multiplier > 1.0
            or e.score_multiplier > 1.0
            or e.reveal_hint
        )
        assert favorable, f"{eid} 버프가 유리하지 않음"
    for eid in DEBUFF_IDS:
        e = ALL_EFFECTS[eid]
        harsh = (
            e.char_limit_factor < 1.0
            or e.time_factor < 1.0
            or e.damage_multiplier < 1.0
            or e.score_multiplier < 1.0
        )
        assert harsh, f"{eid} 디버프가 불리하지 않음"


def test_effect_from_id_unknown_returns_neutral():
    assert effect_from_id("no_such_effect") is NEUTRAL
    assert effect_from_id(None) is NEUTRAL
    assert effect_from_id("power_strike").id == "power_strike"


def test_serialization_roundtrip():
    e = ALL_EFFECTS["char_squeeze"]
    data = effect_to_dict(e)
    assert data["id"] == "char_squeeze"
    assert data["char_limit_factor"] == 0.5
    restored = effect_from_dict(data)
    assert restored.id == e.id
    assert restored.char_limit_factor == e.char_limit_factor


def test_from_dict_empty_returns_neutral():
    assert effect_from_dict(None) is NEUTRAL
    assert effect_from_dict({}) is NEUTRAL
