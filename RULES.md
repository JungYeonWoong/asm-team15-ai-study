# 프로젝트 개발 규칙

## 브랜치 전략

```
main              ← 배포 기준
feat/{name}/{feature}  ← 기능 개발
```

**참여자별 prefix:**
- 김태욱 → `feat/taewook/`
- 서다솜 → `feat/dasom/`
- 이요환 → `feat/yohwna/`
- 이정현 → `feat/hyeon/`
- 정연웅 → `feat/yeonwoong/`

PR은 반드시 코드 리뷰 후 `main` 병합.

## 커밋 메시지

```
feat: 새 기능
fix: 버그 수정
refactor: 동작 변경 없는 코드 정리
test: 테스트 추가/수정
docs: 문서만 수정
chore: 빌드/설정 변경
```

## 코드 스타일

- Python: PEP 8, type hint 필수 (함수 시그니처)
- 함수 주석은 WHY가 명확할 때만
- `from __future__ import annotations` 파일 상단 유지

## 환경 변수

- API 키, 시크릿은 `.env` 에만 저장, 절대 커밋 금지
- `.env.example` 에 키 이름(값 없이)만 기재

## Backend 규칙

- `mock` 백엔드는 개발/테스트 전용, 운영은 반드시 `upstage`
- `GameServer` 속성 직접 수정은 테스트 코드에서만 허용
- 모든 Room 상태 변경은 `room.lock` 보유 상태에서 수행

## Frontend 규칙

- Streamlit 페이지는 `frontend/pages/` 에 배치
- 백엔드 URL은 환경 변수로 관리 (`BACKEND_URL`)
- WebSocket 연결은 `frontend/ws_client.py` 에 집중
- `st.session_state` 키 이름은 snake_case, 상수로 관리

## MVP 범위 (v1.0)

포함:
- 방 코드 기반 1:1 매칭
- 프롬프트 작성 (글자수 카운터 + 타이머)
- AI 응답 결과 + 승패 판정 화면

제외 (v1.1+):
- LLM 피드백
- 랭킹/전적
- 소셜 로그인
- 토큰 정산
