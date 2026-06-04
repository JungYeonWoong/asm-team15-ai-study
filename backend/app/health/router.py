"""헬스 체크 라우터.

GET /healthz — 서버/세션 스토어 상태 반환.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz(request: Request):
    """간단한 상태 점검. Redis 사용 시 ping 결과를 함께 포함."""
    store = request.app.state.session_store
    if store.backend == "redis":
        try:
            redis_status = "ok" if await store.ping() else "down"
        except Exception:  # noqa: BLE001 - ping 자체가 실패해도 헬스는 응답
            redis_status = "down"
    else:
        redis_status = "disabled"

    return {
        "status": "ok",
        "session_backend": store.backend,
        "redis": redis_status,
    }
