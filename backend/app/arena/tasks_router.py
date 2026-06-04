"""과제 목록 노출 라우터.

GET /api/tasks — 사전 정의된 과제 풀의 메타데이터를 반환한다.
정답 데이터는 응답에 포함되지 않는다.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from .tasks import list_tasks_public

router = APIRouter(prefix="/api", tags=["tasks"])


class TaskInfo(BaseModel):
    id: str
    description: str
    model: str
    total_count: int


@router.get("/tasks", response_model=List[TaskInfo])
def get_tasks():
    """과제 풀 메타데이터 (정답 비공개)."""
    return list_tasks_public()
