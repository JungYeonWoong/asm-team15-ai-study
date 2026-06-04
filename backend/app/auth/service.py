"""AuthService — Provider 와 SessionStore 를 묶어 토큰 발급/조회를 담당."""

from __future__ import annotations

import secrets
from typing import Optional

from .providers import AuthenticatedUser, AuthError, AuthProvider
from .session_store import SessionStore


class AuthService:
    def __init__(
        self,
        store: SessionStore,
        providers: dict[str, AuthProvider],
        ttl_seconds: int,
    ) -> None:
        self.store = store
        self.providers = providers
        self.ttl_seconds = ttl_seconds

    def get_provider(self, name: str) -> AuthProvider:
        provider = self.providers.get(name)
        if provider is None:
            raise AuthError(f"unknown auth provider: {name}")
        return provider

    async def login(self, provider_name: str, payload: dict) -> tuple[str, AuthenticatedUser]:
        provider = self.get_provider(provider_name)
        user = await provider.authenticate(payload)
        token = secrets.token_urlsafe(32)
        await self.store.set(
            token,
            {
                "user_id": user.user_id,
                "nickname": user.nickname,
                "provider": user.provider,
            },
            self.ttl_seconds,
        )
        return token, user

    async def resolve(self, token: str) -> Optional[AuthenticatedUser]:
        data = await self.store.get(token)
        if data is None:
            return None
        return AuthenticatedUser(
            user_id=data["user_id"],
            nickname=data["nickname"],
            provider=data["provider"],
        )

    async def logout(self, token: str) -> None:
        await self.store.delete(token)
