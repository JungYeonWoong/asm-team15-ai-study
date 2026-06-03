"""대전 도메인 모델: 과제, 테스트 케이스, 결과."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RoundResult(str, Enum):
    WIN = "WIN"
    LOSE = "LOSE"
    DRAW = "DRAW"


@dataclass(frozen=True)
class TestCase:
    """채점용 테스트 케이스. AI 출력과 expected 를 이진 비교한다."""

    input: str
    expected: str


@dataclass(frozen=True)
class Task:
    """한 라운드에서 사용되는 과제 정의."""

    id: str
    description: str  # ROUND_START 의 task 필드
    model: str        # 사용할 Base AI 모델명
    test_cases: tuple[TestCase, ...]

    @property
    def total_count(self) -> int:
        return len(self.test_cases)


@dataclass
class PlayerResult:
    """채점이 끝난 한 플레이어의 결과 데이터."""

    client_id: str
    prompt: str
    ai_response: str
    correct_count: int
    total_count: int
    prompt_length: int
    score: float

    def to_dict(self) -> dict:
        return {
            "client_id": self.client_id,
            "prompt": self.prompt,
            "ai_response": self.ai_response,
            "correct_count": self.correct_count,
            "total_count": self.total_count,
            "prompt_length": self.prompt_length,
            "score": self.score,
        }
