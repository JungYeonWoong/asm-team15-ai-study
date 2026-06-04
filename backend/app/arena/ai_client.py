"""Base AI 모델 호출 추상화.

채점 흐름:
  사용자 프롬프트 + 테스트 케이스 입력 → AI 모델 → 출력 → expected 와 이진 비교

- 실제 서비스: :class:`UpstageAIClient` 가 Upstage Solar API 를 호출.
- 로컬 데모(키 없음): :class:`MockAIClient` 가 정답표 기반으로 결정론적 가짜 출력.
- 테스트: :class:`CallableAIClient` 로 출력을 완전히 통제.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Awaitable, Callable, Mapping, Protocol, runtime_checkable

from .domain import TestCase


class AICallError(RuntimeError):
    """AI 모델 호출이 재시도 끝에 실패했을 때 발생."""


@runtime_checkable
class AIClient(Protocol):
    """AI 모델 클라이언트 인터페이스."""

    async def run(self, model: str, prompt: str, test_input: str) -> str:
        """주어진 프롬프트/입력으로 모델을 1회 호출하고 출력 문자열을 반환."""
        ...


# ---------------------------------------------------------------------------
# 구현체
# ---------------------------------------------------------------------------
class MockAIClient:
    """키 없이 로컬에서 돌릴 수 있는 결정론적 더미 클라이언트.

    실제 추론 대신, (프롬프트, 입력) 해시로 정답/오답을 결정론적으로 가른다.
    ``answer_key`` (입력→정답) 가 주어지면 정답일 때 그 값을, 아니면 오답
    문자열을 반환한다. 데모/스모크 용도이며 운영에서는 UpstageAIClient 로 교체.
    """

    def __init__(
        self,
        answer_key: Mapping[str, str] | None = None,
        accuracy: float = 0.7,
    ) -> None:
        self.answer_key = dict(answer_key or {})
        self.accuracy = accuracy

    async def run(self, model: str, prompt: str, test_input: str) -> str:
        await asyncio.sleep(0)  # 비동기 인터페이스 유지
        seed = f"{prompt}|{test_input}".encode("utf-8")
        digest = int(hashlib.sha256(seed).hexdigest(), 16)
        is_correct = (digest % 100) < int(self.accuracy * 100)
        if is_correct and test_input in self.answer_key:
            return self.answer_key[test_input]
        return f"__WRONG__:{digest % 1000}"


class CallableAIClient:
    """임의의 함수를 감싸는 클라이언트. 주로 테스트에서 사용한다."""

    def __init__(
        self, fn: Callable[[str, str, str], "str | Awaitable[str]"]
    ) -> None:
        self._fn = fn

    async def run(self, model: str, prompt: str, test_input: str) -> str:
        result = self._fn(model, prompt, test_input)
        if asyncio.iscoroutine(result):
            return await result
        return result  # type: ignore[return-value]


class UpstageAIClient:
    """Upstage Solar Chat Completions API 호출 클라이언트."""

    def __init__(self, api_key: str, base_url: str) -> None:
        import httpx  # httpx는 UpstageAIClient 사용 시에만 필요
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(timeout=30.0)

    async def run(self, model: str, prompt: str, test_input: str) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": test_input},
            ],
            "temperature": 0,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        resp = await self._http.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# 재시도 + 채점
# ---------------------------------------------------------------------------
async def _call_with_retry(
    client: AIClient,
    model: str,
    prompt: str,
    test_input: str,
    max_retries: int,
) -> str:
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return await client.run(model, prompt, test_input)
        except Exception as exc:  # noqa: BLE001 - 모든 호출 오류를 재시도 대상으로
            last_exc = exc
            if attempt < max_retries - 1:
                await asyncio.sleep(min(0.5 * (2 ** attempt), 10.0))
    raise AICallError(f"AI 모델 호출 {max_retries}회 실패") from last_exc


def _normalize(text: str) -> str:
    return text.strip()


async def grade(
    client: AIClient,
    model: str,
    prompt: str,
    test_cases: tuple[TestCase, ...],
    max_retries: int = 3,
) -> tuple[int, int, str]:
    """프롬프트를 모든 테스트 케이스에 병렬 적용하고 채점한다.

    Returns: (정답 수, 전체 수 N, 대표 응답 1개)
    실패 시 :class:`AICallError` 를 전파한다.
    """
    outputs = await asyncio.gather(
        *(
            _call_with_retry(client, model, prompt, tc.input, max_retries)
            for tc in test_cases
        )
    )
    correct = sum(
        1
        for output, tc in zip(outputs, test_cases)
        if _normalize(output) == _normalize(tc.expected)
    )
    representative = outputs[0] if outputs else ""
    return correct, len(test_cases), representative
