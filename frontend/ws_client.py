from __future__ import annotations

import json
import os
import queue
import threading

import websocket

WS_URL = os.getenv("WS_URL", "ws://localhost:8000")


def connect(room_code: str, client_id: str) -> websocket.WebSocket:
    """WebSocket 연결 수립. 실패 시 예외 발생."""
    url = f"{WS_URL}/ws/arena/{room_code}?client_id={client_id}"
    ws = websocket.WebSocket()
    ws.connect(url)
    return ws


def start_recv_thread(ws: websocket.WebSocket, q: queue.Queue) -> threading.Thread:
    """백그라운드에서 ws.recv() 루프 실행. 수신 메시지를 q에 적재."""
    def _loop() -> None:
        while True:
            try:
                raw = ws.recv()
                if raw:
                    q.put(json.loads(raw))
            except Exception:
                q.put({"event": "WS_CLOSED"})
                break

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t


def send_join(ws: websocket.WebSocket) -> None:
    ws.send(json.dumps({"action": "JOIN"}))


def send_submit(ws: websocket.WebSocket, prompt_text: str) -> None:
    ws.send(json.dumps({"action": "SUBMIT", "prompt_text": prompt_text}))


def close(ws: websocket.WebSocket) -> None:
    try:
        ws.close()
    except Exception:
        pass
