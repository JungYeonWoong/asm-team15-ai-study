"""대전 엔진(GameServer) 직접 테스트.

단일 이벤트 루프에서 handle_join / handle_submit / 타임아웃 / 연결 끊김을
직접 호출해 라운드 전 과정을 결정론적으로 검증한다.
"""

from __future__ import annotations

import asyncio

import pytest

from app.arena.ai_client import CallableAIClient
from .conftest import FakeWebSocket, make_scripted_ai, make_server, new_client_id


async def _join_both(server, room, host, guest):
    wa, wb = FakeWebSocket(), FakeWebSocket()
    await server.handle_join(room, host, wa)   # host → WAITING
    await server.handle_join(room, guest, wb)  # guest → ROUND_START (양쪽)
    return wa, wb


# ---------------------------------------------------------------------------
# 입장 / 라운드 시작
# ---------------------------------------------------------------------------
async def test_first_join_waiting_then_round_start():
    server = make_server()
    host, guest = new_client_id(), new_client_id()
    room = server.rooms.create(host)

    wa = FakeWebSocket()
    await server.handle_join(room, host, wa)
    assert wa.events == ["WAITING"]

    wb = FakeWebSocket()
    await server.handle_join(room, guest, wb)

    start_a = wa.last_of("ROUND_START")
    assert start_a["task"] == "입력을 그대로 출력하시오."
    assert start_a["model"] == "Test-Model"
    assert start_a["time_limit"] == server.time_limit
    assert wb.has("ROUND_START")


# ---------------------------------------------------------------------------
# 채점 / 승패
# ---------------------------------------------------------------------------
async def test_win_lose_by_score():
    server = make_server()
    server.ai_client = make_scripted_ai(
        {"HOST": ["a", "b", "c", "d"], "GUEST": ["a"]}
    )
    host, guest = new_client_id(), new_client_id()
    room = server.rooms.create(host)
    wa, wb = await _join_both(server, room, host, guest)

    await server.handle_submit(room, host, "HOST")
    assert wa.has("WAITING")  # 제출 후 상대 대기
    await server.handle_submit(room, guest, "GUEST")

    res_a = wa.last_of("RESULT")
    res_b = wb.last_of("RESULT")
    assert res_a["result"] == "WIN"
    assert res_b["result"] == "LOSE"
    assert res_a["winner_id"] == host
    assert res_a["my_data"]["correct_count"] == 4
    assert res_a["my_data"]["total_count"] == 4
    assert res_a["opponent_data"]["client_id"] == guest
    assert res_a["opponent_data"]["correct_count"] == 1
    assert res_a["my_data"]["score"] > res_a["opponent_data"]["score"]
    # 점수 범위 검증
    assert 0.0 <= res_a["my_data"]["score"] <= 1.0


async def test_draw_when_equal():
    server = make_server()
    server.ai_client = make_scripted_ai({"SAME": ["a", "b"]})
    host, guest = new_client_id(), new_client_id()
    room = server.rooms.create(host)
    wa, wb = await _join_both(server, room, host, guest)

    await server.handle_submit(room, host, "SAME")
    await server.handle_submit(room, guest, "SAME")

    assert wa.last_of("RESULT")["result"] == "DRAW"
    assert wb.last_of("RESULT")["result"] == "DRAW"
    assert wa.last_of("RESULT")["winner_id"] is None


# ---------------------------------------------------------------------------
# 타임아웃
# ---------------------------------------------------------------------------
async def test_timeout_auto_loss():
    server = make_server(time_limit=0.05)
    server.ai_client = make_scripted_ai({"HOST": ["a", "b", "c", "d"]})
    host, guest = new_client_id(), new_client_id()
    room = server.rooms.create(host)
    wa, wb = await _join_both(server, room, host, guest)

    await server.handle_submit(room, host, "HOST")
    # guest 미제출 → 타이머 발화 대기
    await asyncio.sleep(0.2)

    res_a = wa.last_of("RESULT")
    timeout_b = wb.last_of("TIMEOUT")
    assert res_a["result"] == "WIN"
    assert res_a["winner_id"] == host
    assert res_a["opponent_data"]["score"] == 0.0  # 상대(타임아웃) 점수 0
    assert timeout_b["result"] == "LOSE"
    assert not wb.has("RESULT")  # 타임아웃 플레이어는 RESULT 대신 TIMEOUT


async def test_both_timeout_draw():
    server = make_server(time_limit=0.05)
    host, guest = new_client_id(), new_client_id()
    room = server.rooms.create(host)
    wa, wb = await _join_both(server, room, host, guest)

    await asyncio.sleep(0.2)  # 둘 다 미제출

    assert wa.last_of("TIMEOUT")["result"] == "LOSE"
    assert wb.last_of("TIMEOUT")["result"] == "LOSE"


# ---------------------------------------------------------------------------
# 글자 수 초과 → 자동 패배
# ---------------------------------------------------------------------------
async def test_over_length_auto_loss():
    server = make_server()
    server.ai_client = make_scripted_ai({"GUEST": ["a", "b", "c", "d"]})
    host, guest = new_client_id(), new_client_id()
    room = server.rooms.create(host)
    wa, wb = await _join_both(server, room, host, guest)

    await server.handle_submit(room, host, "x" * 1201)  # 1200자 초과
    err = wa.last_of("ERROR")
    assert err["code"] == "SERVER_ERROR"

    await server.handle_submit(room, guest, "GUEST")

    assert wa.last_of("RESULT")["result"] == "LOSE"
    assert wa.last_of("RESULT")["my_data"]["score"] == 0.0
    assert wb.last_of("RESULT")["result"] == "WIN"
    assert wb.last_of("RESULT")["winner_id"] == guest


async def test_submit_rejected_after_done():
    """타임아웃/제출 완료 후 중복 제출은 무시된다."""
    server = make_server()
    server.ai_client = make_scripted_ai({"A": ["a"], "B": ["b"]})
    host, guest = new_client_id(), new_client_id()
    room = server.rooms.create(host)
    wa, wb = await _join_both(server, room, host, guest)

    await server.handle_submit(room, host, "A")
    await server.handle_submit(room, host, "AGAIN")  # 무시되어야 함
    assert room.players[host].prompt_text == "A"


# ---------------------------------------------------------------------------
# 연결 끊김 → 부전승
# ---------------------------------------------------------------------------
async def test_opponent_disconnect_forfeit():
    server = make_server(time_limit=30)
    host, guest = new_client_id(), new_client_id()
    room = server.rooms.create(host)
    wa, wb = await _join_both(server, room, host, guest)

    await server.handle_disconnect(room, guest)

    err = wa.last_of("ERROR")
    assert err["code"] == "OPPONENT_DISCONNECTED"
    assert err["action_required"] == "GO_TO_HOME"


# ---------------------------------------------------------------------------
# AI 호출 실패 → 라운드 무효
# ---------------------------------------------------------------------------
async def test_ai_call_failure():
    server = make_server()
    server.ai_max_retries = 2

    def boom(model, prompt, test_input):
        raise RuntimeError("model down")

    server.ai_client = CallableAIClient(boom)
    host, guest = new_client_id(), new_client_id()
    room = server.rooms.create(host)
    wa, wb = await _join_both(server, room, host, guest)

    await server.handle_submit(room, host, "A")
    await server.handle_submit(room, guest, "B")

    err_a = wa.last_of("ERROR")
    err_b = wb.last_of("ERROR")
    assert err_a["code"] == "AI_CALL_FAILED"
    assert err_a["action_required"] == "RETRY_ROUND"
    assert err_b["code"] == "AI_CALL_FAILED"
