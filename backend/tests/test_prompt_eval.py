"""LLM 프롬프트 평가(evaluate_prompt) 단위 테스트.

채점 출력을 LLM 에게 보여준 뒤 프롬프트 총평을 받는 부가 기능을 검증한다.
실제 모델 대신 CallableAIClient 로 입출력을 통제한다.
"""

from __future__ import annotations

from app.arena.ai_client import (
    PROMPT_EVAL_SYSTEM,
    CallableAIClient,
    build_eval_input,
    evaluate_prompt,
)
from app.arena.domain import TestCase

TEST_CASES = (
    TestCase(input="a", expected="A"),
    TestCase(input="b", expected="B"),
)


def test_build_eval_input_contains_prompt_and_outputs():
    text = build_eval_input("내 프롬프트", TEST_CASES, ["A", "x"])
    assert "내 프롬프트" in text
    # 케이스별 입력/기대/실제가 모두 들어간다
    assert "'a'" in text and "'A'" in text
    assert "정답" in text  # a→A 는 정답
    assert "오답" in text  # b→x 는 오답


async def test_evaluate_prompt_sees_outputs_and_returns_feedback():
    seen: dict[str, str] = {}

    def fn(model: str, prompt: str, test_input: str) -> str:
        seen["system"] = prompt
        seen["user"] = test_input
        return "  좋은 프롬프트입니다.  "

    client = CallableAIClient(fn)
    result = await evaluate_prompt(
        client, "M", "내 프롬프트", TEST_CASES, ["A", "B"]
    )

    # 평가 LLM 은 평가 전용 system 프롬프트를 받는다
    assert seen["system"] == PROMPT_EVAL_SYSTEM
    # 실제 출력(A, B)을 본 상태로 평가한다
    assert "'A'" in seen["user"] and "'B'" in seen["user"]
    # 반환값은 정규화(trim)된다
    assert result == "좋은 프롬프트입니다."


async def test_evaluate_prompt_empty_prompt_skips_call():
    called = False

    def fn(model: str, prompt: str, test_input: str) -> str:
        nonlocal called
        called = True
        return "x"

    client = CallableAIClient(fn)
    result = await evaluate_prompt(client, "M", "   ", TEST_CASES, ["A", "B"])
    assert result == ""
    assert called is False  # 빈 프롬프트는 모델을 호출하지 않는다


async def test_evaluate_prompt_swallows_failure():
    def boom(model: str, prompt: str, test_input: str) -> str:
        raise RuntimeError("model down")

    client = CallableAIClient(boom)
    # 평가 실패는 라운드를 깨지 않고 빈 문자열로 흡수된다
    result = await evaluate_prompt(
        client, "M", "p", TEST_CASES, ["A", "B"], max_retries=1
    )
    assert result == ""
