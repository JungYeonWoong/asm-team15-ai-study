"""TaskRepository 단위 테스트."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import Base, init_engine, get_session_factory
from app.db import repository as repo
from app.arena.task_repository import TaskRepository
from app.arena.tasks import TASK_POOL


@pytest_asyncio.fixture(scope="function")
async def db() -> AsyncSession:
    engine = init_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with get_session_factory()() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _seed(db, n_problems=3, n_cases=5):
    problems = []
    for i in range(n_problems):
        p = await repo.create_problem(
            db,
            title=f"Problem {i}",
            description=f"Description {i}",
            problem_type="classification",
        )
        for j in range(n_cases):
            await repo.add_test_case(
                db,
                problem_id=p.problem_id,
                input_value=f"input_{i}_{j}",
                expected_answer=f"output_{i}_{j}",
            )
        problems.append(p)
    return problems


@pytest.mark.asyncio
async def test_load_from_db(db):
    await _seed(db, n_problems=3, n_cases=5)
    task_repo = TaskRepository()
    await task_repo.load(db)

    assert task_repo.loaded
    assert len(task_repo._pool) == 3
    for task in task_repo._pool:
        assert len(task.test_cases) == 5


@pytest.mark.asyncio
async def test_pick_returns_task(db):
    await _seed(db, n_problems=4, n_cases=3)
    task_repo = TaskRepository()
    await task_repo.load(db)

    task = task_repo.pick()
    assert task.id is not None
    assert task.description != ""
    assert len(task.test_cases) == 3


@pytest.mark.asyncio
async def test_pick_fallback_when_empty(db):
    task_repo = TaskRepository()
    # load 안 하면 하드코딩 풀에서 fallback
    assert not task_repo.loaded
    task = task_repo.pick()
    assert task in TASK_POOL


@pytest.mark.asyncio
async def test_list_public_uses_db(db):
    await _seed(db, n_problems=2, n_cases=4)
    task_repo = TaskRepository()
    await task_repo.load(db)

    result = task_repo.list_public()
    assert len(result) == 2
    for item in result:
        assert "id" in item
        assert "description" in item
        assert "model" in item
        assert item["total_count"] == 4
        assert "test_cases" not in item  # 정답 비공개


@pytest.mark.asyncio
async def test_list_public_fallback_when_not_loaded(db):
    task_repo = TaskRepository()
    result = task_repo.list_public()
    assert len(result) == len(TASK_POOL)


@pytest.mark.asyncio
async def test_skips_problem_without_test_cases(db):
    # 테스트 케이스 없는 문제는 풀에서 제외
    await repo.create_problem(db, title="Empty", description="no cases", problem_type="classification")
    await _seed(db, n_problems=2, n_cases=3)

    task_repo = TaskRepository()
    await task_repo.load(db)
    assert len(task_repo._pool) == 2  # Empty 문제 제외


@pytest.mark.asyncio
async def test_task_id_matches_problem_id(db):
    problems = await _seed(db, n_problems=2, n_cases=2)
    task_repo = TaskRepository()
    await task_repo.load(db)

    ids = {t.id for t in task_repo._pool}
    expected_ids = {str(p.problem_id) for p in problems}
    assert ids == expected_ids


@pytest.mark.asyncio
async def test_reload_replaces_pool(db):
    await _seed(db, n_problems=2, n_cases=2)
    task_repo = TaskRepository()
    await task_repo.load(db)
    assert len(task_repo._pool) == 2

    await _seed(db, n_problems=3, n_cases=2)
    await task_repo.load(db)
    assert len(task_repo._pool) == 5  # 2 + 3
