"""실제 Upstage Solar API 를 1회 호출하는 통합 테스트.

`RUN_INTEGRATION=1` 환경 변수가 없으면 skip.
`UPSTAGE_API_KEY` 가 없어도 skip.
비용 절감을 위해 단 1회만 호출한다.
"""

from __future__ import annotations

import os

import pytest

from app.arena.ai_client import UpstageAIClient

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_upstage_solar_smoke():
    if not os.getenv("RUN_INTEGRATION"):
        pytest.skip("set RUN_INTEGRATION=1 to enable")
    api_key = os.getenv("UPSTAGE_API_KEY", "")
    if not api_key:
        pytest.skip("UPSTAGE_API_KEY not set")

    client = UpstageAIClient(
        api_key,
        os.getenv("UPSTAGE_BASE_URL", "https://api.upstage.ai/v1/solar"),
    )
    output = await client.run(
        model=os.getenv("UPSTAGE_MODEL", "solar-pro3"),
        prompt="Echo back the user's exact input.",
        test_input="hello",
    )
    assert isinstance(output, str)
    assert output  # 비어있지 않아야 한다
