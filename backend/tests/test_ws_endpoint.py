"""WebSocket 엔드포인트 배선/거부 조건 테스트 (TestClient).

라운드 진행 로직은 test_game.py 에서 엔진을 직접 검증하므로, 여기서는
연결 수립/거부와 JOIN 직후 WAITING 만 확인한다.
"""

from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

from .conftest import create_room, new_client_id


def ws_url(code: str, cid: str) -> str:
    return f"/ws/arena/{code}?client_id={cid}"


def test_join_emits_waiting(client, server):
    host = new_client_id()
    code = create_room(client, host)
    with client.websocket_connect(ws_url(code, host)) as ws:
        ws.send_json({"action": "JOIN"})
        msg = ws.receive_json()
    assert msg["event"] == "WAITING"


def test_reject_missing_client_id(client, server):
    host = new_client_id()
    code = create_room(client, host)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/arena/{code}") as ws:
            ws.receive_json()


def test_reject_nonexistent_room(client, server):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(ws_url("0000", new_client_id())) as ws:
            ws.receive_json()
