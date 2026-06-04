"""세션 토큰 저장소.

- :class:`InMemorySessionStore` : 단일 프로세스/테스트용 폴백 (TTL 지원).
- :class:`RedisSessionStore`    : redis-py 비동기 클라이언트 사용.
- :func:`build_session_store`   : Settings 를 보고 적절한 구현을 선택.

세션 값은 dict 직렬화로 보관한다 (`user_id`, `nickname`, `provider`).
"""

from __future__ import annotations

import json
import time
from typing import Optional, Protocol, runtime_checkable


SessionData = dict


@runtime_checkable
class SessionStore(Protocol):
    backend: str

    async def set(self, token: str, data: SessionData, ttl_seconds: int) -> None: ...
    async def get(self, token: str) -> Optional[SessionData]: ...
    async def delete(self, token: str) -> None: ...
    async def ping(self) -> bool: ...


class InMemorySessionStore:
    """프로세스 내 dict 기반 저장소. TTL 만료를 lazy 하게 체크한다."""

    backend = "memory"
    _CLEANUP_INTERVAL = 100  # set() 호출 N회마다 만료 항목 일괄 제거

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, SessionData]] = {}
        self._set_count: int = 0

    def _cleanup(self) -> None:
        now = time.monotonic()
        expired = [t for t, (exp, _) in self._data.items() if now >= exp]
        for t in expired:
            del self._data[t]

    async def set(self, token: str, data: SessionData, ttl_seconds: int) -> None:
        expires_at = time.monotonic() + max(1, ttl_seconds)
        self._data[token] = (expires_at, dict(data))
        self._set_count += 1
        if self._set_count >= self._CLEANUP_INTERVAL:
            self._cleanup()
            self._set_count = 0

    async def get(self, token: str) -> Optional[SessionData]:
        item = self._data.get(token)
        if item is None:
            return None
        expires_at, data = item
        if time.monotonic() >= expires_at:
            self._data.pop(token, None)
            return None
        return dict(data)

    async def delete(self, token: str) -> None:
        self._data.pop(token, None)

    async def ping(self) -> bool:
        return True


class RedisSessionStore:
    """redis-py 비동기 클라이언트로 토큰을 저장한다.

    토큰 키는 ``session:<token>``, 값은 JSON 문자열. TTL 은 SET EX 로 적용한다.
    Redis 연결 자체는 lazy. 테스트에서는 ``fakeredis.aioredis.FakeRedis`` 를
    주입할 수 있도록 ``client`` 인자를 허용한다.
    """

    backend = "redis"
    PREFIX = "session:"

    def __init__(self, url: str = "", *, client=None) -> None:
        self._url = url
        self._client = client

    def _ensure_client(self):
        if self._client is None:
            import redis.asyncio as redis_async  # local import to keep optional

            self._client = redis_async.from_url(
                self._url, decode_responses=True
            )
        return self._client

    async def set(self, token: str, data: SessionData, ttl_seconds: int) -> None:
        client = self._ensure_client()
        await client.set(
            self.PREFIX + token, json.dumps(data), ex=max(1, ttl_seconds)
        )

    async def get(self, token: str) -> Optional[SessionData]:
        client = self._ensure_client()
        raw = await client.get(self.PREFIX + token)
        if raw is None:
            return None
        return json.loads(raw)

    async def delete(self, token: str) -> None:
        client = self._ensure_client()
        await client.delete(self.PREFIX + token)

    async def ping(self) -> bool:
        try:
            client = self._ensure_client()
            return bool(await client.ping())
        except Exception:  # noqa: BLE001 - 헬스체크는 실패시 False
            return False


def build_session_store(redis_url: str) -> SessionStore:
    """설정에 따라 적절한 SessionStore 를 만든다."""
    if redis_url:
        return RedisSessionStore(redis_url)
    return InMemorySessionStore()
