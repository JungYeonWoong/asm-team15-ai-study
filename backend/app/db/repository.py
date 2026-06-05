"""CRUD helpers for all DB models."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    MatchRecord,
    Problem,
    ProblemTestCase,
    PromptSubmission,
    Room,
    RoomStatus,
    User,
)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

async def create_user(
    db: AsyncSession,
    *,
    login_id: str,
    password_hash: str,
    nickname: str,
    current_tokens: int = 1000,
) -> User:
    user = User(
        login_id=login_id,
        password_hash=password_hash,
        nickname=nickname,
        current_tokens=current_tokens,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


async def get_user_by_login_id(db: AsyncSession, login_id: str) -> User | None:
    result = await db.execute(select(User).where(User.login_id == login_id))
    return result.scalar_one_or_none()


async def update_user_tokens(db: AsyncSession, user_id: int, delta: int) -> User | None:
    user = await db.get(User, user_id)
    if user is None:
        return None
    user.current_tokens += delta
    await db.commit()
    await db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Problem
# ---------------------------------------------------------------------------

async def create_problem(
    db: AsyncSession,
    *,
    title: str,
    description: str,
    problem_type: str = "classification",
) -> Problem:
    problem = Problem(title=title, description=description, problem_type=problem_type)
    db.add(problem)
    await db.commit()
    await db.refresh(problem)
    return problem


async def get_problem_by_id(db: AsyncSession, problem_id: int) -> Problem | None:
    result = await db.execute(
        select(Problem)
        .where(Problem.problem_id == problem_id)
        .options(selectinload(Problem.test_cases))
    )
    return result.scalar_one_or_none()


async def list_problems(db: AsyncSession) -> Sequence[Problem]:
    result = await db.execute(select(Problem).options(selectinload(Problem.test_cases)))
    return result.scalars().all()


# ---------------------------------------------------------------------------
# ProblemTestCase
# ---------------------------------------------------------------------------

async def add_test_case(
    db: AsyncSession,
    *,
    problem_id: int,
    input_value: str,
    expected_answer: str,
) -> ProblemTestCase:
    tc = ProblemTestCase(
        problem_id=problem_id,
        input_value=input_value,
        expected_answer=expected_answer,
    )
    db.add(tc)
    await db.commit()
    await db.refresh(tc)
    return tc


async def get_test_cases_for_problem(
    db: AsyncSession, problem_id: int
) -> Sequence[ProblemTestCase]:
    result = await db.execute(
        select(ProblemTestCase).where(ProblemTestCase.problem_id == problem_id)
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------

async def create_room(
    db: AsyncSession,
    *,
    room_code: str,
    user1_id: int | None = None,
    base_ai_model: str | None = None,
) -> Room:
    room = Room(
        room_code=room_code,
        user1_id=user1_id,
        base_ai_model=base_ai_model,
    )
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return room


async def get_room_by_code(db: AsyncSession, room_code: str) -> Room | None:
    result = await db.execute(select(Room).where(Room.room_code == room_code))
    return result.scalar_one_or_none()


async def get_room_by_id(db: AsyncSession, room_id: int) -> Room | None:
    return await db.get(Room, room_id)


async def update_room_status(
    db: AsyncSession, room_id: int, status: RoomStatus
) -> Room | None:
    room = await db.get(Room, room_id)
    if room is None:
        return None
    room.status = status
    await db.commit()
    await db.refresh(room)
    return room


async def join_room(db: AsyncSession, room_id: int, user2_id: int) -> Room | None:
    room = await db.get(Room, room_id)
    if room is None:
        return None
    room.user2_id = user2_id
    room.status = RoomStatus.in_progress
    await db.commit()
    await db.refresh(room)
    return room


# ---------------------------------------------------------------------------
# MatchRecord
# ---------------------------------------------------------------------------

async def create_match_record(
    db: AsyncSession,
    *,
    room_id: int,
    problem_id: int | None = None,
    winner_id: int | None = None,
    loser_id: int | None = None,
) -> MatchRecord:
    record = MatchRecord(
        room_id=room_id,
        problem_id=problem_id,
        winner_id=winner_id,
        loser_id=loser_id,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def get_match_records_by_room(
    db: AsyncSession, room_id: int
) -> Sequence[MatchRecord]:
    result = await db.execute(
        select(MatchRecord).where(MatchRecord.room_id == room_id)
    )
    return result.scalars().all()


async def get_match_records_by_user(
    db: AsyncSession, user_id: int
) -> Sequence[MatchRecord]:
    result = await db.execute(
        select(MatchRecord).where(
            (MatchRecord.winner_id == user_id) | (MatchRecord.loser_id == user_id)
        )
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# PromptSubmission
# ---------------------------------------------------------------------------

async def create_submission(
    db: AsyncSession,
    *,
    room_id: int,
    user_id: int,
    submitted_prompt: str,
    prompt_length: int | None = None,
    ai_response: str | None = None,
    test_results: dict | None = None,
    final_score: float | None = None,
) -> PromptSubmission:
    sub = PromptSubmission(
        room_id=room_id,
        user_id=user_id,
        submitted_prompt=submitted_prompt,
        prompt_length=prompt_length,
        ai_response=ai_response,
        test_results=test_results,
        final_score=final_score,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub


async def get_submissions_by_room(
    db: AsyncSession, room_id: int
) -> Sequence[PromptSubmission]:
    result = await db.execute(
        select(PromptSubmission).where(PromptSubmission.room_id == room_id)
    )
    return result.scalars().all()


async def get_submissions_by_user(
    db: AsyncSession, user_id: int
) -> Sequence[PromptSubmission]:
    result = await db.execute(
        select(PromptSubmission).where(PromptSubmission.user_id == user_id)
    )
    return result.scalars().all()
