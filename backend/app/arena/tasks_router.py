"""과제 목록 노출 라우터.

GET /api/tasks — 과제 풀 메타데이터를 반환한다. 정답 데이터는 포함하지 않는다.
DB가 연결된 경우 TaskRepository에서, 아닌 경우 하드코딩 풀에서 반환한다.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Request
from pydantic import BaseModel

from .tasks import list_tasks_public

router = APIRouter(prefix="/api", tags=["tasks"])


class TaskInfo(BaseModel):
    id: str
    description: str
    model: str
    total_count: int


@router.get("/tasks", response_model=List[TaskInfo])
def get_tasks(request: Request):
    """과제 풀 메타데이터 (정답 비공개)."""
    task_repo = getattr(request.app.state, "task_repo", None)
    if task_repo is not None:
        return task_repo.list_public()
    return list_tasks_public()
