"""방 기능 응답 스키마."""

from __future__ import annotations

from pydantic import BaseModel

from .domain import RoomStatus


class RoomCreatedResponse(BaseModel):
    room_code: str
    status: RoomStatus
    current_players: int
    created_by: str


class RoomStatusResponse(BaseModel):
    room_code: str
    status: RoomStatus
    current_players: int
