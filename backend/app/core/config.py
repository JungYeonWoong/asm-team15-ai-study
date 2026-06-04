"""애플리케이션 설정.

환경 변수로 동작을 제어하며, 테스트에서는 GameServer 인스턴스의
속성을 직접 덮어써서(예: time_limit) 짧은 타임아웃을 사용할 수 있다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    # 프롬프트 작성 제한 시간(초). 명세 기준 180초.
    time_limit: int = int(os.getenv("ARENA_TIME_LIMIT", "180"))

    # 프롬프트 최대 글자 수.
    max_prompt_length: int = int(os.getenv("ARENA_MAX_PROMPT_LENGTH", "1200"))

    # AI 모델 호출 재시도 횟수.
    ai_max_retries: int = int(os.getenv("ARENA_AI_MAX_RETRIES", "3"))

    # 사용할 AI 클라이언트 종류: "mock" | "upstage"
    ai_backend: str = os.getenv("ARENA_AI_BACKEND", "mock")

    # Upstage Solar API 설정 (ai_backend == "upstage" 일 때 사용)
    upstage_api_key: str = os.getenv("UPSTAGE_API_KEY", "")
    upstage_base_url: str = os.getenv(
        "UPSTAGE_BASE_URL", "https://api.upstage.ai/v1/solar"
    )


def get_settings() -> Settings:
    return Settings()
