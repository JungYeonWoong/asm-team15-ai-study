"""결과 기록 저장소 + /api/me/history 테스트."""

from __future__ import annotations

from app.history.store import InMemoryHistoryStore


# ---------------------------------------------------------------------------
# Store 단위
# ---------------------------------------------------------------------------
def _record_kwargs(**over):
    base = dict(
        user_id="u1",
        room_code="1234",
        task_id="translate-positive",
        result="WIN",
        winner_id="u1",
        my_score=0.9,
        opponent_score=0.5,
        correct_count=4,
        total_count=5,
        prompt_length=120,
    )
    base.update(over)
    return base


def test_store_records_and_lists_latest_first():
    store = InMemoryHistoryStore(maxlen=3)
    store.record(**_record_kwargs(result="WIN"))
    store.record(**_record_kwargs(result="LOSE"))
    store.record(**_record_kwargs(result="DRAW"))

    items = store.list_for("u1")
    assert [i.result for i in items] == ["DRAW", "LOSE", "WIN"]


def test_store_isolates_users():
    store = InMemoryHistoryStore()
    store.record(**_record_kwargs(user_id="a"))
    store.record(**_record_kwargs(user_id="b"))
    assert len(store.list_for("a")) == 1
    assert len(store.list_for("b")) == 1


def test_store_respects_maxlen():
    store = InMemoryHistoryStore(maxlen=2)
    for i in range(5):
        store.record(**_record_kwargs(room_code=f"r{i}"))
    items = store.list_for("u1")
    assert len(items) == 2
    assert [i.room_code for i in items] == ["r4", "r3"]


def test_unknown_user_returns_empty():
    store = InMemoryHistoryStore()
    assert store.list_for("nope") == []


# ---------------------------------------------------------------------------
# /api/me/history 엔드포인트
# ---------------------------------------------------------------------------
def test_history_endpoint_requires_auth(client):
    resp = client.get("/api/me/history")
    assert resp.status_code == 400


def test_history_endpoint_empty_for_new_user(client):
    cid = "11111111-1111-1111-1111-111111111111"
    resp = client.get("/api/me/history", headers={"X-Client-ID": cid})
    assert resp.status_code == 200
    assert resp.json() == []


def test_history_records_after_round(client, server):
    """대전 1회 진행 후 양 플레이어의 history 가 적재되어야 한다."""
    host = "h-" + "0" * 30
    guest = "g-" + "0" * 30
    code = client.post("/api/rooms", headers={"X-Client-ID": host}).json()[
        "room_code"
    ]

    def ws_url(cid):
        return f"/ws/arena/{code}?client_id={cid}"

    with client.websocket_connect(ws_url(host)) as wsa:
        wsa.send_json({"action": "JOIN"})
        wsa.receive_json()  # WAITING
        with client.websocket_connect(ws_url(guest)) as wsb:
            wsb.send_json({"action": "JOIN"})
            # ROUND_START 양쪽 수신
            wsa.receive_json()
            wsb.receive_json()

            wsa.send_json({"action": "SUBMIT", "prompt_text": "abcabc"})
            # WAITING for opponent
            wsa.receive_json()
            wsb.send_json({"action": "SUBMIT", "prompt_text": "xyzxyz"})
            # RESULT 양쪽 수신
            wsa.receive_json()
            wsb.receive_json()

    h = client.get("/api/me/history", headers={"X-Client-ID": host}).json()
    assert len(h) == 1
    assert h[0]["room_code"] == code
    assert h[0]["task_id"] == "test-echo"  # conftest 의 task_override
