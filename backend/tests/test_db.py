"""DB 레이어 전체 테스트 (SQLite in-memory 사용).

pytest-asyncio + aiosqlite 로 PostgreSQL 없이 실행 가능.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import Base, init_engine, get_session_factory
from app.db.models import RoomStatus
from app.db import repository as repo


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

async def _make_user(db, *, login_id="alice", nickname="Alice", tokens=1000):
    return await repo.create_user(
        db, login_id=login_id, password_hash="hashed", nickname=nickname, current_tokens=tokens
    )


async def _make_problem(db, *, title="Test Problem", ptype="classification"):
    return await repo.create_problem(
        db, title=title, description="Test desc", problem_type=ptype
    )


async def _make_room(db, *, user1_id=None, code="ROOM01"):
    return await repo.create_room(db, room_code=code, user1_id=user1_id)


# ===========================================================================
# User CRUD
# ===========================================================================

@pytest.mark.asyncio
async def test_create_user(db):
    user = await _make_user(db)
    assert user.user_id is not None
    assert user.login_id == "alice"
    assert user.nickname == "Alice"
    assert user.current_tokens == 1000


@pytest.mark.asyncio
async def test_get_user_by_id(db):
    user = await _make_user(db)
    fetched = await repo.get_user_by_id(db, user.user_id)
    assert fetched is not None
    assert fetched.login_id == "alice"


@pytest.mark.asyncio
async def test_get_user_by_login_id(db):
    await _make_user(db)
    fetched = await repo.get_user_by_login_id(db, "alice")
    assert fetched is not None
    assert fetched.nickname == "Alice"


@pytest.mark.asyncio
async def test_get_user_by_login_id_not_found(db):
    result = await repo.get_user_by_login_id(db, "nobody")
    assert result is None


@pytest.mark.asyncio
async def test_update_user_tokens_add(db):
    user = await _make_user(db, tokens=500)
    updated = await repo.update_user_tokens(db, user.user_id, delta=100)
    assert updated.current_tokens == 600


@pytest.mark.asyncio
async def test_update_user_tokens_subtract(db):
    user = await _make_user(db, tokens=500)
    updated = await repo.update_user_tokens(db, user.user_id, delta=-200)
    assert updated.current_tokens == 300


@pytest.mark.asyncio
async def test_update_user_tokens_not_found(db):
    result = await repo.update_user_tokens(db, user_id=9999, delta=50)
    assert result is None


# ===========================================================================
# Problem CRUD
# ===========================================================================

@pytest.mark.asyncio
async def test_create_problem(db):
    problem = await _make_problem(db)
    assert problem.problem_id is not None
    assert problem.problem_type == "classification"


@pytest.mark.asyncio
async def test_get_problem_by_id(db):
    problem = await _make_problem(db, title="Q Profit", ptype="extraction")
    fetched = await repo.get_problem_by_id(db, problem.problem_id)
    assert fetched is not None
    assert fetched.title == "Q Profit"
    assert fetched.problem_type == "extraction"


@pytest.mark.asyncio
async def test_get_problem_by_id_not_found(db):
    result = await repo.get_problem_by_id(db, 9999)
    assert result is None


@pytest.mark.asyncio
async def test_list_problems(db):
    await _make_problem(db, title="P1")
    await _make_problem(db, title="P2")
    problems = await repo.list_problems(db)
    assert len(problems) == 2


@pytest.mark.asyncio
async def test_list_problems_empty(db):
    problems = await repo.list_problems(db)
    assert problems == [] or len(problems) == 0


# ===========================================================================
# ProblemTestCase CRUD
# ===========================================================================

@pytest.mark.asyncio
async def test_add_test_case(db):
    problem = await _make_problem(db)
    tc = await repo.add_test_case(
        db, problem_id=problem.problem_id, input_value="hello", expected_answer="WORLD"
    )
    assert tc.test_case_id is not None
    assert tc.input_value == "hello"
    assert tc.expected_answer == "WORLD"


@pytest.mark.asyncio
async def test_get_test_cases_for_problem(db):
    problem = await _make_problem(db)
    await repo.add_test_case(db, problem_id=problem.problem_id, input_value="a", expected_answer="A")
    await repo.add_test_case(db, problem_id=problem.problem_id, input_value="b", expected_answer="B")
    cases = await repo.get_test_cases_for_problem(db, problem.problem_id)
    assert len(cases) == 2
    inputs = {tc.input_value for tc in cases}
    assert inputs == {"a", "b"}


@pytest.mark.asyncio
async def test_get_test_cases_for_problem_empty(db):
    problem = await _make_problem(db)
    cases = await repo.get_test_cases_for_problem(db, problem.problem_id)
    assert len(cases) == 0


@pytest.mark.asyncio
async def test_problem_with_test_cases_loaded(db):
    problem = await _make_problem(db)
    await repo.add_test_case(db, problem_id=problem.problem_id, input_value="x", expected_answer="X")
    fetched = await repo.get_problem_by_id(db, problem.problem_id)
    assert len(fetched.test_cases) == 1
    assert fetched.test_cases[0].input_value == "x"


# ===========================================================================
# Room CRUD
# ===========================================================================

@pytest.mark.asyncio
async def test_create_room(db):
    user = await _make_user(db)
    room = await _make_room(db, user1_id=user.user_id)
    assert room.room_id is not None
    assert room.room_code == "ROOM01"
    assert room.status == RoomStatus.waiting
    assert room.user1_id == user.user_id
    assert room.user2_id is None


@pytest.mark.asyncio
async def test_create_room_without_user(db):
    room = await _make_room(db)
    assert room.user1_id is None
    assert room.status == RoomStatus.waiting


@pytest.mark.asyncio
async def test_get_room_by_code(db):
    await _make_room(db, code="ABC123")
    room = await repo.get_room_by_code(db, "ABC123")
    assert room is not None
    assert room.room_code == "ABC123"


@pytest.mark.asyncio
async def test_get_room_by_code_not_found(db):
    result = await repo.get_room_by_code(db, "NOPE")
    assert result is None


@pytest.mark.asyncio
async def test_update_room_status(db):
    room = await _make_room(db)
    updated = await repo.update_room_status(db, room.room_id, RoomStatus.in_progress)
    assert updated.status == RoomStatus.in_progress


@pytest.mark.asyncio
async def test_update_room_status_not_found(db):
    result = await repo.update_room_status(db, 9999, RoomStatus.completed)
    assert result is None


@pytest.mark.asyncio
async def test_join_room(db):
    user1 = await _make_user(db, login_id="u1", nickname="U1")
    user2 = await _make_user(db, login_id="u2", nickname="U2")
    room = await repo.create_room(db, room_code="JOIN01", user1_id=user1.user_id)
    updated = await repo.join_room(db, room.room_id, user2_id=user2.user_id)
    assert updated.user2_id == user2.user_id
    assert updated.status == RoomStatus.in_progress


@pytest.mark.asyncio
async def test_join_room_not_found(db):
    result = await repo.join_room(db, room_id=9999, user2_id=1)
    assert result is None


# ===========================================================================
# MatchRecord CRUD
# ===========================================================================

@pytest.mark.asyncio
async def test_create_match_record(db):
    user1 = await _make_user(db, login_id="u1", nickname="U1")
    user2 = await _make_user(db, login_id="u2", nickname="U2")
    problem = await _make_problem(db)
    room = await _make_room(db, user1_id=user1.user_id)

    record = await repo.create_match_record(
        db,
        room_id=room.room_id,
        problem_id=problem.problem_id,
        winner_id=user1.user_id,
        loser_id=user2.user_id,
    )
    assert record.record_id is not None
    assert record.winner_id == user1.user_id
    assert record.loser_id == user2.user_id


@pytest.mark.asyncio
async def test_create_match_record_draw(db):
    room = await _make_room(db)
    record = await repo.create_match_record(
        db, room_id=room.room_id, winner_id=None, loser_id=None
    )
    assert record.winner_id is None
    assert record.loser_id is None


@pytest.mark.asyncio
async def test_get_match_records_by_room(db):
    room = await _make_room(db)
    await repo.create_match_record(db, room_id=room.room_id)
    await repo.create_match_record(db, room_id=room.room_id)
    records = await repo.get_match_records_by_room(db, room.room_id)
    assert len(records) == 2


@pytest.mark.asyncio
async def test_get_match_records_by_user(db):
    user1 = await _make_user(db, login_id="w1", nickname="W1")
    user2 = await _make_user(db, login_id="l1", nickname="L1")
    room = await _make_room(db, user1_id=user1.user_id)
    await repo.create_match_record(
        db, room_id=room.room_id, winner_id=user1.user_id, loser_id=user2.user_id
    )
    records_w = await repo.get_match_records_by_user(db, user1.user_id)
    records_l = await repo.get_match_records_by_user(db, user2.user_id)
    assert len(records_w) == 1
    assert len(records_l) == 1


@pytest.mark.asyncio
async def test_get_match_records_by_room_empty(db):
    room = await _make_room(db)
    records = await repo.get_match_records_by_room(db, room.room_id)
    assert len(records) == 0


# ===========================================================================
# PromptSubmission CRUD
# ===========================================================================

@pytest.mark.asyncio
async def test_create_submission_minimal(db):
    user = await _make_user(db)
    room = await _make_room(db, user1_id=user.user_id)
    sub = await repo.create_submission(
        db,
        room_id=room.room_id,
        user_id=user.user_id,
        submitted_prompt="Extract the profit.",
    )
    assert sub.submission_id is not None
    assert sub.submitted_prompt == "Extract the profit."
    assert sub.final_score is None
    assert sub.test_results is None


@pytest.mark.asyncio
async def test_create_submission_full(db):
    user = await _make_user(db)
    room = await _make_room(db, user1_id=user.user_id)
    test_results = {"results": [True, False, True, True], "correct": 3, "total": 4}
    sub = await repo.create_submission(
        db,
        room_id=room.room_id,
        user_id=user.user_id,
        submitted_prompt="My prompt here",
        prompt_length=14,
        ai_response="some AI output",
        test_results=test_results,
        final_score=75.0,
    )
    assert sub.prompt_length == 14
    assert sub.ai_response == "some AI output"
    assert sub.test_results["correct"] == 3
    assert float(sub.final_score) == 75.0


@pytest.mark.asyncio
async def test_get_submissions_by_room(db):
    user = await _make_user(db)
    room = await _make_room(db, user1_id=user.user_id)
    await repo.create_submission(db, room_id=room.room_id, user_id=user.user_id, submitted_prompt="p1")
    await repo.create_submission(db, room_id=room.room_id, user_id=user.user_id, submitted_prompt="p2")
    subs = await repo.get_submissions_by_room(db, room.room_id)
    assert len(subs) == 2


@pytest.mark.asyncio
async def test_get_submissions_by_user(db):
    user = await _make_user(db)
    room = await _make_room(db, user1_id=user.user_id)
    await repo.create_submission(db, room_id=room.room_id, user_id=user.user_id, submitted_prompt="prompt")
    subs = await repo.get_submissions_by_user(db, user.user_id)
    assert len(subs) == 1
    assert subs[0].submitted_prompt == "prompt"


@pytest.mark.asyncio
async def test_get_submissions_by_room_empty(db):
    room = await _make_room(db)
    subs = await repo.get_submissions_by_room(db, room.room_id)
    assert len(subs) == 0


@pytest.mark.asyncio
async def test_submission_test_results_json(db):
    user = await _make_user(db)
    room = await _make_room(db, user1_id=user.user_id)
    payload = {
        "results": [
            {"input": "Q1 profit was $12.5 million.", "expected": "12500000.00", "correct": True},
            {"input": "No profit figure.", "expected": "N/A", "correct": True},
        ],
        "correct": 2,
        "total": 2,
    }
    sub = await repo.create_submission(
        db,
        room_id=room.room_id,
        user_id=user.user_id,
        submitted_prompt="Extract profit accurately.",
        test_results=payload,
        final_score=100.0,
    )
    fetched = await repo.get_submissions_by_user(db, user.user_id)
    assert fetched[0].test_results["results"][0]["correct"] is True


# ===========================================================================
# 복합 시나리오: 전체 대전 흐름
# ===========================================================================

@pytest.mark.asyncio
async def test_full_match_flow(db):
    # 1. 유저 생성
    user1 = await _make_user(db, login_id="player1", nickname="Player1", tokens=1000)
    user2 = await _make_user(db, login_id="player2", nickname="Player2", tokens=1000)

    # 2. 문제 및 테스트 케이스 생성
    problem = await _make_problem(db, title="Profit Extractor", ptype="extraction")
    await repo.add_test_case(db, problem_id=problem.problem_id, input_value="Q1 was $1M", expected_answer="1000000.00")
    await repo.add_test_case(db, problem_id=problem.problem_id, input_value="No data.", expected_answer="N/A")

    # 3. 방 생성 + 참가
    room = await repo.create_room(db, room_code="MATCH01", user1_id=user1.user_id, base_ai_model="solar-pro")
    room = await repo.join_room(db, room.room_id, user2_id=user2.user_id)
    assert room.status == RoomStatus.in_progress

    # 4. 양측 프롬프트 제출
    sub1 = await repo.create_submission(
        db,
        room_id=room.room_id,
        user_id=user1.user_id,
        submitted_prompt="Extract USD profit exactly.",
        prompt_length=28,
        test_results={"correct": 2, "total": 2},
        final_score=100.0,
    )
    sub2 = await repo.create_submission(
        db,
        room_id=room.room_id,
        user_id=user2.user_id,
        submitted_prompt="Tell me the profit number.",
        prompt_length=26,
        test_results={"correct": 1, "total": 2},
        final_score=50.0,
    )

    # 5. 전적 기록
    record = await repo.create_match_record(
        db,
        room_id=room.room_id,
        problem_id=problem.problem_id,
        winner_id=user1.user_id,
        loser_id=user2.user_id,
    )

    # 6. 방 완료 처리
    room = await repo.update_room_status(db, room.room_id, RoomStatus.completed)
    assert room.status == RoomStatus.completed

    # 7. 토큰 업데이트
    await repo.update_user_tokens(db, user1.user_id, delta=50)
    await repo.update_user_tokens(db, user2.user_id, delta=-50)

    winner = await repo.get_user_by_id(db, user1.user_id)
    loser = await repo.get_user_by_id(db, user2.user_id)
    assert winner.current_tokens == 1050
    assert loser.current_tokens == 950

    # 8. 검증
    subs = await repo.get_submissions_by_room(db, room.room_id)
    assert len(subs) == 2

    records = await repo.get_match_records_by_room(db, room.room_id)
    assert len(records) == 1
    assert records[0].winner_id == user1.user_id

    problem_fetched = await repo.get_problem_by_id(db, problem.problem_id)
    assert len(problem_fetched.test_cases) == 2
