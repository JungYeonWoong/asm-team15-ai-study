"""세션 기능 응답 스키마."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class MeResponse(BaseModel):
    client_id: str
    status: str = "active"
    nickname: Optional[str] = None
    provider: Optional[str] = None
