"""FastAPI 진입점: 기능별 라우터를 조립한다.

Base URL: http://localhost:8000
인증: 세션 기반 (MVP 는 프론트가 생성한 X-Client-ID UUID 만 사용)

기능별 패키지
  - app.session : 세션 확인 (/api/me)
  - app.rooms   : 방 생성/조회 (/api/rooms)
  - app.arena   : WebSocket 대전 (/ws/arena/{room_code})
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.arena.game import GameServer
from app.arena.router import router as arena_router
from app.core.config import get_settings
from app.rooms.router import router as rooms_router
from app.session.router import router as session_router


def create_app() -> FastAPI:
    app = FastAPI(title="Prompt Arena API", version="1.0-MVP")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.server = GameServer(get_settings())

    app.include_router(session_router)
    app.include_router(rooms_router)
    app.include_router(arena_router)
    return app


app = create_app()
