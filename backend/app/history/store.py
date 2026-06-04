"""라운드 결과 기록 저장소 (메모리).

각 user_id 마다 deque (maxlen=50) 로 최근 결과를 보관한다.
서버 재시작 시 휘발된다 (v1.2 에서 영속화 예정).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Optional, Protocol


@dataclass(frozen=True)
class RoundRecord:
    user_id: str
    room_code: str
    task_id: str
    result: str            # WIN | LOSE | DRAW
    winner_id: Optional[str]
    my_score: float
    opponent_score: float
    correct_count: int
    total_count: int
    prompt_length: int
    timestamp: float = field(default_factory=time.time)


class HistoryStore(Protocol):
    def record(self, **kwargs) -> RoundRecord: ...
    def list_for(self, user_id: str, limit: int = 20) -> list[RoundRecord]: ...
    def clear(self) -> None: ...


class InMemoryHistoryStore:
    """user_id → 최근 결과 deque(maxlen=50)."""

    def __init__(self, maxlen: int = 50) -> None:
        self._records: dict[str, deque[RoundRecord]] = {}
        self._maxlen = maxlen

    def record(
        self,
        *,
        user_id: str,
        room_code: str,
        task_id: str,
        result: str,
        winner_id: Optional[str],
        my_score: float,
        opponent_score: float,
        correct_count: int,
        total_count: int,
        prompt_length: int,
    ) -> RoundRecord:
        rec = RoundRecord(
            user_id=user_id,
            room_code=room_code,
            task_id=task_id,
            result=result,
            winner_id=winner_id,
            my_score=my_score,
            opponent_score=opponent_score,
            correct_count=correct_count,
            total_count=total_count,
            prompt_length=prompt_length,
        )
        bucket = self._records.setdefault(
            user_id, deque(maxlen=self._maxlen)
        )
        bucket.append(rec)
        return rec

    def list_for(self, user_id: str, limit: int = 20) -> list[RoundRecord]:
        bucket = self._records.get(user_id)
        if not bucket:
            return []
        # 최신순 (deque 의 마지막이 가장 최근)
        records = list(bucket)
        records.reverse()
        return records[: max(0, limit)]

    def clear(self) -> None:
        self._records.clear()


def record_to_dict(rec: RoundRecord) -> dict:
    return asdict(rec)
