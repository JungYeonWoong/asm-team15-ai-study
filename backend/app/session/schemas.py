"""세션 기능 응답 스키마."""

from __future__ import annotations

from pydantic import BaseModel


class MeResponse(BaseModel):
    client_id: str
    status: str = "active"
