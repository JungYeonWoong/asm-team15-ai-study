"""공용 의존성.

- :func:`get_server`         : GameServer 접근
- :func:`get_auth_service`   : AuthService 접근
- :func:`get_history_store`  : 결과 기록 저장소
- :func:`get_current_user`   : Authorization Bearer 우선, X-Client-ID 폴백
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from fastapi import Header, HTTPException, Request

if TYPE_CHECKING:
    from app.arena.game import GameServer
    from app.auth.service import AuthService
    from app.history.store import HistoryStore


def get_server(request: Request) -> "GameServer":
    return request.app.state.server


def get_auth_service(request: Request) -> "AuthService":
    return request.app.state.auth_service


def get_history_store(request: Request) -> "HistoryStore":
    return request.app.state.history_store


@dataclass(frozen=True)
class CurrentUser:
    """현재 요청자를 표현하는 경량 dataclass.

    - Bearer 토큰으로 인증된 사용자: ``user_id`` 는 안정적인 식별자.
    - X-Client-ID 폴백: ``user_id`` 가 곧 client UUID.
    """

    user_id: str
    nickname: Optional[str]
    provider: str  # "dev" | "nickname" | "social:*" | "client-id"


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_client_id: Optional[str] = Header(default=None),
) -> CurrentUser:
    """현재 사용자 의존성.

    우선순위:
      1) ``Authorization: Bearer <token>`` 으로 세션 조회
      2) ``X-Client-ID`` UUID 폴백 (MVP 호환)

    둘 다 없거나, Bearer 토큰이 만료/무효이고 X-Client-ID 도 없으면 401.
    """
    token = _bearer_token(authorization)
    if token:
        service = get_auth_service(request)
        user = await service.resolve(token)
        if user is not None:
            return CurrentUser(
                user_id=user.user_id,
                nickname=user.nickname,
                provider=user.provider,
            )
        # Bearer 토큰이 제시됐지만 무효 — X-Client-ID 폴백 없이 즉시 거부
        raise HTTPException(
            status_code=401, detail="세션 토큰이 만료되었거나 유효하지 않습니다."
        )

    if x_client_id:
        return CurrentUser(
            user_id=x_client_id, nickname=None, provider="client-id"
        )

    raise HTTPException(
        status_code=400,
        detail="Authorization Bearer 또는 X-Client-ID 헤더가 필요합니다.",
    )
