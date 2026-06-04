"""/healthz 테스트."""

from __future__ import annotations


def test_healthz_ok_no_redis(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    # 기본 환경에서는 InMemory 백엔드
    assert body["session_backend"] == "memory"
    assert body["redis"] == "disabled"
