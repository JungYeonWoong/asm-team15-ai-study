"""인증/세션 라우터 테스트.

- /api/auth/dev-login : 무인증 즉시 로그인 + 자동 닉네임
- /api/auth/login    : 닉네임 검증 + 토큰 발급
- /api/auth/logout   : 토큰 폐기 후 401
- /api/auth/social/* : stub 501
- /api/me            : Bearer 토큰 인증 동작
"""

from __future__ import annotations

import pytest

from app.auth.session_store import (
    InMemorySessionStore,
    RedisSessionStore,
    build_session_store,
)


# ---------------------------------------------------------------------------
# HTTP 흐름
# ---------------------------------------------------------------------------
def test_dev_login_auto_nickname(client):
    resp = client.post("/api/auth/dev-login", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token"]
    assert body["provider"] == "dev"
    assert body["nickname"].startswith("dev-")
    assert body["user_id"].startswith("u_")


def test_dev_login_with_nickname(client):
    resp = client.post("/api/auth/dev-login", json={"nickname": "tester"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["nickname"] == "tester"


def test_nickname_login_and_resolve(client):
    resp = client.post("/api/auth/login", json={"nickname": "alice"})
    assert resp.status_code == 200
    token = resp.json()["token"]

    me = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["nickname"] == "alice"
    assert body["provider"] == "nickname"


def test_nickname_login_rejects_bad_format(client):
    resp = client.post("/api/auth/login", json={"nickname": "a"})  # too short
    assert resp.status_code == 400


def test_nickname_login_requires_nickname(client):
    resp = client.post("/api/auth/login", json={})
    assert resp.status_code == 422  # missing required field


def test_nickname_same_input_same_user_id(client):
    a = client.post("/api/auth/login", json={"nickname": "alice"}).json()
    b = client.post("/api/auth/login", json={"nickname": "alice"}).json()
    assert a["user_id"] == b["user_id"]
    assert a["token"] != b["token"]  # 토큰은 매번 새로 발급


def test_logout_invalidates_token(client):
    token = client.post(
        "/api/auth/dev-login", json={"nickname": "bob"}
    ).json()["token"]
    out = client.post(
        "/api/auth/logout", headers={"Authorization": f"Bearer {token}"}
    )
    assert out.status_code == 200

    me = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 401  # 토큰 무효 → 401


def test_missing_auth_returns_400(client):
    resp = client.get("/api/me")
    assert resp.status_code == 400


def test_invalid_bearer_token_returns_401(client):
    resp = client.get(
        "/api/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert resp.status_code == 401


def test_social_stub_returns_501(client):
    resp = client.post("/api/auth/social/google")
    assert resp.status_code == 501


def test_bearer_token_used_for_create_room(client):
    token = client.post(
        "/api/auth/dev-login", json={"nickname": "host"}
    ).json()["token"]
    resp = client.post(
        "/api/rooms", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "WAITING"
    assert body["current_players"] == 1


# ---------------------------------------------------------------------------
# SessionStore 직접 테스트
# ---------------------------------------------------------------------------
async def test_inmemory_store_set_get_delete():
    store = InMemorySessionStore()
    await store.set("t1", {"user_id": "u_1", "nickname": "a", "provider": "dev"}, 60)
    got = await store.get("t1")
    assert got == {"user_id": "u_1", "nickname": "a", "provider": "dev"}
    await store.delete("t1")
    assert await store.get("t1") is None


async def test_inmemory_store_ttl_expires():
    store = InMemorySessionStore()
    await store.set("t1", {"v": 1}, ttl_seconds=1)
    # 강제로 시간 경과 시뮬레이션
    expires_at, data = store._data["t1"]
    store._data["t1"] = (expires_at - 10, data)
    assert await store.get("t1") is None


async def test_build_session_store_no_redis_url_uses_memory():
    store = build_session_store("")
    assert isinstance(store, InMemorySessionStore)


async def test_redis_store_with_fakeredis():
    fakeredis = pytest.importorskip("fakeredis")
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = RedisSessionStore(url="ignored", client=client)
    await store.set("tok", {"user_id": "u_x", "nickname": "x", "provider": "dev"}, 60)
    got = await store.get("tok")
    assert got == {"user_id": "u_x", "nickname": "x", "provider": "dev"}
    assert await store.ping() is True
    await store.delete("tok")
    assert await store.get("tok") is None
