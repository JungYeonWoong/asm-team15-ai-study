"""실제 Upstage API로 채점 전체 흐름을 검증하는 통합 테스트.

RUN_INTEGRATION=1 환경 변수가 없으면 skip.
"""

from __future__ import annotations

import os

import pytest

from app.arena.ai_client import UpstageAIClient, grade
from app.arena.domain import TestCase
from app.arena.scoring import compute_score

pytestmark = pytest.mark.integration

API_KEY = os.getenv("UPSTAGE_API_KEY", "")
BASE_URL = os.getenv("UPSTAGE_BASE_URL", "https://api.upstage.ai/v1/solar")
MODEL = os.getenv("ARENA_DEFAULT_MODEL", "solar-pro3")


def _client():
    return UpstageAIClient(API_KEY, BASE_URL)


def _skip_if_not_enabled():
    if not os.getenv("RUN_INTEGRATION"):
        pytest.skip("set RUN_INTEGRATION=1 to enable")
    if not API_KEY:
        pytest.skip("UPSTAGE_API_KEY not set")


# ---------------------------------------------------------------------------
# 단일 케이스
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_single_test_case_correct():
    """명확한 프롬프트로 정답을 맞히는지 확인."""
    _skip_if_not_enabled()
    client = _client()
    output = await client.run(
        model=MODEL,
        prompt="숫자만 대문자로 바꿔서 출력하세요. 다른 것은 출력하지 마세요.",
        test_input="hello",
    )
    assert isinstance(output, str)
    assert output.strip()


@pytest.mark.asyncio
async def test_uppercase_task_grade():
    """UPPERCASE 과제: 좋은 프롬프트는 높은 점수, 나쁜 프롬프트는 낮은 점수."""
    _skip_if_not_enabled()
    client = _client()

    test_cases = (
        TestCase(input="hello", expected="HELLO"),
        TestCase(input="prompt arena", expected="PROMPT ARENA"),
        TestCase(input="upstage", expected="UPSTAGE"),
    )

    good_prompt = (
        "Convert the input text to uppercase. "
        "Output ONLY the uppercase result with no extra text or punctuation."
    )
    bad_prompt = "just say something"

    correct_good, total, _ = await grade(client, MODEL, good_prompt, test_cases)
    correct_bad, _, _ = await grade(client, MODEL, bad_prompt, test_cases)

    score_good = compute_score(correct_good, total, len(good_prompt))
    score_bad = compute_score(correct_bad, total, len(bad_prompt))

    assert correct_good > correct_bad, (
        f"좋은 프롬프트({correct_good}/{total})가 나쁜 프롬프트({correct_bad}/{total})보다 높아야 함"
    )
    assert score_good > score_bad


# ---------------------------------------------------------------------------
# 분류 과제 (examples 형식)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_classification_grade():
    """감정 분류 과제: AI가 POSITIVE/NEGATIVE 를 정확히 출력하는지."""
    _skip_if_not_enabled()
    client = _client()

    test_cases = (
        TestCase(input="이 영화 정말 최고였어!", expected="POSITIVE"),
        TestCase(input="시간 낭비였다.", expected="NEGATIVE"),
        TestCase(input="너무 행복한 하루.", expected="POSITIVE"),
    )

    prompt = (
        "Classify the sentiment of the input sentence as POSITIVE or NEGATIVE. "
        "Output ONLY one word: POSITIVE or NEGATIVE."
    )

    correct, total, sample = await grade(client, MODEL, prompt, test_cases)
    score = compute_score(correct, total, len(prompt))

    assert total == 3
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0
    # 좋은 프롬프트면 최소 2/3 이상 맞혀야 함
    assert correct >= 2, f"정답 {correct}/{total}, 응답 예시: {sample!r}"


# ---------------------------------------------------------------------------
# 추출 과제 (examples 형식)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extraction_grade():
    """숫자 추출 과제: AI가 정확한 값만 출력하는지."""
    _skip_if_not_enabled()
    client = _client()

    test_cases = (
        TestCase(input="사과 3개를 샀다.", expected="3"),
        TestCase(input="총 42명이 참석했다.", expected="42"),
        TestCase(input="가격은 1500원이다.", expected="1500"),
    )

    prompt = (
        "Extract the single integer number from the Korean sentence. "
        "Output ONLY the number with no other text."
    )

    correct, total, sample = await grade(client, MODEL, prompt, test_cases)
    score = compute_score(correct, total, len(prompt))

    assert total == 3
    assert 0.0 <= score <= 1.0
    assert correct >= 2, f"정답 {correct}/{total}, 응답 예시: {sample!r}"


# ---------------------------------------------------------------------------
# 점수 계산 검증
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_reflects_accuracy():
    """정답률이 높을수록 점수가 높은지 확인."""
    _skip_if_not_enabled()
    client = _client()

    test_cases = (
        TestCase(input="hello", expected="HELLO"),
        TestCase(input="world", expected="WORLD"),
        TestCase(input="upstage", expected="UPSTAGE"),
        TestCase(input="solar", expected="SOLAR"),
        TestCase(input="arena", expected="ARENA"),
    )

    prompt = (
        "Output the input text in uppercase only. No extra characters."
    )

    correct, total, _ = await grade(client, MODEL, prompt, test_cases)
    score = compute_score(correct, total, len(prompt))

    assert total == 5
    assert 0.0 <= score <= 1.0
    print(f"\n정답: {correct}/{total}, 점수: {score:.4f}")
