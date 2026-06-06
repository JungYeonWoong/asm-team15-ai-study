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


# ---------------------------------------------------------------------------
# 프롬프트 평가 (LLM 이 채점 결과/출력을 본 뒤 프롬프트를 총평)
# ---------------------------------------------------------------------------
# 채점이 끝난 뒤, 같은 모델에게 "이 프롬프트가 왜 이런 출력을 냈는지"를 보여주고
# 강점/약점/개선 방향을 짧게 평가하게 한다. system 메시지로 들어간다.
PROMPT_EVAL_SYSTEM = (
    "당신은 프롬프트 엔지니어링 평가자입니다. "
    "참가자가 작성한 프롬프트와, 그 프롬프트로 생성된 실제 출력 및 기대 출력을 "
    "비교한 채점 결과가 주어집니다. 출력을 근거로 프롬프트의 강점과 약점, "
    "구체적인 개선 방향을 한국어로 3줄 이내로 평가하세요. "
    "프롬프트 자체를 대신 작성해 주지는 마세요."
)


def build_eval_input(
    prompt: str,
    test_cases: tuple[TestCase, ...],
    outputs: list[str],
) -> str:
    """평가 LLM 에 넘길 사용자 메시지를 구성한다 (프롬프트 + 케이스별 입출력)."""
    lines = [
        "=== 참가자 프롬프트 ===",
        prompt or "(빈 프롬프트)",
        "",
        "=== 채점 결과 (입력 / 기대 출력 / 실제 출력) ===",
    ]
    for i, tc in enumerate(test_cases):
        actual = outputs[i] if i < len(outputs) else ""
        verdict = "정답" if _normalize(actual) == _normalize(tc.expected) else "오답"
        lines.append(
            f"[{i + 1}] 입력={tc.input!r} 기대={tc.expected!r} "
            f"실제={actual!r} → {verdict}"
        )
    lines.append("")
    lines.append("위 출력을 근거로 이 프롬프트를 평가해 주세요.")
    return "\n".join(lines)


async def evaluate_prompt(
    client: AIClient,
    model: str,
    prompt: str,
    test_cases: tuple[TestCase, ...],
    outputs: list[str],
    *,
    max_retries: int = 2,
) -> str:
    """채점 출력을 LLM 에게 보여주고 프롬프트 총평을 받는다.

    평가는 부가 기능이므로 실패해도 라운드를 깨지 않고 빈 문자열을 반환한다.
    빈 프롬프트는 평가 대상이 아니다.
    """
    if not prompt or not prompt.strip():
        return ""
    user_content = build_eval_input(prompt, test_cases, outputs)
    try:
        result = await _call_with_retry(
            client, model, PROMPT_EVAL_SYSTEM, user_content, max_retries
        )
    except AICallError:
        return ""
    return _normalize(result)


async def grade(
    client: AIClient,
    model: str,
    prompt: str,
    test_cases: tuple[TestCase, ...],
    max_retries: int = 3,
) -> tuple[int, int, str, list[dict]]:
    """프롬프트를 모든 테스트 케이스에 병렬 적용하고 채점한다.

    Returns: (정답 수, 전체 수 N, 대표 응답 1개, 케이스별 결과 리스트)
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
    case_results = [
        {
            "index": i + 1,
            "actual": out,
            "is_correct": _normalize(out) == _normalize(tc.expected),
        }
        for i, (tc, out) in enumerate(zip(test_cases, outputs))
    ]
    return correct, len(test_cases), representative, case_results
