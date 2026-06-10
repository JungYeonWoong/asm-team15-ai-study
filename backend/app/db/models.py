"""SQLAlchemy ORM models — mirror of db/init/01_init.sql."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class RoomStatus(str, enum.Enum):
    waiting = "waiting"
    in_progress = "in_progress"
    completed = "completed"


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    login_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    current_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    rooms_as_user1: Mapped[list[Room]] = relationship(
        "Room", foreign_keys="Room.user1_id", back_populates="user1"
    )
    rooms_as_user2: Mapped[list[Room]] = relationship(
        "Room", foreign_keys="Room.user2_id", back_populates="user2"
    )
    submissions: Mapped[list[PromptSubmission]] = relationship(
        "PromptSubmission", back_populates="user"
    )


class Problem(Base):
    __tablename__ = "problems"

    problem_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    problem_type: Mapped[str] = mapped_column(String(50), nullable=False, default="classification")
    # 보스 레이드 난이도 티어: "Low" | "Mid" | "High"
    difficulty: Mapped[str] = mapped_column(String(10), nullable=False, default="Mid")

    test_cases: Mapped[list[ProblemTestCase]] = relationship(
        "ProblemTestCase", back_populates="problem", cascade="all, delete-orphan"
    )
    match_records: Mapped[list[MatchRecord]] = relationship(
        "MatchRecord", back_populates="problem"
    )


class ProblemTestCase(Base):
    __tablename__ = "problem_test_cases"
    __table_args__ = (
        Index("idx_problem_test_cases_problem_id", "problem_id"),
    )

    test_case_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    problem_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("problems.problem_id", ondelete="CASCADE"), nullable=False
    )
    input_value: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[str] = mapped_column(Text, nullable=False)

    problem: Mapped[Problem] = relationship("Problem", back_populates="test_cases")


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        Index("idx_rooms_room_code", "room_code"),
    )

    room_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    user1_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.user_id"), nullable=True
    )
    user2_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.user_id"), nullable=True
    )
    status: Mapped[RoomStatus] = mapped_column(
        Enum(RoomStatus, name="room_status"), nullable=False, default=RoomStatus.waiting
    )
    base_ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    user1: Mapped[User | None] = relationship(
        "User", foreign_keys=[user1_id], back_populates="rooms_as_user1"
    )
    user2: Mapped[User | None] = relationship(
        "User", foreign_keys=[user2_id], back_populates="rooms_as_user2"
    )
    match_records: Mapped[list[MatchRecord]] = relationship(
        "MatchRecord", back_populates="room"
    )
    submissions: Mapped[list[PromptSubmission]] = relationship(
        "PromptSubmission", back_populates="room"
    )


class MatchRecord(Base):
    __tablename__ = "match_records"
    __table_args__ = (
        Index("idx_match_records_room_id", "room_id"),
    )

    record_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rooms.room_id"), nullable=False
    )
    problem_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("problems.problem_id"), nullable=True
    )
    winner_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.user_id"), nullable=True
    )
    loser_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.user_id"), nullable=True
    )
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    room: Mapped[Room] = relationship("Room", back_populates="match_records")
    problem: Mapped[Problem | None] = relationship("Problem", back_populates="match_records")


class PromptSubmission(Base):
    __tablename__ = "prompt_submissions"
    __table_args__ = (
        Index("idx_prompt_submissions_room_user", "room_id", "user_id"),
    )

    submission_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rooms.room_id"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.user_id"), nullable=False
    )
    submitted_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    final_score: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    room: Mapped[Room] = relationship("Room", back_populates="submissions")
    user: Mapped[User] = relationship("User", back_populates="submissions")
