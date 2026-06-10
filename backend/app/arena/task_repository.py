"""DB에서 문제 풀을 읽어 도메인 Task 로 변환하는 레포지토리.

- load(db) : 앱 시작 시 한 번 호출 → problems + test_cases 를 메모리에 캐싱
- pick(rng) : 캐시에서 랜덤 선택 (DB 미연결 시 하드코딩 풀로 fallback)
- list_public() : GET /api/tasks 응답용 (정답 제외)
"""

from __future__ import annotations

import os
import random

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import list_problems
from app.arena.domain import Task, TestCase
from app.arena.tasks import TASK_POOL, pick_task

DEFAULT_MODEL = os.getenv("ARENA_DEFAULT_MODEL", "solar-pro3")


class TaskRepository:
    def __init__(self) -> None:
        self._pool: tuple[Task, ...] = ()

    async def load(self, db: AsyncSession) -> None:
        """DB의 problems 를 전부 읽어 Task 튜플로 캐싱."""
        problems = await list_problems(db)
        tasks = []
        for p in problems:
            test_cases = tuple(
                TestCase(input=tc.input_value, expected=tc.expected_answer)
                for tc in p.test_cases
            )
            if not test_cases:
                continue
            tasks.append(
                Task(
                    id=str(p.problem_id),
                    description=p.description,
                    model=DEFAULT_MODEL,
                    test_cases=test_cases,
                    difficulty=getattr(p, "difficulty", None) or "Mid",
                )
            )
        self._pool = tuple(tasks)

    def pick(
        self, rng: random.Random | None = None, difficulty: str | None = None
    ) -> Task:
        """풀에서 과제 선택. ``difficulty`` 지정 시 해당 난이도 우선.

        DB 미로드 시 하드코딩 풀로 fallback 한다.
        """
        if self._pool:
            chooser = rng or random
            pool = self._pool
            if difficulty is not None:
                filtered = tuple(t for t in self._pool if t.difficulty == difficulty)
                if filtered:
                    pool = filtered
            return chooser.choice(pool)
        return pick_task(rng, difficulty=difficulty)

    def list_public(self) -> list[dict]:
        """GET /api/tasks 응답용 — 정답 제외."""
        pool = self._pool if self._pool else TASK_POOL
        return [
            {
                "id": t.id,
                "description": t.description,
                "model": t.model,
                "total_count": t.total_count,
            }
            for t in pool
        ]

    @property
    def loaded(self) -> bool:
        return bool(self._pool)
