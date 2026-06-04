"""인증 라우터.

- POST /api/auth/dev-login         : 개발용 즉시 로그인
- POST /api/auth/login             : 닉네임 로그인
- POST /api/auth/logout            : 토큰 폐기 (Authorization Bearer)
- POST /api/auth/social/{provider} : OAuth stub (v1.1 예정)
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request

from .providers import AuthError
from .schemas import DevLoginRequest, LoginRequest, LoginResponse, LogoutResponse
from .service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


@router.post("/dev-login", response_model=LoginResponse)
async def dev_login(
    payload: Optional[DevLoginRequest] = None,
    service: AuthService = Depends(get_auth_service),
):
    """개발용 즉시 로그인. 닉네임이 없으면 자동 부여."""
    body = payload.model_dump() if payload else {}
    try:
        token, user = await service.login("dev", body)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LoginResponse(
        token=token,
        user_id=user.user_id,
        nickname=user.nickname,
        provider=user.provider,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
):
    """닉네임 로그인. 동일 닉네임은 동일 user_id 로 매핑된다."""
    try:
        token, user = await service.login("nickname", payload.model_dump())
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LoginResponse(
        token=token,
        user_id=user.user_id,
        nickname=user.nickname,
        provider=user.provider,
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    authorization: Optional[str] = Header(default=None),
    service: AuthService = Depends(get_auth_service),
):
    """현재 Bearer 토큰을 폐기한다. 토큰이 없거나 만료여도 성공으로 응답."""
    token = _bearer_token(authorization)
    if token:
        await service.logout(token)
    return LogoutResponse()


@router.post("/social/{provider}", response_model=LoginResponse)
async def social_login(
    provider: str = Path(..., description="google | kakao | ..."),
    service: AuthService = Depends(get_auth_service),
):
    """소셜 로그인 stub — v1.1 에서 구현 예정."""
    raise HTTPException(
        status_code=501,
        detail=f"social provider '{provider}' is not implemented yet",
    )
