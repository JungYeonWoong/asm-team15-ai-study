"""REST API 테스트: 세션 확인, 방 생성, 방 상태 조회."""

from __future__ import annotations

from .conftest import create_room, new_client_id


# --- 1. 세션 확인 -----------------------------------------------------------
def test_me_ok(client):
    cid = new_client_id()
    resp = client.get("/api/me", headers={"X-Client-ID": cid})
    assert resp.status_code == 200
    body = resp.json()
    assert body["client_id"] == cid
    assert body["status"] == "active"
    # 인증 확장 후 추가 필드 (X-Client-ID 폴백 시 provider="client-id")
    assert body.get("provider") == "client-id"


def test_me_missing_header(client):
    resp = client.get("/api/me")
    assert resp.status_code == 400


# --- 2. 방 생성 -------------------------------------------------------------
def test_create_room_ok(client):
    cid = new_client_id()
    resp = client.post("/api/rooms", headers={"X-Client-ID": cid})
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "WAITING"
    assert body["current_players"] == 1
    assert body["created_by"] == cid
    assert len(body["room_code"]) == 4
    assert body["room_code"].isdigit()


def test_create_room_missing_header(client):
    resp = client.post("/api/rooms")
    assert resp.status_code == 400


def test_create_room_conflict_when_already_in_room(client):
    cid = new_client_id()
    first = client.post("/api/rooms", headers={"X-Client-ID": cid})
    assert first.status_code == 201
    second = client.post("/api/rooms", headers={"X-Client-ID": cid})
    assert second.status_code == 409


# --- 3. 방 상태 조회 --------------------------------------------------------
def test_get_room_ok(client):
    cid = new_client_id()
    code = create_room(client, cid)
    resp = client.get(f"/api/rooms/{code}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["room_code"] == code
    assert body["status"] == "WAITING"
    assert body["current_players"] == 1


def test_get_room_not_found(client):
    resp = client.get("/api/rooms/9999")
    assert resp.status_code == 404
