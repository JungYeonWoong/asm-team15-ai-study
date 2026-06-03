"""세션 확인 라우터."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from .schemas import MeResponse

router = APIRouter(prefix="/api", tags=["session"])


@router.get("/me", response_model=MeResponse)
def get_me(x_client_id: Optional[str] = Header(default=None)):
    """1. 세션 확인 — X-Client-ID 로 세션 상태 확인.

    소셜 로그인 구현 전 MVP 단계에서는 프론트엔드가 생성한 UUID 를
    세션 식별자로 사용한다.
    """
    if not x_client_id:
        raise HTTPException(status_code=400, detail="X-Client-ID 헤더가 필요합니다.")
    return MeResponse(client_id=x_client_id, status="active")
