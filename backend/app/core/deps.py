"""공용 의존성: app.state 에 보관된 GameServer 접근."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from app.arena.game import GameServer


def get_server(request: Request) -> "GameServer":
    return request.app.state.server
