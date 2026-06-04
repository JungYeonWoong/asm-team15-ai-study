# 이슈: 브라우저 탭 닫기 시 부전승 미처리

**발견일:** 2026-06-04  
**발견자:** 이정현 (프론트엔드)  
**심각도:** Medium — 게임 공정성 영향

---

## 현상

라운드 진행 중 상대방이 브라우저 탭을 닫아도 부전승 처리가 즉시 되지 않음.  
수 분 후 자동 처리되거나 처리 안 됨.

## 원인

Streamlit 아키텍처 특성:

```
브라우저 ↔ Streamlit 서버 ↔ FastAPI (게임 WS)
```

브라우저 탭이 닫히면 **브라우저 ↔ Streamlit** 연결만 끊김.  
**Streamlit 서버 ↔ FastAPI** 게임 WebSocket은 Streamlit 세션이 완전히 종료될 때까지 유지됨.  
→ 백엔드 `WebSocketDisconnect` 예외가 즉시 발생하지 않아 `handle_disconnect()` 호출 안 됨.

## 현재 임시 대응

- 대기 화면: "❌ 취소" 버튼 (명시적 WS 종료)
- 라운드 화면: "❌ 대전 포기" 버튼 (명시적 WS 종료)
- 버튼 클릭 시 `ws_client.close(ws)` → 백엔드 즉시 disconnect 감지 → 상대 부전승 처리

탭 닫기로는 여전히 즉시 처리 안 됨.

## 권장 해결책 (백엔드 작업 필요)

### 방법 A: JS beforeunload + `/api/leave` 엔드포인트 (권장)

**백엔드 추가 사항:**
```python
# app/rooms/router.py 또는 별도 router
@router.post("/api/leave")
async def leave_room(
    body: LeaveRequest,
    server: GameServer = Depends(get_game_server),
):
    room = server.rooms.get(body.room_code)
    if room:
        await server.handle_disconnect(room, body.client_id)
```

**프론트엔드 추가 사항:**
```python
# round.py, waiting.py의 render() 상단
st.components.v1.html(f"""
<script>
window.addEventListener('beforeunload', function() {{
    navigator.sendBeacon('{BACKEND_URL}/api/leave',
        new Blob([JSON.stringify({{
            client_id: '{client_id}',
            room_code: '{room_code}'
        }})], {{type: 'application/json'}}));
}});
</script>
""", height=0)
```

FastAPI CORS `allow_origins=["*"]` 이미 설정되어 있어 별도 CORS 작업 불필요.

### 방법 B: 백엔드 하트비트 타임아웃

백엔드 WS 수신 루프에 타임아웃 추가. 일정 시간(예: 30초) 메시지 없으면 disconnect 처리.  
구현 복잡도 높음.

## 참고

- 관련 파일: `backend/app/arena/router.py:55` (`WebSocketDisconnect` 핸들러)
- 관련 파일: `backend/app/arena/game.py` (`handle_disconnect`)
- 프론트엔드 임시 대응: `frontend/screens/round.py`, `frontend/screens/waiting.py`
