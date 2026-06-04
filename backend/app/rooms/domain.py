"""방 / 플레이어 도메인 모델 및 저장소."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.arena.domain import Task


class RoomStatus(str, Enum):
    WAITING = "WAITING"  # 1명 대기 중, 입장 가능
    FULL = "FULL"        # 2명 모두 입장, 대기 중
    PLAYING = "PLAYING"  # 게임 진행 중, 입장 불가
    CLOSED = "CLOSED"    # 종료된 방


@dataclass
class Player:
    """방에 참여한 한 플레이어의 실시간 상태."""

    client_id: str
    websocket: object = None  # starlette WebSocket
    joined: bool = False

    # 라운드 진행 상태
    submitted: bool = False        # 유효 제출 완료
    prompt_text: str = ""          # 제출한 프롬프트 원문
    timed_out: bool = False        # 제한 시간 초과 (TIMEOUT 이벤트 대상)
    over_length: bool = False      # 글자 수 초과로 제출 거부 → 자동 패배

    # 채점 결과 (finalize 후 채워짐)
    correct_count: int = 0
    total_count: int = 0
    ai_response: str = ""
    score: float = 0.0

    @property
    def done(self) -> bool:
        """이 플레이어의 라운드 입력이 확정되었는지."""
        return self.submitted or self.timed_out or self.over_length

    @property
    def loss_forced(self) -> bool:
        """점수와 무관하게 패배가 확정되는 사유가 있는지."""
        return self.timed_out or self.over_length


@dataclass
class Room:
    """대전 방."""

    room_code: str
    created_by: str
    status: RoomStatus = RoomStatus.WAITING

    # 예약된 멤버(호스트는 생성 시 추가). current_players 표시에 사용.
    members: set[str] = field(default_factory=set)
    # 현재 활성 연결: client_id -> Player
    players: dict[str, Player] = field(default_factory=dict)

    task: "Optional[Task]" = None
    finalized: bool = False

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    timers: dict[str, asyncio.Task] = field(default_factory=dict)

    @property
    def current_players(self) -> int:
        return len(self.members)

    @property
    def joined_count(self) -> int:
        return sum(1 for p in self.players.values() if p.joined)

    def opponent_of(self, client_id: str) -> Optional[Player]:
        for cid, player in self.players.items():
            if cid != client_id:
                return player
        return None

    def cancel_timers(self) -> None:
        # finalize 가 타임아웃 타이머 안에서 호출될 수 있으므로, 현재 실행 중인
        # 타이머(자기 자신)는 취소하지 않는다. (자기 취소 시 다음 await 에서
        # CancelledError 가 발생해 finalize 가 중단됨)
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        for timer in self.timers.values():
            if timer is not current:
                timer.cancel()
        self.timers.clear()


class RoomManager:
    """방 저장소 및 코드 발급."""

    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        # client_id -> room_code (한 클라이언트는 한 방에만)
        self._membership: dict[str, str] = {}

    # -- 조회 ---------------------------------------------------------------
    def get(self, room_code: str) -> Optional[Room]:
        return self._rooms.get(room_code)

    def room_of_client(self, client_id: str) -> Optional[Room]:
        code = self._membership.get(client_id)
        return self._rooms.get(code) if code else None

    # -- 생성/소멸 ----------------------------------------------------------
    def generate_code(self) -> str:
        for _ in range(10_000):
            code = f"{random.randint(0, 9999):04d}"
            if code not in self._rooms:
                return code
        raise RuntimeError("방 코드 공간이 가득 찼습니다.")

    def create(self, client_id: str) -> Room:
        code = self.generate_code()
        room = Room(room_code=code, created_by=client_id)
        room.members.add(client_id)
        self._rooms[code] = room
        self._membership[client_id] = code
        return room

    def add_member(self, room: Room, client_id: str) -> None:
        room.members.add(client_id)
        self._membership[client_id] = room.room_code

    def remove_member(self, client_id: str) -> None:
        self._membership.pop(client_id, None)

    def close(self, room: Room) -> None:
        room.status = RoomStatus.CLOSED
        room.cancel_timers()
        for cid in list(room.members):
            self._membership.pop(cid, None)
        self._rooms.pop(room.room_code, None)
