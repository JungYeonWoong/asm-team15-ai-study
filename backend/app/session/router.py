"""세션 확인 라우터.

세션 식별자 우선순위:
  1) Authorization: Bearer <token>   (auth 로그인으로 발급)
  2) X-Client-ID                    (MVP 호환, 프론트 발급 UUID)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUser, get_current_user

from .schemas import MeResponse

router = APIRouter(prefix="/api", tags=["session"])


@router.get("/me", response_model=MeResponse)
async def get_me(user: CurrentUser = Depends(get_current_user)):
    """현재 클라이언트의 세션 상태."""
    return MeResponse(
        client_id=user.user_id,
        status="active",
        nickname=user.nickname,
        provider=user.provider,
    )
