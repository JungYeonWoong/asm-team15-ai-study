"""대전 WebSocket 라우터.

WS /ws/arena/{room_code}?client_id={uuid}
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.rooms.domain import RoomStatus

router = APIRouter()

# WebSocket 종료 코드 (RFC 6455 사설 영역)
WS_CLOSE_NO_CLIENT_ID = 4001
WS_CLOSE_ROOM_UNAVAILABLE = 4004


@router.websocket("/ws/arena/{room_code}")
async def arena(websocket: WebSocket, room_code: str):
    gs = websocket.app.state.server
    client_id = websocket.query_params.get("client_id")

    # 연결 거부 조건
    if not client_id:
        await websocket.close(code=WS_CLOSE_NO_CLIENT_ID)
        return

    room = gs.rooms.get(room_code)
    if room is None or room.status in (RoomStatus.PLAYING, RoomStatus.CLOSED):
        # 이미 진행/종료된 방, 존재하지 않는 방 → 거부
        if room is None or client_id not in room.players:
            await websocket.close(code=WS_CLOSE_ROOM_UNAVAILABLE)
            return

    # 이미 2명이 차 있고 본인이 멤버가 아니면 거부
    if (
        room.current_players >= 2
        and client_id not in room.members
        and client_id not in room.players
    ):
        await websocket.close(code=WS_CLOSE_ROOM_UNAVAILABLE)
        return

    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            if action == "JOIN":
                await gs.handle_join(room, client_id, websocket)
            elif action == "SUBMIT":
                await gs.handle_submit(room, client_id, data.get("prompt_text"))
            # 그 외 액션은 무시
    except WebSocketDisconnect:
        await gs.handle_disconnect(room, client_id)
