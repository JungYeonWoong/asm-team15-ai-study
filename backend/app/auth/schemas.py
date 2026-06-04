"""인증 라우터 요청/응답 스키마."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    nickname: str = Field(..., description="2~20자 닉네임")


class DevLoginRequest(BaseModel):
    nickname: Optional[str] = Field(
        None, description="없으면 dev-XXXXXX 로 자동 발급"
    )


class LoginResponse(BaseModel):
    token: str
    user_id: str
    nickname: str
    provider: str


class LogoutResponse(BaseModel):
    status: str = "ok"
