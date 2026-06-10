"""협동 보스 레이드 모드 (LangGraph 기반 마스터 디렉터).

- state.py  : 그래프 상태(BossRaidState) + 튜닝 상수
- nodes.py  : 그래프 노드 (입력·실행 / 채점 / 보스 크리틱 / 종료 판정)
- graph.py  : 컴파일된 StateGraph (보스 크리틱 조건부 엣지)
- server.py : RaidServer — WebSocket 라운드 루프 + 그래프 호출
- router.py : WS /ws/raid/{room_code}
"""
