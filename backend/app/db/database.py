"""Async SQLAlchemy engine + session factory.

Production:  DATABASE_URL=postgresql+asyncpg://...
Tests:       DATABASE_URL=sqlite+aiosqlite:///:memory:
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def init_engine(database_url: str):
    global _engine, _session_factory
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    _engine = create_async_engine(database_url, echo=False, connect_args=connect_args)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_engine():
    if _engine is None:
        raise RuntimeError("DB engine not initialised — call init_engine() first")
    return _engine


def get_session_factory():
    if _session_factory is None:
        raise RuntimeError("DB session factory not initialised — call init_engine() first")
    return _session_factory


async def get_db() -> AsyncSession:
    async with get_session_factory()() as session:
        yield session
