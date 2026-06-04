"""인증 Provider 추상화.

- :class:`DevProvider`      : 입력 검증 없이 즉시 통과. 개발용 빠른 접속.
- :class:`NicknameProvider` : 닉네임을 정규화해 user_id 발급.
- :class:`SocialProvider`   : OAuth 흐름 stub. v1.1 확장 지점.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AuthenticatedUser:
    """인증 성공 시 반환되는 사용자 정보."""

    user_id: str
    nickname: str
    provider: str


class AuthError(ValueError):
    """인증 실패."""


class AuthProvider(Protocol):
    name: str

    async def authenticate(self, payload: dict) -> AuthenticatedUser: ...


_NICKNAME_RE = re.compile(r"^[A-Za-z0-9가-힣_\-]{2,20}$")


def _normalize_nickname(raw: str) -> str:
    return raw.strip()


def _stable_user_id(provider: str, nickname: str) -> str:
    """닉네임에서 결정론적 user_id 를 만든다 (DB 없는 MVP)."""
    digest = hashlib.sha256(f"{provider}:{nickname}".encode("utf-8")).hexdigest()
    return f"u_{digest[:16]}"


class DevProvider:
    """개발용 즉시 접속 Provider.

    닉네임을 제공하면 그대로 쓰고, 없으면 ``dev-<랜덤>`` 으로 부여한다.
    어떤 입력이든 인증을 거부하지 않는다.
    """

    name = "dev"

    async def authenticate(self, payload: dict) -> AuthenticatedUser:
        raw = (payload or {}).get("nickname") or ""
        nickname = _normalize_nickname(raw) or _dev_default_nickname()
        return AuthenticatedUser(
            user_id=_stable_user_id(self.name, nickname),
            nickname=nickname,
            provider=self.name,
        )


def _dev_default_nickname() -> str:
    import secrets
    return f"dev-{secrets.token_hex(3)}"


class NicknameProvider:
    """닉네임 기반 로그인.

    형식 검증(영문/숫자/한글/_/-, 2~20자)을 통과한 닉네임만 허용.
    동일 닉네임은 동일 user_id 로 매핑된다 (결정론적).
    """

    name = "nickname"

    async def authenticate(self, payload: dict) -> AuthenticatedUser:
        nickname = _normalize_nickname((payload or {}).get("nickname") or "")
        if not nickname:
            raise AuthError("nickname is required")
        if not _NICKNAME_RE.match(nickname):
            raise AuthError(
                "nickname must be 2-20 chars of letters/digits/Korean/_-"
            )
        return AuthenticatedUser(
            user_id=_stable_user_id(self.name, nickname),
            nickname=nickname,
            provider=self.name,
        )


class SocialProvider:
    """OAuth 소셜 로그인 stub.

    v1.0 에서는 라우트만 노출하고 항상 :class:`AuthError` 를 던진다.
    실제 구현은 v1.1 에서 provider 별 (google/kakao 등) 흐름을 채운다.
    """

    name = "social"

    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name
        self.name = f"social:{provider_name}"

    async def authenticate(self, payload: dict) -> AuthenticatedUser:
        raise AuthError(
            f"social provider '{self.provider_name}' is not implemented yet"
        )
