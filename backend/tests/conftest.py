"""테스트 공용 픽스처.

- TestClient (starlette) 로 REST + WebSocket 을 동기적으로 검증한다.
- GameServer 에 결정론적 과제와 AI 클라이언트를 주입해 채점 결과를 통제한다.
"""

from __future__ import annotations

import uuid
from typing import Iterable

import pytest
from fastapi.testclient import TestClient

from app.arena.ai_client import CallableAIClient
from app.arena.domain import Task, TestCase
from app.arena.game import GameServer
from app.core.config import Settings
from app.main import create_app

# 결정론적 테스트 과제 (N=4)
TEST_TASK = Task(
    id="test-echo",
    description="입력을 그대로 출력하시오.",
    model="Test-Model",
    test_cases=(
        TestCase(input="a", expected="A"),
        TestCase(input="b", expected="B"),
        TestCase(input="c", expected="C"),
        TestCase(input="d", expected="D"),
    ),
)
ANSWER_KEY = {tc.input: tc.expected for tc in TEST_TASK.test_cases}


def make_scripted_ai(correct_inputs_by_prompt: dict[str, Iterable[str]]):
    """프롬프트별로 '어떤 입력을 맞힐지'를 지정하는 결정론적 AI.

    correct_inputs_by_prompt[prompt] 에 포함된 입력은 정답(expected)을,
    나머지는 오답 문자열을 돌려준다.
    """
    table = {p: set(inputs) for p, inputs in correct_inputs_by_prompt.items()}

    def fn(model: str, prompt: str, test_input: str) -> str:
        if test_input in table.get(prompt, set()):
            return ANSWER_KEY[test_input]
        return "__WRONG__"

    return CallableAIClient(fn)


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def server(client):
    """현재 앱의 GameServer. 테스트가 훅을 주입할 수 있다."""
    srv = client.app.state.server
    srv.task_override = TEST_TASK
    srv.time_limit = 1  # 타임아웃 테스트 속도용
    return srv


def new_client_id() -> str:
    return str(uuid.uuid4())


def create_room(client, host_id: str) -> str:
    resp = client.post("/api/rooms", headers={"X-Client-ID": host_id})
    assert resp.status_code == 201, resp.text
    return resp.json()["room_code"]


# ---------------------------------------------------------------------------
# 게임 엔진 직접 테스트용 (TestClient 없이 단일 이벤트 루프에서 검증)
# ---------------------------------------------------------------------------
class FakeWebSocket:
    """send_json 을 기록만 하는 가짜 WebSocket."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)

    @property
    def events(self) -> list[str]:
        return [m.get("event") for m in self.sent]

    def last_of(self, event: str) -> dict:
        for msg in reversed(self.sent):
            if msg.get("event") == event:
                return msg
        raise AssertionError(f"event={event} 메시지가 없습니다. got={self.events}")

    def has(self, event: str) -> bool:
        return event in self.events


def make_server(time_limit: float = 5.0) -> GameServer:
    """결정론적 과제가 주입된 독립 GameServer (TestClient 무관)."""
    srv = GameServer(Settings())
    srv.task_override = TEST_TASK
    srv.time_limit = time_limit
    return srv
