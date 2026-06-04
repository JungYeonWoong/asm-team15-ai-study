"""결과 기록 조회 라우터.

GET /api/me/history?limit=20 — 본인 최근 라운드 결과 (auth 필요).
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.deps import CurrentUser, get_current_user, get_history_store

from .store import HistoryStore, record_to_dict

router = APIRouter(prefix="/api/me", tags=["history"])


class HistoryItem(BaseModel):
    user_id: str
    room_code: str
    task_id: str
    result: str
    winner_id: Optional[str]
    my_score: float
    opponent_score: float
    correct_count: int
    total_count: int
    prompt_length: int
    timestamp: float


@router.get("/history", response_model=List[HistoryItem])
def get_history(
    limit: int = Query(20, ge=1, le=50),
    user: CurrentUser = Depends(get_current_user),
    store: HistoryStore = Depends(get_history_store),
):
    """내 최근 라운드 결과."""
    records = store.list_for(user.user_id, limit=limit)
    return [record_to_dict(r) for r in records]
