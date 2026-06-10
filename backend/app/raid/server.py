"""협동 보스 레이드 진행 오케스트레이션 (WebSocket 라운드 루프).

RaidServer 는 매칭(RoomManager)·슬롯 배정·라운드 준비/제출/타임아웃·그래프 호출·
브로드캐스트를 담당한다. 라운드의 '디렉터 두뇌'(채점/난이도/HP/상태효과/종료 판정)는
LangGraph(``build_raid_graph``)가 맡고, 서버는 라운드를 이어붙인다.

상태 머신:
  WAITING ──(2명 JOIN)──> RAID_START → [ROUND_START → 양쪽 제출 → 그래프 → ROUND_RESULT] ×N
                                       └─ 보스 HP 0 또는 6라운드 도달 ──> RAID_END
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import Settings
from app.rooms.domain import Player, Room, RoomManager, RoomStatus

from app.arena import ai_client as ai
from app.arena.ai_client import AIClient, AICallError, MockAIClient, UpstageAIClient
from app.arena.domain import Task
from app.arena.safety import PromptSafety
from app.arena.task_repository import TaskRepository
from app.arena.tasks import pick_task

from .effects import effect_from_dict, effect_to_dict
from .graph import build_raid_graph
from .state import BossRaidState, new_campaign_state

SLOTS = ("p1", "p2")


@dataclass
class RaidGame:
    """한 방의 보스 레이드 캠페인 + 라운드 진행 상태."""

    room_code: str
    order: list[str] = field(default_factory=list)        # 입장 순서
    slot_of: dict[str, str] = field(default_factory=dict)  # client_id -> "p1"|"p2"
    campaign: BossRaidState = field(default_factory=dict)  # 라운드 간 유지 상태

    started: bool = False
    finalized: bool = False
    round_active: bool = False

    task: Optional[Task] = None
    cur_limit: dict[str, int] = field(default_factory=dict)   # 슬롯별 이번 라운드 글자수 제한
    cur_time_limit: dict[str, float] = field(default_factory=dict)  # 슬롯별 이번 라운드 제한시간
    cur_status: dict[str, str] = field(default_factory=dict)  # 슬롯별 이번 라운드 상태효과 표시
    cur_hint: dict[str, str] = field(default_factory=dict)    # 슬롯별 이번 라운드 힌트
    cur_effect: dict[str, dict] = field(default_factory=dict)  # 슬롯별 이번 라운드 활성 효과 dict
    round_started_at: float = 0.0                             # 이번 라운드 ROUND_START 시각(loop.time)
    sub: dict[str, dict] = field(default_factory=dict)        # 슬롯별 제출 {prompt,done,valid,timed_out,elapsed}

    def client_of(self, slot: str) -> Optional[str]:
        for cid, s in self.slot_of.items():
            if s == slot:
                return cid
        return None


class RaidServer:
    """보스 레이드 서버. FastAPI app.state 에 하나 보관된다."""

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
        self.history = history
        self.safety = safety or PromptSafety(extra_banned=settings.banned_words)
        self.task_repo: Optional[TaskRepository] = task_repo

        # 테스트/오버라이드 훅
        self.time_limit: float = settings.time_limit
        self.max_prompt_length: int = settings.max_prompt_length
        self.ai_max_retries: int = settings.ai_max_retries
        self.ai_client: Optional[AIClient] = None
        self.task_override: Optional[Task] = None
        self.boss_hp_override: Optional[float] = None   # 테스트용 보스 HP
        self.max_rounds_override: Optional[int] = None  # 테스트용 라운드 수
        self._upstage_client: Optional[UpstageAIClient] = None
        self._rng = random.Random()

        self.graph = build_raid_graph()
        self.games: dict[str, RaidGame] = {}

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
        answer_key = {tc.input: tc.expected for tc in task.test_cases}
        return MockAIClient(answer_key=answer_key)

    def _pick_task(self, difficulty: str) -> Task:
        if self.task_override:
            return self.task_override
        if self.task_repo is not None:
            return self.task_repo.pick(self._rng, difficulty=difficulty)
        return pick_task(self._rng, difficulty=difficulty)

    # ------------------------------------------------------------------
    # WebSocket 라이프사이클
    # ------------------------------------------------------------------
    async def handle_join(self, room: Room, client_id: str, websocket) -> None:
        async with room.lock:
            game = self.games.get(room.room_code)
            if game is not None and game.finalized:
                await self._safe_send(websocket, self._err("입장할 수 없는 방입니다."))
                return
            if room.status == RoomStatus.CLOSED:
                await self._safe_send(websocket, self._err("입장할 수 없는 방입니다."))
                return
            # 진행 중인 레이드에 신규(멤버 아님) 입장 거부
            if game is not None and game.started and client_id not in game.slot_of:
                await self._safe_send(websocket, self._err("이미 진행 중인 방입니다."))
                return

            player = room.players.get(client_id)
            if player is None:
                player = Player(client_id=client_id, websocket=websocket)
                room.players[client_id] = player
            else:
                player.websocket = websocket
            player.joined = True
            self.rooms.add_member(room, client_id)

            if game is None:
                game = RaidGame(room_code=room.room_code)
                self.games[room.room_code] = game
            if client_id not in game.slot_of and len(game.order) < 2:
                game.order.append(client_id)
                game.slot_of[client_id] = SLOTS[len(game.order) - 1]

            if room.joined_count >= 2 and not game.started:
                await self._start_raid(room, game)
            elif not game.started:
                room.status = RoomStatus.WAITING
                await self._safe_send(
                    websocket,
                    {"event": "WAITING", "message": "동료를 기다리는 중입니다..."},
                )

    async def _start_raid(self, room: Room, game: RaidGame) -> None:
        """양쪽 입장 완료 → 캠페인 시작 + 1라운드 준비 (room.lock 보유)."""
        game.started = True
        room.status = RoomStatus.PLAYING
        game.campaign = new_campaign_state(
            model="",
            ai_client=None,
            max_retries=self.ai_max_retries,
            base_char_limit=self.max_prompt_length,
        )
        if self.boss_hp_override is not None:
            game.campaign["boss_hp"] = self.boss_hp_override
            game.campaign["boss_max_hp"] = self.boss_hp_override
        if self.max_rounds_override is not None:
            game.campaign["max_rounds"] = self.max_rounds_override
        boss_intro = {
            "event": "RAID_START",
            "boss_hp": game.campaign["boss_hp"],
            "boss_max_hp": game.campaign["boss_max_hp"],
            "max_rounds": game.campaign["max_rounds"],
            "message": "보스 레이드 시작! 동료와 협력해 6라운드 안에 보스를 처치하세요.",
        }
        for cid in game.slot_of:
            await self._safe_send(room.players[cid].websocket, boss_intro)
        await self._prepare_round(room, game)

    async def _prepare_round(self, room: Room, game: RaidGame) -> None:
        """다음 라운드 과제를 검색(RAG-lite)하고 ROUND_START 를 발송 (room.lock 보유)."""
        campaign = game.campaign
        difficulty = campaign["current_difficulty"]
        task = self._pick_task(difficulty)
        game.task = task

        for slot in SLOTS:
            # 디렉터가 정한 다음 효과를 이번 라운드 활성 효과로 적용.
            effect = effect_from_dict(campaign.get(f"{slot}_next_effect"))
            game.cur_effect[slot] = effect_to_dict(effect)
            game.cur_limit[slot] = max(
                1, int(self.max_prompt_length * effect.char_limit_factor)
            )
            game.cur_time_limit[slot] = self.time_limit * effect.time_factor
            game.cur_status[slot] = effect.label
            hint = ""
            if effect.reveal_hint and task.test_cases:
                tc = task.test_cases[0]
                hint = f"예시 — 입력: {tc.input!r} → 정답: {tc.expected!r}"
            game.cur_hint[slot] = hint
            game.sub[slot] = {
                "prompt": "", "done": False, "valid": True,
                "timed_out": False, "elapsed": None,
            }

        game.round_active = True
        game.round_started_at = asyncio.get_running_loop().time()
        for cid, slot in game.slot_of.items():
            await self._safe_send(
                room.players[cid].websocket,
                {
                    "event": "ROUND_START",
                    "round": campaign["current_round"],
                    "max_rounds": campaign["max_rounds"],
                    "task": task.description,
                    "model": task.model,
                    "difficulty": difficulty,
                    "time_limit": game.cur_time_limit[slot],
                    "char_limit": game.cur_limit[slot],
                    "status_effect": game.cur_status[slot],
                    "effect": game.cur_effect[slot],
                    "hint": game.cur_hint[slot],
                    "boss_hp": campaign["boss_hp"],
                    "boss_max_hp": campaign["boss_max_hp"],
                    "your_slot": slot,
                },
            )

        # 플레이어별 타임아웃 타이머
        for cid in game.slot_of:
            room.timers[cid] = asyncio.create_task(
                self._timeout_watch(room, game, cid)
            )

    async def handle_submit(
        self, room: Room, client_id: str, prompt_text: Optional[str]
    ) -> None:
        async with room.lock:
            game = self.games.get(room.room_code)
            if game is None or game.finalized or not game.round_active:
                return
            slot = game.slot_of.get(client_id)
            if slot is None:
                return
            sub = game.sub.get(slot)
            if sub is None or sub["done"]:
                return

            text = prompt_text or ""
            limit = game.cur_limit[slot]
            ws = room.players[client_id].websocket

            # 무효 제출은 거부하되 라운드는 유지(시간 내 재제출 허용).
            if len(text) > limit:
                await self._safe_send(
                    ws,
                    {
                        "event": "SUBMIT_REJECTED",
                        "slot": slot,
                        "reason": "OVER_LENGTH",
                        "message": f"프롬프트가 {limit}자를 초과했습니다. 줄여서 다시 제출하세요.",
                    },
                )
                return
            safety_result = self.safety.validate(text)
            if not safety_result.ok:
                await self._safe_send(
                    ws,
                    {
                        "event": "SUBMIT_REJECTED",
                        "slot": slot,
                        "reason": "UNSAFE",
                        "message": f"부적절한 프롬프트입니다. 수정 후 다시 제출하세요. ({safety_result.reason})",
                    },
                )
                return

            elapsed = asyncio.get_running_loop().time() - game.round_started_at
            sub.update(
                prompt=text, done=True, valid=True, timed_out=False,
                elapsed=max(0.0, elapsed),
            )
            await self._safe_send(
                ws, {"event": "WAITING", "message": "동료의 제출을 기다리는 중..."}
            )
            # 동료에게 진행 상황 알림
            mate = game.client_of("p2" if slot == "p1" else "p1")
            if mate is not None and mate in room.players:
                await self._safe_send(
                    room.players[mate].websocket,
                    {"event": "TEAMMATE_SUBMITTED", "slot": slot},
                )

            await self._maybe_resolve(room, game)

    async def _timeout_watch(
        self, room: Room, game: RaidGame, client_id: str
    ) -> None:
        slot = game.slot_of.get(client_id)
        wait = game.cur_time_limit.get(slot, self.time_limit) if slot else self.time_limit
        try:
            await asyncio.sleep(wait)
        except asyncio.CancelledError:
            return
        async with room.lock:
            if game.finalized or not game.round_active:
                return
            slot = game.slot_of.get(client_id)
            sub = game.sub.get(slot) if slot else None
            if sub is None or sub["done"]:
                return
            sub.update(
                prompt="", done=True, valid=False, timed_out=True, elapsed=wait,
            )
            await self._safe_send(
                room.players[client_id].websocket,
                {
                    "event": "ROUND_TIMEOUT",
                    "slot": slot,
                    "message": "시간 초과 — 이번 라운드 기여 0 처리됩니다.",
                },
            )
            await self._maybe_resolve(room, game)

    async def _maybe_resolve(self, room: Room, game: RaidGame) -> None:
        if game.finalized or not game.round_active:
            return
        if not all(game.sub[s]["done"] for s in SLOTS):
            return
        game.round_active = False
        room.cancel_timers()
        await self._resolve_round(room, game)

    # ------------------------------------------------------------------
    # 라운드 채점(그래프 호출) / 종료
    # ------------------------------------------------------------------
    async def _resolve_round(self, room: Room, game: RaidGame) -> None:
        assert game.task is not None
        client = self._build_ai_client(game.task)

        state: dict = dict(game.campaign)
        state.update({
            "task": game.task,
            "model": game.task.model,
            "ai_client": client,
            "max_retries": self.ai_max_retries,
            "base_char_limit": self.max_prompt_length,
            "p1_prompt": game.sub["p1"]["prompt"],
            "p2_prompt": game.sub["p2"]["prompt"],
            "p1_char_limit": game.cur_limit["p1"],
            "p2_char_limit": game.cur_limit["p2"],
            "p1_valid": game.sub["p1"]["valid"],
            "p2_valid": game.sub["p2"]["valid"],
            "p1_elapsed": game.sub["p1"].get("elapsed"),
            "p2_elapsed": game.sub["p2"].get("elapsed"),
            "time_limit": self.time_limit,
            "p1_effect": game.cur_effect.get("p1", {}),
            "p2_effect": game.cur_effect.get("p2", {}),
        })

        try:
            out = await self.graph.ainvoke(state)
        except AICallError:
            await self._broadcast(room, game, self._ai_failure())
            self._close(room, game)
            return

        game.campaign = self._extract_campaign(out)
        await self._broadcast_round_result(room, game, out)

        if out["game_over"]:
            await self._broadcast_raid_end(room, game, out)
            self._record_history(room, game, out)
            self._close(room, game)
        else:
            await self._prepare_round(room, game)

    @staticmethod
    def _extract_campaign(out: dict) -> BossRaidState:
        """그래프 출력에서 다음 라운드로 이어갈 캠페인 상태만 추린다."""
        keys = (
            "current_round", "max_rounds", "boss_hp", "boss_max_hp",
            "team_score", "current_difficulty", "round_log",
            "p1_next_status", "p2_next_status",
            "p1_next_char_limit", "p2_next_char_limit",
            "p1_buff", "p2_buff",
            "p1_next_effect", "p2_next_effect", "director_rationale",
        )
        return BossRaidState(**{k: out[k] for k in keys if k in out})

    def _player_payload(self, game: RaidGame, out: dict, slot: str) -> dict:
        grade = out.get(f"{slot}_grade", {})
        cid = game.client_of(slot)
        return {
            "slot": slot,
            "client_id": cid,
            "prompt": game.sub[slot]["prompt"],
            "score": out.get(f"{slot}_score", 0.0),
            "damage": out.get(f"{slot}_damage", 0.0),
            "correct_count": grade.get("correct_count", 0),
            "total_count": grade.get("total_count", 0),
            "ai_response": grade.get("ai_response", ""),
            "test_case_results": grade.get("test_case_results", []),
            "prompt_evaluation": grade.get("prompt_evaluation", ""),
            "timed_out": game.sub[slot]["timed_out"],
            "elapsed": game.sub[slot].get("elapsed"),
            "next_status_effect": out.get(f"{slot}_next_status", "—"),
            "next_effect": out.get(f"{slot}_next_effect", {}),
        }

    async def _broadcast_round_result(
        self, room: Room, game: RaidGame, out: dict
    ) -> None:
        p1 = self._player_payload(game, out, "p1")
        p2 = self._player_payload(game, out, "p2")
        played_round = out["round_log"][-1]["round"] if out.get("round_log") else None
        system_message = (
            f"💥 보스에게 {out['damage_dealt']} 데미지! "
            f"(P1 {p1['damage']} + P2 {p2['damage']}) · "
            f"다음 난이도 {out['current_difficulty']}"
        )
        base = {
            "event": "ROUND_RESULT",
            "round": played_round,
            "round_score": out["round_score"],
            "damage_dealt": out["damage_dealt"],
            "boss_hp": out["boss_hp"],
            "boss_max_hp": out["boss_max_hp"],
            "next_difficulty": out["current_difficulty"],
            "director_rationale": out.get("director_rationale", ""),
            "p1": p1,
            "p2": p2,
            "system_message": system_message,
            "game_over": out["game_over"],
            "victory": out["victory"],
        }
        for cid, slot in game.slot_of.items():
            await self._safe_send(
                room.players[cid].websocket, {**base, "your_slot": slot}
            )

    async def _broadcast_raid_end(
        self, room: Room, game: RaidGame, out: dict
    ) -> None:
        payload = {
            "event": "RAID_END",
            "victory": out["victory"],
            "boss_hp": out["boss_hp"],
            "boss_max_hp": out["boss_max_hp"],
            "team_score": out["team_score"],
            "rounds_played": len(out.get("round_log", [])),
            "round_log": out.get("round_log", []),
            "message": (
                "🏆 보스 처치 성공! 협동 승리!"
                if out["victory"]
                else "🛡️ 보스를 처치하지 못했습니다. 다시 도전하세요!"
            ),
        }
        await self._broadcast(room, game, payload)

    def _record_history(self, room: Room, game: RaidGame, out: dict) -> None:
        if self.history is None:
            return
        result = "WIN" if out["victory"] else "LOSE"
        for cid in game.slot_of:
            self.history.record(
                user_id=cid,
                room_code=room.room_code,
                task_id="raid",
                result=result,
                winner_id=None,
                my_score=out["team_score"],
                opponent_score=0.0,
                correct_count=0,
                total_count=0,
                prompt_length=0,
            )

    async def handle_disconnect(self, room: Room, client_id: str) -> None:
        async with room.lock:
            game = self.games.get(room.room_code)
            player = room.players.get(client_id)
            if player is not None:
                player.joined = False
                player.websocket = None

            if game is not None and not game.finalized and game.started:
                # 협동 모드: 한 명이 이탈하면 레이드 종료.
                room.cancel_timers()
                game.finalized = True
                for cid in game.slot_of:
                    if cid != client_id and cid in room.players:
                        await self._safe_send(
                            room.players[cid].websocket,
                            {
                                "event": "ERROR",
                                "code": "OPPONENT_DISCONNECTED",
                                "message": "동료가 연결을 끊어 레이드가 종료되었습니다.",
                                "action_required": "GO_TO_HOME",
                            },
                        )
                self._close(room, game)
            elif room.joined_count == 0:
                self._close(room, game)

    def _close(self, room: Room, game: Optional[RaidGame]) -> None:
        if game is not None:
            game.finalized = True
        self.games.pop(room.room_code, None)
        self.rooms.close(room)

    # ------------------------------------------------------------------
    # 발송 헬퍼
    # ------------------------------------------------------------------
    async def _broadcast(self, room: Room, game: RaidGame, payload: dict) -> None:
        for cid in game.slot_of:
            if cid in room.players:
                await self._safe_send(room.players[cid].websocket, payload)

    @staticmethod
    def _err(message: str) -> dict:
        return {
            "event": "ERROR",
            "code": "SERVER_ERROR",
            "message": message,
            "action_required": "GO_TO_HOME",
        }

    @staticmethod
    def _ai_failure() -> dict:
        return {
            "event": "ERROR",
            "code": "AI_CALL_FAILED",
            "message": "AI 모델 호출에 실패해 레이드를 종료합니다. 다시 시도해 주세요.",
            "action_required": "GO_TO_HOME",
        }

    @staticmethod
    async def _safe_send(websocket, payload: dict) -> None:
        if websocket is None:
            return
        try:
            await websocket.send_json(payload)
        except Exception:  # noqa: BLE001 - 끊긴 소켓 전송 실패는 무시
            pass
