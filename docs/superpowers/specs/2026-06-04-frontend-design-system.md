# Prompt Arena — Frontend 디자인 시스템 Spec

**날짜:** 2026-06-04  
**작성자:** 이정현  
**대상 브랜치:** `feat/hyeon/frontend`  
**범위:** 색상·폰트·이모지·컴포넌트 레이아웃

---

## 1. 디자인 방향

친근한 교육 앱 느낌. 파스텔 베이스 + 오렌지 포인트. 이모지는 최소화.

---

## 2. 색상 팔레트

| 역할 | 색상 | HEX |
|------|------|-----|
| 배경 | 따뜻한 크림 | `#FFFBF0` |
| 메인 텍스트 | 부드러운 검정 | `#2D2D2D` |
| 포인트 (버튼·강조) | 오렌지 | `#FF8C00` |
| 포인트 연 (hover) | 연오렌지 | `#FFB347` |
| 승리 | 그린 | `#4CAF50` (Streamlit 기본 유지) |
| 패배 | 레드 | `#F44336` (Streamlit 기본 유지) |
| 무승부 | 오렌지 | `#FF8C00` (포인트 색과 통일) |

---

## 3. 타이포그래피

| 용도 | 폰트 | 굵기 |
|------|------|------|
| 본문 | Noto Sans KR | 400 |
| 제목 (h1~h3) | Noto Sans KR | 700 |
| 방코드 | monospace (기본 유지) | - |

구글 폰트 로딩:
```
https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap
```

---

## 4. CSS 적용 범위

`frontend/style.py`에서 전역 inject. `app.py` 최상단에서 1회 호출.

### 적용 항목

```css
/* 폰트 로드 */
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');

/* 배경 + 폰트 */
html, body, [data-testid="stAppViewContainer"] {
    background-color: #FFFBF0;
    font-family: 'Noto Sans KR', sans-serif;
}
[data-testid="stMain"] {
    background-color: #FFFBF0;
}

/* 제목 */
h1, h2, h3 {
    font-family: 'Noto Sans KR', sans-serif;
    font-weight: 700;
    color: #2D2D2D;
}

/* Primary 버튼 → 오렌지 */
[data-testid="stBaseButton-primary"] {
    background-color: #FF8C00 !important;
    border: none !important;
    color: white !important;
}
[data-testid="stBaseButton-primary"]:hover {
    background-color: #FFB347 !important;
}

/* Secondary 버튼 → 오렌지 테두리 */
[data-testid="stBaseButton-secondary"] {
    border: 1.5px solid #FF8C00 !important;
    color: #FF8C00 !important;
}

/* metric 라벨 */
[data-testid="stMetricLabel"] {
    color: #FF8C00;
    font-weight: 700;
}
```

### 건드리지 않는 항목

- `st.info()` / `st.success()` / `st.error()` / `st.warning()` 박스 색상
- 레이아웃, 컬럼, divider
- 모든 화면 로직

---

## 5. 이모지 조정

WIN 결과만 🏆 유지. 나머지 제거.

| 위치 | 현재 | 변경 후 |
|------|------|---------|
| 홈 타이틀 | `⚔️ Prompt Arena` | `Prompt Arena` |
| 대기 타이틀 | `⏳ 대기 중` | `대기 중` |
| 라운드 타이틀 | `✍️ 프롬프트 대전` | `프롬프트 대전` |
| 제출 완료 메시지 | `✅ 제출 완료!` | `제출 완료!` |
| 결과 WIN | `🏆 승리!` | `🏆 승리!` (유지) |
| 결과 LOSE | `💀 패배...` | `패배` |
| 결과 DRAW | `🤝 무승부` | `무승부` |
| 다시 하기 버튼 | `🔄 다시 하기` | `다시 하기` |
| 제출 버튼 | `📤 제출` | `제출` |
| 대전 포기 버튼 | `❌ 대전 포기` | `대전 포기` |
| 취소 버튼 | `❌ 취소` | `취소` |
| 결과 비교 소제목 | `📊 결과 비교` | `결과 비교` |
| 부전승 메시지 | `🏆 상대방 연결 끊김 — 부전승!` | `상대방 연결 끊김 — 부전승` |
| AI 실패 메시지 | `⚠️ AI 호출 실패 — 라운드 무효` | `AI 호출 실패 — 라운드 무효` |

---

## 6. 컴포넌트 레이아웃

### 카드 컴포넌트

`st.container(border=True)` 사용. CSS로 모서리·그림자·테두리 색 보정.

```css
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px !important;
    border-color: #FFE0B2 !important;
    box-shadow: 0 2px 8px rgba(255, 140, 0, 0.08) !important;
    padding: 4px !important;
}
```

### 홈 화면

```
Prompt Arena              ← h1, 중앙 정렬
프롬프트로 승부하라         ← caption

[카드: 새 방]  [카드: 방 참여]   ← st.columns(2)
 설명 텍스트    설명 텍스트
 [새 방 만들기] 코드 입력 [  ]
               [입장]
```

두 카드 높이 동일하게 맞춤. 버튼 `use_container_width=True`.

### 대기 화면

```
대기 중                    ← h1

[카드]
  방 코드                  ← st.write("방 코드")
  ┌─────────┐
  │  1234   │              ← st.code(), 크게
  └─────────┘
  상대방에게 이 코드를 알려주세요 ← st.caption

상대방을 기다리는 중입니다... ← st.info
[취소]                      ← secondary 버튼, full width
```

### 라운드 화면

```
프롬프트 대전               ← h1

[카드: 과제]
  과제: {task}             ← st.info 내부
  모델: {model}            ← st.caption

남은 시간   02:45           ← st.metric (라벨 오렌지)

[카드: 프롬프트 작성]
  ┌──────────────────────┐
  │ 텍스트 입력 (h=220)  │  ← st.text_area
  └──────────────────────┘
  글자수: 0 / 1200         ← st.caption, 우측 정렬 (columns 활용)
  [제출]                   ← primary, full width

⚙️ 기타 (expander)
  [대전 포기]              ← secondary
```

### 결과 화면

```
🏆 승리! / 패배 / 무승부   ← st.success/error/warning

결과 비교                  ← st.subheader

[카드: 나]     [카드: 상대]  ← st.columns(2)
 내 프롬프트   상대 프롬프트
 AI 응답       AI 응답
 정답: 8/10    정답: 7/10
 점수: 0.9200  점수: 0.8500

[다시 하기]                ← primary, full width
```

---

## 7. 변경 파일

| 파일 | 변경 내용 |
|------|-----------|
| `frontend/style.py` (신규) | `apply()` — CSS 전역 inject |
| `frontend/app.py` | `style.apply()` 1줄 추가 |
| `frontend/screens/home.py` | 카드 레이아웃 + 이모지 제거 |
| `frontend/screens/waiting.py` | 카드 레이아웃 + 이모지 제거 |
| `frontend/screens/round.py` | 카드 레이아웃 + 이모지 제거 |
| `frontend/screens/result.py` | 카드 레이아웃 + 이모지 제거 |
