from __future__ import annotations

import os

import requests

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


def create_room(client_id: str) -> str:
    """방 생성 후 room_code 반환. 실패 시 예외 발생."""
    resp = requests.post(
        f"{BACKEND_URL}/api/rooms",
        headers={"X-Client-ID": client_id},
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json()["room_code"]


def get_room(room_code: str) -> dict:
    """방 상태 조회. 실패 시 예외 발생."""
    resp = requests.get(
        f"{BACKEND_URL}/api/rooms/{room_code}",
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json()
