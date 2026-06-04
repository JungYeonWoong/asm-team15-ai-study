"""채점 수식.

Score = 0.9 × (정답 수 / N) + 0.1 × √(1 - (L / 1200)²)

- 정답 수 / N : 테스트 케이스 정답률 (정확도)
- L : 프롬프트 글자 수, 1200 = 최대 글자 수
- 길이 보정항은 짧은 프롬프트일수록 가산점을 준다.
"""

from __future__ import annotations

import math


def compute_score(
    correct_count: int,
    total_count: int,
    prompt_length: int,
    max_length: int = 1200,
) -> float:
    """명세의 채점 수식을 그대로 계산해 0.0~1.0 점수를 반환한다."""
    accuracy = (correct_count / total_count) if total_count > 0 else 0.0

    # L 이 max_length 를 넘으면 음수가 되므로 0 으로 클램프한다.
    ratio = min(prompt_length / max_length, 1.0) if max_length > 0 else 1.0
    length_bonus = math.sqrt(max(0.0, 1.0 - ratio**2))

    score = 0.9 * accuracy + 0.1 * length_bonus
    return round(score, 4)
