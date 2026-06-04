"""사전 정의된 과제 풀.

ROUND_START 시 이 풀에서 과제를 하나 배정한다. 각 과제는 채점용
테스트 케이스(N개)를 포함한다. expected 는 AI 출력과 이진 비교된다.

각 과제는 5개 TC 를 가지며, GET /api/tasks 로는 정답을 제외한
메타데이터(id/description/model/total_count)만 노출한다.
"""

from __future__ import annotations

import random

from .domain import Task, TestCase

import os

# Upstage 백엔드 사용 시 실제로 호출 가능한 모델명. 환경 변수로 오버라이드.
DEFAULT_MODEL = os.getenv("ARENA_DEFAULT_MODEL", "solar-pro3")


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
    Task(
        id="to-uppercase",
        description="입력 영문을 대문자로만 출력하시오. 다른 문자는 출력하지 마시오.",
        model=DEFAULT_MODEL,
        test_cases=(
            TestCase(input="hello", expected="HELLO"),
            TestCase(input="prompt arena", expected="PROMPT ARENA"),
            TestCase(input="upstage", expected="UPSTAGE"),
            TestCase(input="ai is fun", expected="AI IS FUN"),
            TestCase(input="solar pro", expected="SOLAR PRO"),
        ),
    ),
    Task(
        id="count-vowels",
        description="영어 문장에 포함된 모음(a,e,i,o,u, 대소문자 무관)의 개수를 정수로 출력하시오.",
        model=DEFAULT_MODEL,
        test_cases=(
            TestCase(input="hello", expected="2"),
            TestCase(input="prompt", expected="1"),
            TestCase(input="arena", expected="3"),
            TestCase(input="education", expected="5"),
            TestCase(input="sky", expected="0"),
        ),
    ),
    Task(
        id="json-keys",
        description=(
            "주어진 JSON 객체의 최상위 키들을 알파벳순으로 정렬해 "
            "쉼표로 이어 출력하시오. 공백 없이."
        ),
        model=DEFAULT_MODEL,
        test_cases=(
            TestCase(input='{"name":"a","age":1}', expected="age,name"),
            TestCase(input='{"b":1,"a":2,"c":3}', expected="a,b,c"),
            TestCase(input='{"id":1}', expected="id"),
            TestCase(input='{"zoo":"x","apple":"y"}', expected="apple,zoo"),
            TestCase(input='{"k2":2,"k1":1,"k3":3}', expected="k1,k2,k3"),
        ),
    ),
)


def pick_task(rng: random.Random | None = None) -> Task:
    """과제 풀에서 무작위로 하나를 배정한다."""
    chooser = rng or random
    return chooser.choice(TASK_POOL)


def list_tasks_public() -> list[dict]:
    """GET /api/tasks 응답용 — 정답 데이터는 제외."""
    return [
        {
            "id": t.id,
            "description": t.description,
            "model": t.model,
            "total_count": t.total_count,
        }
        for t in TASK_POOL
    ]
