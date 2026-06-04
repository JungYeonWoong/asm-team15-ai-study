"""방 생성 / 조회 라우터."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Path

from app.core.deps import get_server

from .domain import RoomStatus
from .schemas import RoomCreatedResponse, RoomStatusResponse

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


@router.post("", response_model=RoomCreatedResponse, status_code=201)
def create_room(
    x_client_id: Optional[str] = Header(default=None),
    server=Depends(get_server),
):
    """2. 방 생성 — 호스트가 방을 만들고 방 코드를 발급받는다."""
    if not x_client_id:
        raise HTTPException(status_code=400, detail="X-Client-ID 헤더가 필요합니다.")

    existing = server.rooms.room_of_client(x_client_id)
    if existing is not None and existing.status != RoomStatus.CLOSED:
        raise HTTPException(status_code=409, detail="이미 다른 방에 참여 중입니다.")

    room = server.rooms.create(x_client_id)
    return RoomCreatedResponse(
        room_code=room.room_code,
        status=room.status,
        current_players=room.current_players,
        created_by=room.created_by,
    )


@router.get("/{room_code}", response_model=RoomStatusResponse)
def get_room(room_code: str = Path(...), server=Depends(get_server)):
    """3. 방 상태 조회 — WebSocket 연결 전 입장 가능 여부 확인."""
    room = server.rooms.get(room_code)
    if room is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 방 코드입니다.")
    return RoomStatusResponse(
        room_code=room.room_code,
        status=room.status,
        current_players=room.current_players,
    )
