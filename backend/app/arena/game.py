"""대전 진행 오케스트레이션 (WebSocket 라운드 로직).

상태 머신:
  WAITING ──(2명 JOIN)──> PLAYING ──(양쪽 done)──> 채점 ──> RESULT/TIMEOUT
                                  └──(연결 끊김)──> ERROR(부전승)

GameServer 는 RoomManager 위에서 한 라운드의 입장/제출/타임아웃/채점/종료를
조정한다. 모든 상태 변경은 room.lock 으로 보호한다.
"""

from __future__ import annotations

import asyncio
import random
from typing import Optional

from app.core.config import Settings
from app.rooms.domain import Player, Room, RoomManager, RoomStatus

from . import ai_client as ai
from .ai_client import AIClient, AICallError, MockAIClient, UpstageAIClient
from .domain import PlayerResult, RoundResult, Task
from .safety import PromptSafety
from .scoring import compute_score
from .task_repository import TaskRepository
from .tasks import pick_task


class GameServer:
    """대전 서버. FastAPI app.state 에 하나 보관된다."""

    def __init__(
        self,
        settings: Settings,
        *,
        history=None,
        safety: Optional[PromptSafety] = None,
        task_repo: Optional[TaskRepository] = None,
    ) -> None:
        self.settings = settings
        self.rooms = RoomManager()
        self.history = history  # InMemoryHistoryStore or None
        self.safety = safety or PromptSafety(extra_banned=settings.banned_words)
        self.task_repo: Optional[TaskRepository] = task_repo

        # 테스트/오버라이드용 훅
        self.time_limit: float = settings.time_limit
        self.max_prompt_length: int = settings.max_prompt_length
        self.ai_max_retries: int = settings.ai_max_retries
        self.ai_client: Optional[AIClient] = None  # 설정 시 항상 이 클라이언트 사용
        self.task_override: Optional[Task] = None   # 설정 시 항상 이 과제 배정
        self._upstage_client: Optional[UpstageAIClient] = None  # 커넥션 풀 재사용
        self._rng = random.Random()

    # ------------------------------------------------------------------
    # AI 클라이언트 / 과제 선택
    # ------------------------------------------------------------------
    def _build_ai_client(self, task: Task) -> AIClient:
        if self.ai_client is not None:
            return self.ai_client
        if self.settings.ai_backend == "upstage" and self.settings.upstage_api_key:
            if self._upstage_client is None:
                self._upstage_client = UpstageAIClient(
                    self.settings.upstage_api_key, self.settings.upstage_base_url
                )
            return self._upstage_client
        # 데모 기본값: 과제 정답표를 알고 있는 결정론적 목 클라이언트
        answer_key = {tc.input: tc.expected for tc in task.test_cases}
        return MockAIClient(answer_key=answer_key)

    def _pick_task(self) -> Task:
        if self.task_override:
            return self.task_override
        if self.task_repo is not None:
            return self.task_repo.pick(self._rng)
        return pick_task(self._rng)

    # ------------------------------------------------------------------
    # WebSocket 라이프사이클
    # ------------------------------------------------------------------
    async def handle_join(self, room: Room, client_id: str, websocket) -> None:
        async with room.lock:
            if room.finalized or room.status in (
                RoomStatus.PLAYING,
                RoomStatus.CLOSED,
            ):
                if client_id not in room.players:
                    await self._safe_send(
                        websocket,
                        {
                            "event": "ERROR",
                            "code": "SERVER_ERROR",
                            "message": "입장할 수 없는 방입니다.",
                            "action_required": "GO_TO_HOME",
                        },
                    )
                    return

            player = room.players.get(client_id)
            if player is None:
                player = Player(client_id=client_id, websocket=websocket)
                room.players[client_id] = player
            else:
                player.websocket = websocket
            player.joined = True
            self.rooms.add_member(room, client_id)

            if room.joined_count >= 2:
                await self._start_round(room)
            else:
                room.status = RoomStatus.WAITING
                await self._safe_send(
                    websocket,
                    {
                        "event": "WAITING",
                        "message": "상대방을 기다리는 중입니다...",
                    },
                )

    async def _start_round(self, room: Room) -> None:
        """양쪽 모두 JOIN 했을 때 호출 (room.lock 보유 상태)."""
        room.status = RoomStatus.PLAYING
        room.task = self._pick_task()

        payload = {
            "event": "ROUND_START",
            "task": room.task.description,
            "model": room.task.model,
            "time_limit": self.time_limit,
        }
        for player in room.players.values():
            await self._safe_send(player.websocket, payload)

        # 플레이어별 타임아웃 타이머 시작
        for cid in list(room.players.keys()):
            room.timers[cid] = asyncio.create_task(self._timeout_watch(room, cid))

    async def handle_submit(
        self, room: Room, client_id: str, prompt_text: Optional[str]
    ) -> None:
        async with room.lock:
            player = room.players.get(client_id)
            if player is None or room.finalized:
                return
            if player.done:
                return  # 중복/지연 제출 무시
            if room.status != RoomStatus.PLAYING:
                return

            text = prompt_text or ""

            if len(text) > self.max_prompt_length:
                # 글자 수 초과: 제출 거부 + 자동 패배 처리
                player.over_length = True
                player.prompt_text = ""
                await self._safe_send(
                    player.websocket,
                    {
                        "event": "ERROR",
                        "code": "SERVER_ERROR",
                        "message": (
                            f"프롬프트가 최대 {self.max_prompt_length}자를 "
                            "초과하여 제출이 거부되었습니다. 자동 패배 처리됩니다."
                        ),
                        "action_required": "GO_TO_HOME",
                    },
                )
            else:
                safety_result = self.safety.validate(text)
                if not safety_result.ok:
                    player.unsafe = True
                    player.prompt_text = ""
                    await self._safe_send(
                        player.websocket,
                        {
                            "event": "ERROR",
                            "code": "SERVER_ERROR",
                            "message": (
                                f"부적절한 프롬프트로 판단되어 제출이 거부되었습니다. "
                                f"자동 패배 처리됩니다. ({safety_result.reason})"
                            ),
                            "action_required": "GO_TO_HOME",
                        },
                    )
                else:
                    player.submitted = True
                    player.prompt_text = text
                    # 제출 완료 → 상대 제출 대기 안내
                    await self._safe_send(
                        player.websocket,
                        {
                            "event": "WAITING",
                            "message": "상대방을 기다리는 중입니다...",
                        },
                    )

            await self._maybe_finalize(room)

    async def _timeout_watch(self, room: Room, client_id: str) -> None:
        try:
            await asyncio.sleep(self.time_limit)
        except asyncio.CancelledError:
            return
        async with room.lock:
            player = room.players.get(client_id)
            if player is None or room.finalized or player.done:
                return
            player.timed_out = True
            await self._maybe_finalize(room)

    async def handle_disconnect(self, room: Room, client_id: str) -> None:
        async with room.lock:
            if room.finalized:
                return
            player = room.players.get(client_id)
            if player is not None:
                player.joined = False
                player.websocket = None

            opponent = room.opponent_of(client_id)
            # 라운드가 시작되었고 상대가 아직 남아있다면 → 남은 사람(피탈주자) 부전승
            if room.status == RoomStatus.PLAYING and opponent is not None:
                room.finalized = True
                room.cancel_timers()
                await self._finalize_forfeit(
                    room, winner=opponent, deserter_id=client_id
                )
                self.rooms.close(room)
            elif room.joined_count == 0:
                # 아무도 안 남았으면 방 정리
                self.rooms.close(room)

    async def _finalize_forfeit(
        self, room: Room, *, winner: Player, deserter_id: str
    ) -> None:
        """상대 중도 이탈 시 남은 플레이어를 부전승(WIN) 처리한다 (lock 보유).

        탈주자는 점수와 무관하게 패배(LOSE), 피탈주자는 승리(WIN)로 확정한다.
        피탈주자에게는 RESULT(result=WIN, by_forfeit=True) 를 발송하고,
        히스토리에는 양쪽 결과를 모두 기록한다.
        """
        deserter = room.players.get(deserter_id)
        task_total = room.task.total_count if room.task else 0

        my_data = PlayerResult(
            client_id=winner.client_id,
            prompt=winner.prompt_text,
            ai_response="",
            correct_count=0,
            total_count=task_total,
            prompt_length=len(winner.prompt_text),
            score=0.0,
            test_case_results=[],
        ).to_dict()

        opp_data = None
        if deserter is not None:
            opp_data = PlayerResult(
                client_id=deserter.client_id,
                prompt=deserter.prompt_text,
                ai_response="",
                correct_count=0,
                total_count=task_total,
                prompt_length=len(deserter.prompt_text),
                score=0.0,
                test_case_results=[],
            ).to_dict()

        await self._safe_send(
            winner.websocket,
            {
                "event": "RESULT",
                "result": RoundResult.WIN.value,
                "winner_id": winner.client_id,
                "by_forfeit": True,
                "reason": "OPPONENT_DISCONNECTED",
                "message": "상대방이 게임을 떠나 부전승으로 승리했습니다.",
                "my_data": my_data,
                "opponent_data": opp_data,
            },
        )

        if self.history is not None and room.task is not None:
            self.history.record(
                user_id=winner.client_id,
                room_code=room.room_code,
                task_id=room.task.id,
                result=RoundResult.WIN.value,
                winner_id=winner.client_id,
                my_score=0.0,
                opponent_score=0.0,
                correct_count=0,
                total_count=task_total,
                prompt_length=len(winner.prompt_text),
            )
            self.history.record(
                user_id=deserter_id,
                room_code=room.room_code,
                task_id=room.task.id,
                result=RoundResult.LOSE.value,
                winner_id=winner.client_id,
                my_score=0.0,
                opponent_score=0.0,
                correct_count=0,
                total_count=task_total,
                prompt_length=len(deserter.prompt_text) if deserter else 0,
            )

    # ------------------------------------------------------------------
    # 채점 / 종료
    # ------------------------------------------------------------------
    async def _maybe_finalize(self, room: Room) -> None:
        """양쪽 플레이어가 모두 done 이면 채점 후 결과를 발송 (lock 보유)."""
        if room.finalized:
            return
        if len(room.players) < 2:
            return
        if not all(p.done for p in room.players.values()):
            return

        room.finalized = True
        room.cancel_timers()
        await self._finalize(room)

    async def _finalize(self, room: Room) -> None:
        assert room.task is not None
        players = list(room.players.values())

        # 1) 채점 (유효 제출 플레이어만 AI 호출, 병렬)
        client = self._build_ai_client(room.task)

        async def _grade_one(player: Player) -> None:
            if player.submitted:
                correct, total, sample, case_results = await ai.grade(
                    client,
                    room.task.model,
                    player.prompt_text,
                    room.task.test_cases,
                    max_retries=self.ai_max_retries,
                )
                player.correct_count = correct
                player.total_count = total
                player.ai_response = sample
                player.test_case_results = case_results
                player.score = compute_score(
                    correct, total, len(player.prompt_text),
                    self.max_prompt_length,
                )
                # 채점 출력을 LLM 에게 보여주고 프롬프트 총평을 받는다.
                # (부가 기능: 실패해도 라운드는 정상 종료된다)
                outputs = [cr["actual"] for cr in case_results]
                player.prompt_evaluation = await ai.evaluate_prompt(
                    client,
                    room.task.model,
                    player.prompt_text,
                    room.task.test_cases,
                    outputs,
                    max_retries=self.ai_max_retries,
                )
            else:
                # 타임아웃 / 글자수 초과 → 점수 0
                player.correct_count = 0
                player.total_count = room.task.total_count
                player.ai_response = ""
                player.score = 0.0

        try:
            await asyncio.gather(*(_grade_one(p) for p in players))
        except AICallError:
            await self._broadcast_ai_failure(room)
            self.rooms.close(room)
            return

        # 2) 승패 판정
        result_map, winner_id = self._decide_results(players)

        # 3) 이벤트 발송 (타임아웃 플레이어는 TIMEOUT, 그 외는 RESULT)
        for player in players:
            opponent = room.opponent_of(player.client_id)
            if player.timed_out:
                await self._safe_send(
                    player.websocket,
                    {
                        "event": "TIMEOUT",
                        "message": "제한 시간이 초과되었습니다. 자동 패배 처리됩니다.",
                        "result": RoundResult.LOSE.value,
                    },
                )
            else:
                await self._safe_send(
                    player.websocket,
                    self._build_result_payload(
                        player, opponent, result_map, winner_id
                    ),
                )

        # 결과 기록 저장 (양 플레이어 각각)
        if self.history is not None:
            for player in players:
                opponent = room.opponent_of(player.client_id)
                self.history.record(
                    user_id=player.client_id,
                    room_code=room.room_code,
                    task_id=room.task.id,
                    result=result_map[player.client_id].value,
                    winner_id=winner_id,
                    my_score=player.score,
                    opponent_score=opponent.score if opponent else 0.0,
                    correct_count=player.correct_count,
                    total_count=player.total_count,
                    prompt_length=len(player.prompt_text),
                )

        self.rooms.close(room)

    def _decide_results(
        self, players: list[Player]
    ) -> tuple[dict[str, RoundResult], Optional[str]]:
        """각 플레이어의 승패와 winner_id 를 정한다 (2인 기준)."""
        if len(players) < 2:
            p = players[0]
            return {p.client_id: RoundResult.WIN}, p.client_id
        p1, p2 = players[0], players[1]
        result_map: dict[str, RoundResult] = {}
        winner_id: Optional[str] = None

        if p1.loss_forced and p2.loss_forced:
            result_map[p1.client_id] = RoundResult.DRAW
            result_map[p2.client_id] = RoundResult.DRAW
        elif p1.loss_forced:
            result_map[p1.client_id] = RoundResult.LOSE
            result_map[p2.client_id] = RoundResult.WIN
            winner_id = p2.client_id
        elif p2.loss_forced:
            result_map[p1.client_id] = RoundResult.WIN
            result_map[p2.client_id] = RoundResult.LOSE
            winner_id = p1.client_id
        else:
            if p1.score > p2.score:
                result_map[p1.client_id] = RoundResult.WIN
                result_map[p2.client_id] = RoundResult.LOSE
                winner_id = p1.client_id
            elif p2.score > p1.score:
                result_map[p1.client_id] = RoundResult.LOSE
                result_map[p2.client_id] = RoundResult.WIN
                winner_id = p2.client_id
            else:
                result_map[p1.client_id] = RoundResult.DRAW
                result_map[p2.client_id] = RoundResult.DRAW

        return result_map, winner_id

    def _build_result_payload(
        self,
        me: Player,
        opponent: Optional[Player],
        result_map: dict[str, RoundResult],
        winner_id: Optional[str],
    ) -> dict:
        result = result_map[me.client_id]
        my_data = PlayerResult(
            client_id=me.client_id,
            prompt=me.prompt_text,
            ai_response=me.ai_response,
            correct_count=me.correct_count,
            total_count=me.total_count,
            prompt_length=len(me.prompt_text),
            score=me.score,
            test_case_results=me.test_case_results,
            prompt_evaluation=me.prompt_evaluation,
        ).to_dict()

        opp_data = None
        if opponent is not None:
            opp_data = PlayerResult(
                client_id=opponent.client_id,
                prompt=opponent.prompt_text,
                ai_response=opponent.ai_response,
                correct_count=opponent.correct_count,
                total_count=opponent.total_count,
                prompt_length=len(opponent.prompt_text),
                score=opponent.score,
                test_case_results=opponent.test_case_results,
                prompt_evaluation=opponent.prompt_evaluation,
            ).to_dict()

        return {
            "event": "RESULT",
            "result": result.value,
            "winner_id": winner_id,
            "my_data": my_data,
            "opponent_data": opp_data,
        }

    async def _broadcast_ai_failure(self, room: Room) -> None:
        for player in room.players.values():
            await self._safe_send(
                player.websocket,
                {
                    "event": "ERROR",
                    "code": "AI_CALL_FAILED",
                    "message": "AI 모델 호출에 실패했습니다. 라운드를 다시 시도해 주세요.",
                    "action_required": "RETRY_ROUND",
                },
            )

    # ------------------------------------------------------------------
    @staticmethod
    async def _safe_send(websocket, payload: dict) -> None:
        if websocket is None:
            return
        try:
            await websocket.send_json(payload)
        except Exception:  # noqa: BLE001 - 끊긴 소켓 전송 실패는 무시
            pass
