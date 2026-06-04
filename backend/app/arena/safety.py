"""프롬프트 안전성 검증.

기획서 §4 "악의적 입력 및 규칙 위반" 의 MVP 수준 필터:
- 금칙어 (욕설/혐오 표현) 단순 부분 일치 검사 (대소문자 무시)
- 빈 문자열 / 공백만 입력 거부
- 명백한 프롬프트 인젝션 패턴 (예: "ignore previous instructions") 거부

위반 시 :func:`validate_prompt` 는 ``(False, reason)`` 을 반환한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

# 기본 금칙어 — 운영환경에서는 ARENA_BANNED_WORDS 환경 변수로 확장.
DEFAULT_BANNED_WORDS: tuple[str, ...] = (
    "fuck", "shit", "bitch", "asshole",
    "씨발", "개새끼", "병신", "지랄",
)

# 프롬프트 인젝션/시스템 우회 시도 패턴 (소문자로 정규화 후 부분 일치).
INJECTION_PATTERNS: tuple[str, ...] = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard above",
    "system prompt:",
    "정답을 알려",
    "정답이 무엇",
    "테스트 입력값",
)


@dataclass(frozen=True)
class SafetyResult:
    ok: bool
    reason: Optional[str] = None


def _parse_extra(banned: str) -> list[str]:
    return [w.strip().lower() for w in banned.split(",") if w.strip()]


def _compile_pattern(needles: Iterable[str]) -> "re.Pattern[str]":
    parts = [re.escape(w) for w in needles if w]
    if not parts:
        return re.compile(r'(?!x)x')  # never matches
    return re.compile('|'.join(parts))


class PromptSafety:
    """금칙어/주입 패턴 검사기.

    환경 변수로 확장된 금칙어 목록을 ``extra_banned`` 로 받는다.
    """

    def __init__(self, extra_banned: str = "") -> None:
        self.banned_words: tuple[str, ...] = (
            tuple(w.lower() for w in DEFAULT_BANNED_WORDS) + tuple(_parse_extra(extra_banned))
        )
        self._banned_re = _compile_pattern(self.banned_words)
        self._injection_re = _compile_pattern(INJECTION_PATTERNS)

    def validate(self, text: str) -> SafetyResult:
        if text is None or not text.strip():
            return SafetyResult(False, "빈 프롬프트는 제출할 수 없습니다.")
        lowered = text.lower()
        m = self._banned_re.search(lowered)
        if m:
            return SafetyResult(False, f"금칙어가 포함되어 있습니다: '{m.group()}'")
        m = self._injection_re.search(lowered)
        if m:
            return SafetyResult(False, f"허용되지 않는 패턴이 포함되어 있습니다: '{m.group()}'")
        return SafetyResult(True, None)


def _first_hit(haystack_lower: str, needles: Iterable[str]) -> Optional[str]:
    for needle in needles:
        if needle and needle in haystack_lower:
            return needle
    return None


# 기본 인스턴스 (테스트/직접 호출 편의). 운영에서는 GameServer 가 주입한 것을 사용.
default_safety = PromptSafety()


def validate_prompt(text: str) -> SafetyResult:
    """기본 검사기. 환경 변수 확장 금칙어를 적용하려면 :class:`PromptSafety` 직접 사용."""
    return default_safety.validate(text)
