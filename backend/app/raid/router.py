"""보스 레이드 WebSocket 라우터.

WS /ws/raid/{room_code}?client_id={uuid}

클라이언트 액션: JOIN, SUBMIT (prompt_text)
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.rooms.domain import RoomStatus

router = APIRouter()

# WebSocket 종료 코드 (RFC 6455 사설 영역)
WS_CLOSE_NO_CLIENT_ID = 4001
WS_CLOSE_ROOM_UNAVAILABLE = 4004


@router.websocket("/ws/raid/{room_code}")
async def raid(websocket: WebSocket, room_code: str):
    server = websocket.app.state.server
    client_id = websocket.query_params.get("client_id")

    if not client_id:
        await websocket.close(code=WS_CLOSE_NO_CLIENT_ID)
        return

    room = server.rooms.get(room_code)
    if room is None or room.status == RoomStatus.CLOSED:
        if room is None or client_id not in room.players:
            await websocket.close(code=WS_CLOSE_ROOM_UNAVAILABLE)
            return

    # 이미 진행 중인 레이드에 멤버가 아닌 신규 입장은 거부.
    game = server.games.get(room_code)
    if game is not None and game.started and client_id not in game.slot_of:
        await websocket.close(code=WS_CLOSE_ROOM_UNAVAILABLE)
        return
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
                await server.handle_join(room, client_id, websocket)
            elif action == "SUBMIT":
                await server.handle_submit(room, client_id, data.get("prompt_text"))
    except WebSocketDisconnect:
        await server.handle_disconnect(room, client_id)
