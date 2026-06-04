"""FastAPI 진입점: 기능별 라우터를 조립한다.

Base URL: http://localhost:8000

기능별 패키지
  - app.session  : 세션 확인 (/api/me)
  - app.auth     : 로그인/세션 토큰 (/api/auth/*)
  - app.rooms    : 방 생성/조회 (/api/rooms)
  - app.arena    : WebSocket 대전 (/ws/arena/{room_code}) + GET /api/tasks
  - app.history  : 결과 기록 (/api/me/history)
  - app.health   : 상태 점검 (/healthz)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.arena.game import GameServer
from app.arena.router import router as arena_router
from app.arena.task_repository import TaskRepository
from app.arena.tasks_router import router as tasks_router
from app.auth.providers import DevProvider, NicknameProvider
from app.auth.router import router as auth_router
from app.auth.service import AuthService
from app.auth.session_store import build_session_store
from app.core.config import get_settings
from app.health.router import router as health_router
from app.history.router import router as history_router
from app.history.store import InMemoryHistoryStore
from app.rooms.router import router as rooms_router
from app.session.router import router as session_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = app.state.settings
    if settings.database_url:
        try:
            from app.db.database import init_engine, get_session_factory
            init_engine(settings.database_url)
            async with get_session_factory()() as db:
                await app.state.task_repo.load(db)
            logger.info("과제 풀을 DB에서 로드했습니다 (%d개).", len(app.state.task_repo._pool))
        except Exception:
            logger.exception("DB 과제 로드 실패 — 하드코딩 풀로 대체합니다.")
    else:
        logger.info("DATABASE_URL 미설정 — 하드코딩 과제 풀을 사용합니다.")
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Prompt Arena API", version="1.1-MVP", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    settings = get_settings()
    app.state.settings = settings

    # 과제 레포지토리 (lifespan에서 DB 로드)
    app.state.task_repo = TaskRepository()

    # 세션/인증
    app.state.session_store = build_session_store(settings.redis_url)
    app.state.auth_service = AuthService(
        store=app.state.session_store,
        providers={
            "dev": DevProvider(),
            "nickname": NicknameProvider(),
        },
        ttl_seconds=settings.session_ttl_seconds,
    )

    # 결과 기록
    app.state.history_store = InMemoryHistoryStore()

    # 대전 엔진
    app.state.server = GameServer(
        settings,
        history=app.state.history_store,
        task_repo=app.state.task_repo,
    )

    app.include_router(session_router)
    app.include_router(auth_router)
    app.include_router(rooms_router)
    app.include_router(arena_router)
    app.include_router(tasks_router)
    app.include_router(history_router)
    app.include_router(health_router)
    return app


app = create_app()
