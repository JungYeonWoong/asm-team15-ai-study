"""사전 정의된 과제 풀.

ROUND_START 시 이 풀에서 과제를 하나 배정한다. 각 과제는 채점용
테스트 케이스(N개)를 포함한다. expected 는 AI 출력과 이진 비교된다.
"""

from __future__ import annotations

import random

from .domain import Task, TestCase

DEFAULT_MODEL = "Upstage-Solar-Pro"


TASK_POOL: tuple[Task, ...] = (
    Task(
        id="translate-positive",
        description="다음 문장을 긍정적인 톤으로 번역하시오.",
        model=DEFAULT_MODEL,
        test_cases=(
            TestCase(input="It is raining again.", expected="비가 다시 내리네요!"),
            TestCase(input="The meeting was long.", expected="회의가 알찼어요!"),
            TestCase(input="I failed the test.", expected="다음엔 더 잘할 수 있어요!"),
            TestCase(input="Traffic is terrible.", expected="조금 여유롭게 가요!"),
            TestCase(input="The food was cold.", expected="시원하게 즐겼어요!"),
        ),
    ),
    Task(
        id="extract-number",
        description="문장에서 숫자만 추출해 정수로 출력하시오.",
        model=DEFAULT_MODEL,
        test_cases=(
            TestCase(input="사과 3개를 샀다.", expected="3"),
            TestCase(input="기온은 영하 5도이다.", expected="5"),
            TestCase(input="총 42명이 참석했다.", expected="42"),
            TestCase(input="가격은 1500원이다.", expected="1500"),
            TestCase(input="0개 남았다.", expected="0"),
        ),
    ),
    Task(
        id="classify-sentiment",
        description="문장의 감정을 POSITIVE 또는 NEGATIVE 로 분류하시오.",
        model=DEFAULT_MODEL,
        test_cases=(
            TestCase(input="이 영화 정말 최고였어!", expected="POSITIVE"),
            TestCase(input="시간 낭비였다.", expected="NEGATIVE"),
            TestCase(input="너무 행복한 하루.", expected="POSITIVE"),
            TestCase(input="다시는 안 갈 것이다.", expected="NEGATIVE"),
            TestCase(input="강력 추천합니다.", expected="POSITIVE"),
        ),
    ),
)


def pick_task(rng: random.Random | None = None) -> Task:
    """과제 풀에서 무작위로 하나를 배정한다."""
    chooser = rng or random
    return chooser.choice(TASK_POOL)
