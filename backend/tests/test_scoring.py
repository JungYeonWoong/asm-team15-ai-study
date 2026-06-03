"""채점 수식 단위 테스트.

Score = 0.9 × (정답 수 / N) + 0.1 × √(1 - (L / 1200)²)
"""

from __future__ import annotations

import math

from app.arena.scoring import compute_score


def test_perfect_short_prompt():
    # 4/4 정답, 길이 0 → 0.9*1 + 0.1*1 = 1.0
    assert compute_score(4, 4, 0) == 1.0


def test_zero_correct_max_length():
    # 0 정답, L=1200 → 0.9*0 + 0.1*sqrt(0) = 0.0
    assert compute_score(0, 4, 1200) == 0.0


def test_formula_matches_manual():
    correct, total, length = 3, 4, 600
    accuracy = correct / total
    bonus = math.sqrt(1 - (length / 1200) ** 2)
    expected = round(0.9 * accuracy + 0.1 * bonus, 4)
    assert compute_score(correct, total, length) == expected


def test_over_max_length_clamps_to_zero_bonus():
    # L > max → 길이 보정항 0 으로 클램프, 음수 sqrt 방지
    assert compute_score(4, 4, 5000) == round(0.9, 4)


def test_score_within_bounds():
    for correct in range(0, 5):
        for length in (0, 300, 1200):
            s = compute_score(correct, 4, length)
            assert 0.0 <= s <= 1.0
