# -*- coding: utf-8 -*-
"""
PROMPT ARENA — 협동 보스 레이드 · Streamlit 프론트엔드
15조 불꽃청년 · FastAPI/WebSocket(LangGraph 디렉터) 백엔드 연동본

실행:
  1) 백엔드 먼저 실행  (backend/)  →  python run.py   (http://localhost:8000)
  2) streamlit run app.py

  - REST : POST /api/rooms , GET /api/rooms/{code} , GET /api/me , GET /api/me/history , GET /api/tasks
  - WS   : /ws/raid/{code}?client_id={uuid}
           (JOIN / SUBMIT  ↔  RAID_START / ROUND_START / TEAMMATE_SUBMITTED /
            SUBMIT_REJECTED / ROUND_TIMEOUT / ROUND_RESULT / RAID_END / WAITING / ERROR)
  - 신원 : MVP 호환 X-Client-ID(프론트 생성 UUID) 헤더 사용
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
import uuid

import requests
import streamlit as st
import websocket  # websocket-client

try:
    from streamlit_autorefresh import st_autorefresh
    _HAS_AUTOREFRESH = True
except Exception:  # 폴백: 패키지가 없으면 sleep+rerun 으로 폴링
    _HAS_AUTOREFRESH = False

DEFAULT_BASE = os.environ.get("ARENA_BASE_URL", "http://localhost:8000")
MAX_LEN = 1200
TIME_LIMIT = 180

st.set_page_config(page_title="Prompt Arena · 프롬프트 대전", page_icon="⚔️", layout="centered")


# =====================================================================
# WebSocket 연결 (백그라운드 스레드가 수신 → 큐, 메인 스크립트가 폴링)
# =====================================================================
class WSConn:
    def __init__(self, url: str):
        self.url = url
        self.q: "queue.Queue[dict]" = queue.Queue()
        self.ws = None
        self.alive = False
        self.err = None

    def start(self):
        # 연결(핸드셰이크)에만 타임아웃을 적용한다.
        self.ws = websocket.create_connection(self.url, timeout=8)
        # 연결 후에는 recv 가 무한정 대기하도록 한다.
        # (라운드 진행 중 서버가 한동안 메시지를 안 보내도 끊기지 않게)
        try:
            self.ws.settimeout(None)
        except Exception:
            pass
        self.alive = True
        threading.Thread(target=self._recv_loop, daemon=True).start()
        self.send({"action": "JOIN"})

    def _recv_loop(self):
        while self.alive:
            try:
                raw = self.ws.recv()
            except websocket.WebSocketTimeoutException:
                # 일시적 수신 타임아웃은 무시하고 계속 듣는다 (연결 유지)
                continue
            except Exception as e:  # 소켓 종료/오류
                self.q.put({"event": "_CLOSED", "detail": str(e)})
                self.alive = False
                break
            if not raw:
                continue
            try:
                self.q.put(json.loads(raw))
            except Exception:
                pass

    def send(self, obj: dict):
        try:
            self.ws.send(json.dumps(obj))
        except Exception as e:
            self.err = str(e)

    def drain(self) -> list[dict]:
        out = []
        while True:
            try:
                out.append(self.q.get_nowait())
            except queue.Empty:
                break
        return out

    def close(self):
        self.alive = False
        try:
            self.ws.close()
        except Exception:
            pass


# =====================================================================
# 세션 상태 초기화
# =====================================================================
def init_state():
    ss = st.session_state
    ss.setdefault("base", DEFAULT_BASE)
    ss.setdefault("client_id", str(uuid.uuid4()))
    ss.setdefault("nick", "")
    ss.setdefault("screen", "login")        # login | lobby | arena
    ss.setdefault("phase", "idle")          # waiting | round | scoring | round_result | raid_end | error
    ss.setdefault("room_code", "")
    ss.setdefault("is_host", False)
    ss.setdefault("conn", None)
    ss.setdefault("joined", False)
    ss.setdefault("round", None)            # {round, task, model, time_limit, difficulty, char_limit, status_effect, hint, boss_hp}
    ss.setdefault("round_start_ts", 0.0)
    ss.setdefault("raid", None)             # {boss_hp, boss_max_hp, max_rounds}
    ss.setdefault("my_slot", "p1")
    ss.setdefault("teammate_submitted", False)
    ss.setdefault("submit_rejected", None)
    ss.setdefault("round_result", None)     # 직전 라운드 ROUND_RESULT 페이로드
    ss.setdefault("raid_end", None)         # RAID_END 페이로드
    ss.setdefault("next_round_ready", False)
    ss.setdefault("pending_end", False)
    ss.setdefault("error", None)
    ss.setdefault("record", {"win": 0, "lose": 0, "draw": 0})


init_state()


def ws_base() -> str:
    return st.session_state.base.replace("https://", "wss://").replace("http://", "ws://")


def headers() -> dict:
    return {"X-Client-ID": st.session_state.client_id}


def api_post(path: str):
    return requests.post(st.session_state.base + path, headers=headers(), timeout=8)


def api_get(path: str):
    return requests.get(st.session_state.base + path, headers=headers(), timeout=8)


def fetch_record():
    """GET /api/me/history 로 실제 전적을 집계한다 (X-Client-ID 로도 동작)."""
    try:
        r = api_get("/api/me/history?limit=50")
        if r.status_code == 200:
            rec = {"win": 0, "lose": 0, "draw": 0}
            for item in r.json():
                key = item.get("result", "").lower()
                if key in rec:
                    rec[key] += 1
            st.session_state.record = rec
    except Exception:
        pass


def live_refresh(ms: int, key: str):
    """라이브 화면 폴링. 패키지가 있으면 부드럽게, 없으면 sleep+rerun 폴백."""
    if _HAS_AUTOREFRESH:
        st_autorefresh(interval=ms, key=key)
    else:
        time.sleep(ms / 1000)
        st.rerun()


def reset_to_lobby():
    ss = st.session_state
    if ss.conn:
        ss.conn.close()
        # 서버가 WebSocket 끊김을 처리하고 방 멤버십을 제거할 시간을 준다
        time.sleep(0.7)
    ss.conn = None
    ss.joined = False
    ss.phase = "idle"
    ss.room_code = ""
    ss.is_host = False
    ss.round = None
    ss.raid = None
    ss.round_result = None
    ss.raid_end = None
    ss.next_round_ready = False
    ss.pending_end = False
    ss.teammate_submitted = False
    ss.submit_rejected = None
    ss.error = None
    ss.pop("editor", None)
    ss.pop("submitted_once", None)
    ss.screen = "lobby"


# =====================================================================
# 스타일 — 프로토타입과 동일한 키치/담백 아케이드 룩
# =====================================================================
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Black+Han+Sans&family=Gowun+Dodum&family=Jua&family=Space+Mono:wght@400;700&display=swap');

:root{
  --paper:#fbf3e2; --paper-2:#f4e8cf; --ink:#171513;
  --tomato:#ff5436; --tomato-dark:#e23c20; --gold:#ffc23c;
  --mint:#37cfa0; --mint-dark:#1fae84; --sky:#6aa9ff;
  --shadow:6px 6px 0 var(--ink); --shadow-sm:3px 3px 0 var(--ink);
  --shadow-lg:9px 9px 0 var(--ink); --bd:3px solid var(--ink);
}
/* 전체 배경: 크림 종이 + 점 그리드 */
.stApp{
  background-color:var(--paper);
  background-image:radial-gradient(var(--paper-2) 1.4px, transparent 1.4px);
  background-size:22px 22px;
}
/* 기본 streamlit 군더더기 정리 */
#MainMenu, header[data-testid="stHeader"], footer{visibility:hidden;}
.block-container{padding-top:1.6rem; padding-bottom:5rem; max-width:860px;}
html, body, [class*="css"]{font-family:'Gowun Dodum', system-ui, sans-serif; color:var(--ink);}

/* 공통 카드/뱃지 */
.pa-card{background:#fff;border:var(--bd);border-radius:20px;
  box-shadow:var(--shadow), inset 0 2px 0 rgba(255,255,255,.7);
  padding:26px 28px;margin-bottom:18px;}
.pa-tag{display:inline-block;font-family:'Jua';font-size:12px;padding:5px 13px;border:2.5px solid var(--ink);
  border-radius:30px;background:var(--gold);transform:rotate(-2deg);box-shadow:2px 2px 0 var(--ink);
  transition:transform .12s;}
.pa-tag:hover{transform:rotate(-2deg) translateY(-1px) scale(1.04);}
.pa-tag.mint{background:var(--mint);} .pa-tag.sky{background:var(--sky);color:#fff;}
.pa-tag.tomato{background:var(--tomato);color:#fff;}

/* 상단바 */
.pa-top{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px;flex-wrap:wrap;}
.pa-brand{display:flex;align-items:center;gap:11px;}
.pa-mark{width:42px;height:42px;border:var(--bd);background:var(--tomato);border-radius:11px;display:grid;place-items:center;
  box-shadow:var(--shadow-sm);transform:rotate(-4deg);font-family:'Black Han Sans';color:var(--paper);font-size:24px;line-height:1;}
.pa-brand h1{font-family:'Black Han Sans';font-size:24px;letter-spacing:.5px;line-height:1;margin:0;}
.pa-brand small{display:block;font-size:11px;color:#8a7e6b;font-family:'Space Mono';margin-top:1px;letter-spacing:1px;}
.pa-purse{display:flex;align-items:center;gap:8px;border:var(--bd);background:#fff;padding:6px 14px 6px 8px;border-radius:40px;
  box-shadow:var(--shadow-sm);font-family:'Space Mono';font-weight:700;}
.pa-coin{width:24px;height:24px;border-radius:50%;background:var(--gold);border:2.5px solid var(--ink);display:grid;place-items:center;
  font-family:'Jua';font-size:13px;color:var(--ink);}

/* 큰 타이틀/히어로 */
.pa-hero{text-align:center;padding:14px 0 2px;}
.pa-big{font-family:'Black Han Sans';font-size:clamp(40px,9vw,80px);line-height:.95;letter-spacing:1px;}
.pa-big .red{color:var(--tomato);display:inline-block;transform:rotate(-3deg);}
.pa-big .vs{display:inline-grid;place-items:center;width:1.05em;height:1.05em;background:var(--ink);color:var(--gold);
  border-radius:14px;transform:rotate(6deg) scale(.78);box-shadow:var(--shadow-sm);margin:0 .04em;vertical-align:middle;}
.pa-sub{font-size:17px;color:#5b5346;line-height:1.6;margin-top:14px;text-align:center;}

/* 라운드 브리핑 칩 */
.pa-chips{display:flex;gap:12px;flex-wrap:wrap;justify-content:center;margin:6px 0 4px;}
.pa-chip{border:2.5px solid var(--ink);border-radius:14px;padding:12px 18px;text-align:center;box-shadow:var(--shadow-sm);background:#fff;min-width:120px;}
.pa-chip .ic{font-size:24px;}
.pa-chip .lb{font-size:10px;color:#8a7e6b;font-family:'Space Mono';margin-top:5px;letter-spacing:1px;}
.pa-chip .vl{font-family:'Jua';font-size:17px;margin-top:2px;}

/* 과제 박스 */
.pa-task{border:var(--bd);border-radius:14px;background:var(--paper);padding:16px 18px;box-shadow:inset 3px 3px 0 rgba(0,0,0,.05);}
.pa-task h4{font-family:'Jua';font-size:16px;margin:0 0 8px;}
.pa-task p{line-height:1.7;margin:0;}

/* 타이머/매칭 */
.pa-center{text-align:center;}
.pa-vsbubble{font-family:'Black Han Sans';font-size:34px;color:var(--tomato);transform:rotate(-8deg);}
.pa-fighter{display:inline-block;width:110px;text-align:center;vertical-align:middle;}
.pa-avatar{width:78px;height:78px;border:var(--bd);border-radius:18px;margin:0 auto 8px;display:grid;place-items:center;
  font-size:38px;box-shadow:var(--shadow-sm);background:var(--paper);}
.pa-avatar.me{background:var(--mint);} .pa-avatar.foe{background:var(--paper-2);}
.pa-roomcode{font-family:'Space Mono';font-weight:700;font-size:46px;letter-spacing:10px;border:var(--bd);background:var(--ink);
  color:var(--gold);padding:10px 8px 10px 18px;border-radius:14px;display:inline-block;box-shadow:var(--shadow);}

/* 채점 로더 */
.pa-spin{width:64px;height:64px;margin:6px auto 16px;border:6px solid var(--paper-2);border-top-color:var(--tomato);
  border-right-color:var(--gold);border-radius:50%;animation:pa-spin .9s linear infinite;}
@keyframes pa-spin{to{transform:rotate(360deg);}}

/* 결과 비교 패널 */
.pa-panel{border:var(--bd);border-radius:16px;box-shadow:var(--shadow);overflow:hidden;background:#fff;margin-bottom:14px;}
.pa-ph{padding:11px 15px;display:flex;align-items:center;justify-content:space-between;border-bottom:var(--bd);font-family:'Jua';}
.pa-panel.me .pa-ph{background:var(--mint);} .pa-panel.foe .pa-ph{background:var(--paper-2);}
.pa-acc{font-family:'Space Mono';font-weight:700;font-size:13px;background:#fff;border:2.5px solid var(--ink);border-radius:20px;padding:2px 10px;}
.pa-pbody{padding:14px 15px;}
.pa-lbl{font-family:'Space Mono';font-size:11px;color:#9a8f7c;letter-spacing:1px;margin:0 0 5px;}
.pa-quote{background:var(--paper);border:2px dashed #cdbfa6;border-radius:11px;padding:10px 12px;font-size:14px;line-height:1.6;
  max-height:150px;overflow:auto;white-space:pre-wrap;}
.pa-cases{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px;}
.pa-cse{width:30px;height:30px;border:2.5px solid var(--ink);border-radius:8px;display:grid;place-items:center;font-family:'Jua';font-size:14px;}
.pa-cse.ok{background:var(--mint);} .pa-cse.no{background:#ffd9d1;color:var(--tomato-dark);}

/* 판정 배너 */
.pa-banner{font-family:'Black Han Sans';font-size:clamp(48px,12vw,104px);line-height:.9;letter-spacing:2px;
  -webkit-text-stroke:3px var(--ink);display:inline-block;transform:rotate(-3deg);margin:4px 0;}
.pa-banner.win{color:var(--mint);} .pa-banner.lose{color:#cdbfa6;} .pa-banner.draw{color:var(--gold);}
.pa-sbcard{border:var(--bd);border-radius:16px;padding:16px;box-shadow:var(--shadow);background:#fff;}
.pa-sbcard.win{background:var(--mint);}
.pa-total{font-family:'Black Han Sans';font-size:42px;line-height:1;}
.pa-total small{font-size:15px;color:#5b5346;font-family:'Space Mono';}
.pa-formula{margin-top:10px;font-family:'Space Mono';font-size:12px;line-height:1.9;border-top:2.5px dashed rgba(0,0,0,.25);padding-top:8px;}
.pa-formula .r{display:flex;justify-content:space-between;}
.pa-feedback{border:var(--bd);border-radius:16px;background:#fff;box-shadow:var(--shadow);padding:16px 18px;}
.pa-fb{display:flex;gap:10px;margin-bottom:8px;line-height:1.55;font-size:14px;align-items:flex-start;}
.pa-pin{flex:0 0 auto;width:22px;height:22px;border:2.5px solid var(--ink);border-radius:6px;display:grid;place-items:center;font-size:12px;font-family:'Jua';}
.pa-pin.good{background:var(--mint);} .pa-pin.bad{background:var(--gold);}
.pa-flag{display:inline-block;font-size:10px;font-family:'Space Mono';border:2px solid #cdbfa6;color:#9a8f7c;border-radius:20px;padding:2px 8px;margin-left:6px;}

.pa-foot{text-align:center;margin-top:30px;font-family:'Space Mono';font-size:11px;color:#b4a892;letter-spacing:1px;}
.pa-hint{font-size:12.5px;color:#8a7e6b;}

/* ---- Streamlit 위젯을 키치 버튼/입력으로 ---- */
.stButton > button{
  font-family:'Jua'!important;font-size:17px!important;border:var(--bd)!important;background:var(--gold)!important;color:var(--ink)!important;
  border-radius:14px!important;box-shadow:var(--shadow)!important;padding:11px 22px!important;transition:.07s!important;width:100%;
}
.stButton > button:hover{transform:translate(-1px,-1px);box-shadow:var(--shadow-lg)!important;}
.stButton > button:active{transform:translate(4px,4px);box-shadow:1px 1px 0 var(--ink)!important;}
.stButton > button[kind="primary"]{background:var(--tomato)!important;color:#fff!important;font-size:19px!important;}
div[data-testid="stTextArea"] textarea{
  border:var(--bd)!important;border-radius:16px!important;background:#fff!important;box-shadow:var(--shadow)!important;
  font-family:'Gowun Dodum'!important;font-size:16px!important;line-height:1.7!important;padding:16px!important;
}
div[data-testid="stTextInput"] input{
  border:var(--bd)!important;border-radius:13px!important;background:var(--paper)!important;font-family:'Space Mono'!important;
  font-weight:700!important;font-size:20px!important;letter-spacing:4px!important;text-align:center!important;padding:13px!important;
  box-shadow:inset 3px 3px 0 rgba(0,0,0,.07)!important;
}
div[data-testid="stTextInput"] input:focus, div[data-testid="stTextArea"] textarea:focus{outline:none!important;}

/* ---- 마감 디테일 (조금 더 polished) ---- */
@keyframes pa-rise{from{opacity:0;transform:translateY(12px) scale(.99)}to{opacity:1;transform:none}}
@keyframes pa-pop{0%{opacity:0;transform:rotate(-3deg) scale(.6)}60%{transform:rotate(-3deg) scale(1.08)}100%{opacity:1;transform:rotate(-3deg) scale(1)}}
@keyframes pa-float{0%,100%{transform:translateY(0)}50%{transform:translateY(-3px)}}
.pa-card, .pa-panel, .pa-sbcard, .pa-feedback{animation:pa-rise .42s cubic-bezier(.2,1,.3,1) both;}
.pa-card{transition:transform .14s, box-shadow .14s;}
.pa-card:hover{transform:translate(-1px,-2px);box-shadow:var(--shadow-lg);}
.pa-banner{animation:pa-pop .55s cubic-bezier(.2,1.5,.4,1) both;}
.pa-total{font-variant-numeric:tabular-nums;letter-spacing:-1px;}
.pa-roomcode{animation:pa-float 2.6s ease-in-out infinite;}
.pa-mark{transition:transform .2s;} .pa-brand:hover .pa-mark{transform:rotate(4deg) scale(1.05);}
/* 승리 점수카드에 작은 왕관 스티커 */
.pa-sbcard.win{position:relative;}
.pa-sbcard.win::before{content:"👑";position:absolute;top:-16px;right:-8px;font-size:26px;transform:rotate(14deg);
  filter:drop-shadow(1.5px 1.5px 0 var(--ink));animation:pa-float 2.2s ease-in-out infinite;}
/* 정오 셀 등장 살짝 */
.pa-cse{transition:transform .12s;} .pa-cse:hover{transform:translateY(-2px) rotate(-3deg);}
/* 과제 카드 핀 살짝 강조 */
.pa-task{position:relative;}

/* ============ 고퀄 키치 장식 시스템 ============ */
/* 상단 아케이드 색띠 (화면 최상단 고정) */
.pa-stripe{position:fixed;top:0;left:0;right:0;height:8px;z-index:9999;
  background:linear-gradient(90deg,var(--tomato) 0 25%,var(--gold) 0 50%,var(--mint) 0 75%,var(--sky) 0 100%);
  border-bottom:3px solid var(--ink);}
/* 배경에 떠다니는 스티커들 (콘텐츠 뒤, 아주 은은하게) */
.pa-deco{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden;}
.pa-deco span{position:absolute;font-family:'Jua';filter:drop-shadow(2px 2px 0 var(--ink));opacity:.5;}
@keyframes pa-tw{0%,100%{transform:scale(1) rotate(0)}50%{transform:scale(1.25) rotate(16deg)}}
@keyframes pa-drift{0%,100%{transform:translateY(0) rotate(-8deg)}50%{transform:translateY(-14px) rotate(-2deg)}}
.block-container{position:relative;z-index:1;}

/* 스타버스트 (VS·배너 뒤에서 터지는 방사형) */
.pa-burst{position:relative;display:inline-grid;place-items:center;}
.pa-burst::before{content:"";position:absolute;width:150%;height:150%;z-index:-1;border-radius:50%;
  background:repeating-conic-gradient(from 0deg, var(--gold) 0deg 12deg, transparent 12deg 24deg);
  opacity:.5;animation:pa-spin 14s linear infinite;}
.pa-burst.tomato::before{background:repeating-conic-gradient(from 0deg, var(--tomato) 0deg 12deg, transparent 12deg 24deg);opacity:.32;}

/* 섹션 제목 손그림 밑줄 */
.pa-h{font-family:'Black Han Sans';font-size:24px;text-align:center;margin:18px 0 12px;display:inline-block;position:relative;left:50%;transform:translateX(-50%);}
.pa-h::after{content:"";display:block;height:8px;margin-top:2px;border-radius:6px;
  background:var(--gold);border:2.5px solid var(--ink);transform:rotate(-.6deg);}

/* 카드 상단 컬러 탭 */
.pa-card{position:relative;overflow:visible;}
.pa-tab{position:absolute;top:-3px;left:22px;width:64px;height:9px;border:3px solid var(--ink);border-top:none;
  border-radius:0 0 8px 8px;background:var(--gold);}
.pa-tab.mint{background:var(--mint);} .pa-tab.tomato{background:var(--tomato);} .pa-tab.sky{background:var(--sky);}

/* 룸코드: 스캔라인 LCD 느낌 */
.pa-roomcode{position:relative;overflow:hidden;}
.pa-roomcode::after{content:"";position:absolute;inset:0;pointer-events:none;
  background:repeating-linear-gradient(0deg, rgba(255,255,255,.05) 0 2px, transparent 2px 4px);}

/* 캐릭터 있는 채점 로더 */
.pa-load{display:flex;justify-content:center;align-items:flex-end;gap:14px;height:64px;margin:4px 0 14px;}
.pa-load .coin{width:34px;height:34px;border-radius:50%;background:var(--gold);border:3px solid var(--ink);
  display:grid;place-items:center;font-family:'Black Han Sans';color:var(--ink);font-size:17px;box-shadow:2px 2px 0 var(--ink);
  animation:pa-bounce 1s ease-in-out infinite;}
.pa-load .coin:nth-child(2){animation-delay:.15s;background:var(--mint);}
.pa-load .coin:nth-child(3){animation-delay:.3s;background:var(--tomato);color:#fff;}
@keyframes pa-bounce{0%,100%{transform:translateY(0)}40%{transform:translateY(-22px) rotate(-12deg)}}

/* 결과 배너 뒤 색종이 점 */
@keyframes pa-fall{0%{transform:translateY(-10px) rotate(0);opacity:0}10%{opacity:1}100%{transform:translateY(60px) rotate(220deg);opacity:0}}
.pa-confetti{position:relative;height:0;}
.pa-confetti i{position:absolute;width:9px;height:14px;border:2px solid var(--ink);border-radius:2px;animation:pa-fall 1.8s ease-in infinite;}

/* 가독성/리듬 미세 조정 */
.pa-card{padding:24px 26px;}
.pa-sub{font-size:17px;line-height:1.65;}
.pa-lbl{text-transform:uppercase;}
.pa-quote{box-shadow:inset 2px 2px 0 rgba(0,0,0,.04);}
.pa-avatar.foe{animation:pa-tw 2.2s ease-in-out infinite;}

/* ============ 보스 레이드 전용 ============ */
/* 보스 패널 */
.pa-boss{border:var(--bd);border-radius:18px;background:linear-gradient(180deg,#2a2320,#171513);color:var(--paper);
  box-shadow:var(--shadow);padding:16px 18px;margin-bottom:16px;position:relative;overflow:hidden;}
.pa-boss .row{display:flex;align-items:center;gap:14px;}
.pa-boss .sprite{font-size:46px;filter:drop-shadow(2px 2px 0 #000);animation:pa-float 2.4s ease-in-out infinite;}
.pa-boss .meta{flex:1;}
.pa-boss .name{font-family:'Black Han Sans';font-size:22px;letter-spacing:1px;color:var(--gold);}
.pa-boss .rnd{font-family:'Space Mono';font-size:12px;color:#cdbfa6;letter-spacing:1px;}
.pa-hpbar{height:22px;border:2.5px solid #000;border-radius:30px;background:#0c0a09;overflow:hidden;margin-top:10px;box-shadow:inset 2px 2px 0 rgba(0,0,0,.5);}
.pa-hpfill{height:100%;width:100%;border-radius:30px;transition:width .6s cubic-bezier(.2,1,.3,1);
  background:repeating-linear-gradient(45deg,rgba(255,255,255,.18) 0 8px,transparent 8px 16px),var(--mint);}
.pa-hpfill.mid{background:repeating-linear-gradient(45deg,rgba(255,255,255,.18) 0 8px,transparent 8px 16px),var(--gold);}
.pa-hpfill.low{background:repeating-linear-gradient(45deg,rgba(255,255,255,.18) 0 8px,transparent 8px 16px),var(--tomato);}
.pa-hptext{display:flex;justify-content:space-between;font-family:'Space Mono';font-weight:700;font-size:12px;margin-top:6px;color:var(--paper);}

/* 난이도 뱃지 */
.pa-diff{display:inline-block;font-family:'Jua';font-size:12px;padding:4px 12px;border:2.5px solid var(--ink);border-radius:20px;
  box-shadow:2px 2px 0 var(--ink);color:var(--ink);}
.pa-diff.Low{background:var(--sky);color:#fff;} .pa-diff.Mid{background:var(--gold);} .pa-diff.High{background:var(--tomato);color:#fff;}

/* 상태효과 배너 */
.pa-status{border:2.5px solid var(--ink);border-radius:14px;padding:10px 14px;margin-top:10px;font-size:13.5px;line-height:1.5;
  box-shadow:var(--shadow-sm);background:#fff;}
.pa-status.buff{background:#dff7ee;} .pa-status.debuff{background:#ffe2db;}
.pa-status.none{background:var(--paper-2);color:#7a7160;}
.pa-status .hint{display:block;margin-top:6px;font-family:'Space Mono';font-size:12px;color:#5b5346;}

/* 협동 플레이어 패널 */
.pa-coop{border:var(--bd);border-radius:14px;background:#fff;box-shadow:var(--shadow-sm);padding:12px 14px;margin-bottom:10px;}
.pa-coop.me{background:#eafaf4;} .pa-coop .who{font-family:'Jua';font-size:15px;}
.pa-coop .st{font-family:'Space Mono';font-size:11px;color:#8a7e6b;}
.pa-coop .badge{float:right;font-family:'Jua';font-size:12px;border:2px solid var(--ink);border-radius:16px;padding:1px 9px;}
.pa-coop .badge.ok{background:var(--mint);} .pa-coop .badge.wait{background:var(--paper-2);}

/* 데미지 팝 */
@keyframes pa-dmg{0%{opacity:0;transform:translateY(8px) scale(.7)}30%{opacity:1;transform:translateY(-2px) scale(1.12)}100%{opacity:1;transform:none}}
.pa-dmg{font-family:'Black Han Sans';font-size:34px;color:var(--tomato);-webkit-text-stroke:2px var(--ink);
  display:inline-block;animation:pa-dmg .6s cubic-bezier(.2,1.6,.4,1) both;}

/* 라운드 로그 (최종 리포트) */
.pa-log{width:100%;border-collapse:separate;border-spacing:0 6px;font-family:'Space Mono';font-size:12.5px;}
.pa-log td{background:#fff;border-top:2.5px solid var(--ink);border-bottom:2.5px solid var(--ink);padding:8px 10px;}
.pa-log td:first-child{border-left:2.5px solid var(--ink);border-radius:10px 0 0 10px;}
.pa-log td:last-child{border-right:2.5px solid var(--ink);border-radius:0 10px 10px 0;}
</style>"""
st.markdown(CSS, unsafe_allow_html=True)

# 화면 전체 장식 (한 번만): 상단 색띠 + 배경 스티커
st.markdown(
    '<div class="pa-stripe"></div>'
    '<div class="pa-deco">'
    '<span style="top:12%;left:5%;font-size:30px;color:var(--gold);animation:pa-tw 2.6s ease-in-out infinite">✦</span>'
    '<span style="top:24%;right:6%;font-size:22px;color:var(--mint);animation:pa-tw 3.1s ease-in-out infinite .6s">★</span>'
    '<span style="top:58%;left:3%;font-size:26px;color:var(--tomato);animation:pa-drift 5s ease-in-out infinite">✱</span>'
    '<span style="bottom:10%;right:8%;font-size:34px;color:var(--gold);animation:pa-drift 6s ease-in-out infinite .8s">✦</span>'
    '<span style="bottom:22%;left:9%;font-size:18px;color:var(--sky);animation:pa-tw 2.4s ease-in-out infinite .3s">●</span>'
    '</div>',
    unsafe_allow_html=True,
)


# =====================================================================
# 상단바
# =====================================================================
def _pa_html(s: str) -> str:
    """HTML 블록을 빈 줄/들여쓰기 없이 정리해 Streamlit 마크다운이 코드블록으로
    오인하지 않게 한다."""
    return "\n".join(ln.strip() for ln in s.splitlines() if ln.strip())


def top_bar():
    ss = st.session_state
    if ss.screen == "login":
        right = ""
    else:
        wins = ss.record.get("win", 0)
        nick = ss.nick or "플레이어"
        right = (
            f'<div class="pa-purse"><span class="pa-coin">P</span>'
            f'<span>{nick}</span>&nbsp;·&nbsp;<span style="color:var(--mint-dark)">{wins}승</span></div>'
        )
    st.markdown(
        _pa_html(
            f'''<div class="pa-top">
              <div class="pa-brand">
                <div class="pa-mark">P</div>
                <div><h1>PROMPT ARENA</h1><small>프롬프트 대전 · BETA</small></div>
              </div>
              {right}
            </div>'''
        ),
        unsafe_allow_html=True,
    )


# =====================================================================
# 1) 로그인
# =====================================================================
def render_login():
    ss = st.session_state
    st.markdown(
        '''<div class="pa-hero">
            <div class="pa-big">프롬프트<br><span class="red">보스</span> <span class="vs">⚔</span> 레이드</div>
            <p class="pa-sub">둘이 <b>협력</b>해 최대 6라운드, 프롬프트로 <b>보스를 처치</b>하라.<br>점수가 높을수록 큰 데미지 · 버프, 낮으면 디버프 · 난이도 하향.</p>
        </div>''',
        unsafe_allow_html=True,
    )
    st.write("")
    c = st.columns([1, 2, 1])[1]
    with c:
        nick = st.text_input("닉네임", value=ss.nick, key="nick_input",
                             placeholder="닉네임", label_visibility="collapsed")
        if st.button("⚔️  레이드 시작하기", type="primary", key="login_go"):
            ss.nick = (nick or "").strip() or f"플레이어{ss.client_id[:4]}"
            fetch_record()
            ss.screen = "lobby"
            st.rerun()
        st.markdown('<p class="pa-hint" style="text-align:center">닉네임은 화면 표시용이에요. 신원은 자동 발급되는 세션 ID로 관리돼요.</p>',
                    unsafe_allow_html=True)

    with st.expander("⚙️ 백엔드 서버 주소 설정"):
        base = st.text_input("Base URL", value=ss.base, key="base_input")
        ss.base = base.strip().rstrip("/") or DEFAULT_BASE
        ok = False
        if st.button("연결 확인", key="ping"):
            try:
                r = api_get("/api/me")
                ok = r.status_code == 200
                st.success(f"연결 성공 · 세션 {r.json().get('client_id','')[:8]}…") if ok else st.error(f"응답 {r.status_code}")
            except Exception as e:
                st.error(f"연결 실패: {e}")
    st.markdown('<p class="pa-foot">PROMPT ARENA — 15조 불꽃청년 · FastAPI 연동 프론트엔드</p>', unsafe_allow_html=True)


# =====================================================================
# 2) 로비 (방 생성 / 방 코드 입장)
# =====================================================================
def render_lobby():
    ss = st.session_state
    rec = ss.record
    total = rec["win"] + rec["lose"] + rec["draw"]
    rate = f'{round(rec["win"]/total*100)}%' if total else "—"

    st.markdown(
        f'''<div class="pa-card"><div class="pa-tab"></div>
            <span class="pa-tag">협동 보스 레이드</span>
            <h2 style="font-family:'Black Han Sans';font-size:30px;line-height:1.15;margin:12px 0 6px">{ss.nick}님,<br>동료와 출격 준비!</h2>
            <p style="color:#5b5346;line-height:1.6;margin-bottom:6px">방을 새로 파서 코드를 공유하거나, 동료가 준 코드로 같은 방에 들어가면 레이드가 시작돼요.
            라운드마다 프롬프트로 보스를 공격! 두 사람의 개인 점수가 각각 데미지로 들어갑니다.</p>
            <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:14px">
              <div class="pa-chip" style="min-width:84px"><div class="vl">{rec["win"]}</div><div class="lb">클리어</div></div>
              <div class="pa-chip" style="min-width:84px"><div class="vl">{rec["lose"]}</div><div class="lb">실패</div></div>
              <div class="pa-chip" style="min-width:84px"><div class="vl">{rate}</div><div class="lb">클리어율</div></div>
            </div>
        </div>''',
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="pa-card" style="margin-bottom:8px"><div class="pa-tab tomato"></div><span class="pa-tag tomato">새 방</span>'
                    '<h3 style="font-family:\'Jua\';font-size:19px;margin:10px 0 4px">새 레이드방 만들기</h3>'
                    '<p class="pa-hint" style="margin-bottom:10px">방을 만들면 4자리 코드가 나와요. 동료에게 코드를 알려주세요.</p></div>',
                    unsafe_allow_html=True)
        if st.button("⚔️ 방 만들기", type="primary", key="create"):
            create_room()
    with col2:
        st.markdown('<div class="pa-card" style="margin-bottom:8px"><div class="pa-tab mint"></div><span class="pa-tag mint">방 코드로 입장</span>'
                    '<h3 style="font-family:\'Jua\';font-size:19px;margin:10px 0 4px">동료와 합류</h3>'
                    '<p class="pa-hint" style="margin-bottom:10px">동료가 만든 4자리 코드를 입력하면 레이드 시작!</p></div>',
                    unsafe_allow_html=True)
        code = st.text_input("방 코드", max_chars=4, key="join_code",
                             placeholder="0000", label_visibility="collapsed")
        if st.button("입장하기 →", key="join"):
            join_room((code or "").strip())

    st.markdown('<p class="pa-foot">PROMPT ARENA — 15조 불꽃청년 · FastAPI 연동 프론트엔드</p>', unsafe_allow_html=True)


def create_room():
    ss = st.session_state
    try:
        r = api_post("/api/rooms")
    except Exception as e:
        st.error(f"서버에 연결할 수 없어요. 백엔드가 실행 중인지 확인해 주세요. ({e})")
        return
    if r.status_code == 201:
        data = r.json()
        ss.room_code = data["room_code"]
        ss.is_host = True
        enter_arena()
    elif r.status_code == 409:
        # 서버가 이전 세션의 UUID를 아직 방 멤버로 기억 중 → UUID 새로 발급 후 재시도
        ss.client_id = str(uuid.uuid4())
        time.sleep(0.4)
        try:
            r2 = api_post("/api/rooms")
        except Exception as e:
            st.error(f"재시도 중 오류가 발생했어요. ({e})")
            return
        if r2.status_code == 201:
            data = r2.json()
            ss.room_code = data["room_code"]
            ss.is_host = True
            enter_arena()
        else:
            st.error(f"방 생성에 실패했어요. 백엔드를 재시작해 주세요. (응답 {r2.status_code})")
    else:
        st.error(f"방 생성 실패 (응답 {r.status_code})")


def join_room(code: str):
    ss = st.session_state
    if len(code) < 1:
        st.warning("방 코드를 입력해 주세요.")
        return
    try:
        r = api_get(f"/api/rooms/{code}")
    except Exception as e:
        st.error(f"서버에 연결할 수 없어요. ({e})")
        return
    if r.status_code == 404:
        st.warning("그런 방 코드가 없어요. 코드를 다시 확인해 주세요.")
        return
    if r.status_code != 200:
        st.error(f"방 조회 실패 (응답 {r.status_code})")
        return
    status = r.json().get("status")
    if status not in ("WAITING",):
        st.warning(f"지금은 입장할 수 없는 방이에요. (상태: {status})")
        return
    ss.room_code = code
    ss.is_host = False
    enter_arena()


def enter_arena():
    ss = st.session_state
    ss.screen = "arena"
    ss.phase = "waiting"
    ss.round = None
    ss.result = None
    ss.error = None
    ss.joined = False
    st.rerun()


# =====================================================================
# 3) 아레나 (WebSocket 라이프사이클: 대기 → 라운드 → 채점 → 결과)
# =====================================================================
def ensure_conn():
    ss = st.session_state
    if ss.conn is None:
        url = f"{ws_base()}/ws/raid/{ss.room_code}?client_id={ss.client_id}"
        conn = WSConn(url)
        try:
            conn.start()
        except Exception as e:
            ss.error = {"event": "ERROR", "code": "SERVER_ERROR",
                        "message": f"대전 서버에 연결하지 못했어요. ({e})", "action_required": "GO_TO_HOME"}
            ss.phase = "error"
            ss.conn = None
            return
        ss.conn = conn
        ss.joined = True


def _enter_round(msg: dict):
    """ROUND_START 페이로드로 라운드 입력 화면을 시작한다."""
    ss = st.session_state
    ss.round = {
        "round": msg.get("round", 1),
        "max_rounds": msg.get("max_rounds", 6),
        "task": msg.get("task", ""),
        "model": msg.get("model", ""),
        "time_limit": msg.get("time_limit", TIME_LIMIT),
        "difficulty": msg.get("difficulty", "Mid"),
        "char_limit": int(msg.get("char_limit", MAX_LEN)),
        "status_effect": msg.get("status_effect", "—"),
        "hint": msg.get("hint", ""),
        "boss_hp": msg.get("boss_hp", 100.0),
        "boss_max_hp": msg.get("boss_max_hp", 100.0),
    }
    ss.my_slot = msg.get("your_slot", ss.my_slot)
    ss.round_start_ts = time.time()
    ss.teammate_submitted = False
    ss.submit_rejected = None
    ss.next_round_ready = False
    ss.pop("editor", None)
    ss.submitted_once = False
    ss.phase = "round"


def drain_events():
    ss = st.session_state
    if not ss.conn:
        return
    for msg in ss.conn.drain():
        ev = msg.get("event")
        if ev == "RAID_START":
            ss.raid = {
                "boss_hp": msg.get("boss_hp", 100.0),
                "boss_max_hp": msg.get("boss_max_hp", 100.0),
                "max_rounds": msg.get("max_rounds", 6),
            }
        elif ev == "WAITING":
            if ss.phase not in ("round", "scoring", "round_result", "raid_end"):
                ss.phase = "waiting"
        elif ev == "ROUND_START":
            # 직전 라운드 결과를 보고 있으면 다음 라운드를 버퍼링(자동 전환 방지).
            if ss.phase == "round_result":
                ss.round = {
                    "round": msg.get("round", 1), "max_rounds": msg.get("max_rounds", 6),
                    "task": msg.get("task", ""), "model": msg.get("model", ""),
                    "time_limit": msg.get("time_limit", TIME_LIMIT),
                    "difficulty": msg.get("difficulty", "Mid"),
                    "char_limit": int(msg.get("char_limit", MAX_LEN)),
                    "status_effect": msg.get("status_effect", "—"),
                    "hint": msg.get("hint", ""),
                    "boss_hp": msg.get("boss_hp", 100.0),
                    "boss_max_hp": msg.get("boss_max_hp", 100.0),
                }
                ss.my_slot = msg.get("your_slot", ss.my_slot)
                ss.next_round_ready = True
            else:
                _enter_round(msg)
        elif ev == "TEAMMATE_SUBMITTED":
            ss.teammate_submitted = True
        elif ev == "SUBMIT_REJECTED":
            # 제출 거부 → 다시 입력 가능하도록 라운드로 복귀
            ss.submit_rejected = msg.get("message", "제출이 거부되었습니다.")
            ss.submitted_once = False
            if ss.phase == "scoring":
                ss.phase = "round"
        elif ev == "ROUND_TIMEOUT":
            ss.submit_rejected = msg.get("message", "시간 초과로 이번 라운드 기여가 0 처리됩니다.")
        elif ev == "ROUND_RESULT":
            ss.round_result = msg
            if ss.raid:
                ss.raid["boss_hp"] = msg.get("boss_hp", ss.raid["boss_hp"])
            ss.next_round_ready = False
            ss.pending_end = False
            ss.phase = "round_result"
        elif ev == "RAID_END":
            ss.raid_end = msg
            _tally("WIN" if msg.get("victory") else "LOSE")
            if ss.phase == "round_result":
                # 최종 라운드 결과를 먼저 보여주고, 버튼으로 리포트 전환
                ss.next_round_ready = True
                ss.pending_end = True
            else:
                ss.phase = "raid_end"
        elif ev == "ERROR":
            ss.error = msg
            ss.phase = "error"
        elif ev == "_CLOSED":
            if ss.phase not in ("round_result", "raid_end", "error"):
                ss.error = {"event": "ERROR", "code": "SERVER_ERROR",
                            "message": "레이드 서버와의 연결이 끊어졌어요.", "action_required": "GO_TO_HOME"}
                ss.phase = "error"


def _tally(result: str | None):
    rec = st.session_state.record
    key = (result or "").lower()
    if key in rec:
        rec[key] += 1


def render_arena():
    ss = st.session_state
    ensure_conn()
    drain_events()

    phase = ss.phase
    if phase == "waiting":
        render_waiting()
    elif phase == "round":
        render_round()
    elif phase == "scoring":
        render_scoring()
    elif phase == "round_result":
        render_round_result()
    elif phase == "raid_end":
        render_raid_end()
    elif phase == "error":
        render_error()


def _boss_panel_html(boss_hp: float, boss_max: float, rnd: int, max_rounds: int,
                     difficulty: str) -> str:
    boss_max = boss_max or 100.0
    pct = max(0.0, min(100.0, boss_hp / boss_max * 100))
    cls = "" if pct > 50 else ("mid" if pct > 25 else "low")
    return _pa_html(
        f'''<div class="pa-boss">
          <div class="row">
            <div class="sprite">👹</div>
            <div class="meta">
              <div class="name">프롬프트 보스</div>
              <div class="rnd">ROUND {rnd} / {max_rounds} &nbsp;·&nbsp; 난이도
                <span class="pa-diff {difficulty}">{difficulty}</span></div>
            </div>
          </div>
          <div class="pa-hpbar"><div class="pa-hpfill {cls}" style="width:{pct:.1f}%"></div></div>
          <div class="pa-hptext"><span>BOSS HP</span><span>{boss_hp:.1f} / {boss_max:.0f}</span></div>
        </div>'''
    )


def render_waiting():
    ss = st.session_state
    code_html = (f'<p class="pa-hint">아래 코드를 동료에게 공유하세요</p>'
                 f'<div class="pa-roomcode">{ss.room_code}</div>') if ss.is_host else \
                (f'<p class="pa-hint">방 코드</p><div class="pa-roomcode">{ss.room_code}</div>')
    st.markdown(
        _pa_html(
            f'''<div class="pa-card pa-center"><div class="pa-tab sky"></div>
            <span class="pa-tag sky">동료 대기 중</span>
            <div style="margin:16px 0 10px">{code_html}</div>
            <div style="margin:18px 0 6px">
              <div class="pa-fighter"><div class="pa-avatar me">😎</div><div style="font-family:Jua;font-size:14px">{ss.nick}</div></div>
              <span class="pa-burst"><span class="pa-vsbubble" style="color:var(--mint-dark)">＋</span></span>
              <div class="pa-fighter"><div class="pa-avatar foe">🧑‍🚀</div><div style="font-family:Jua;font-size:14px">동료 합류 대기…</div></div>
            </div>
            <p class="pa-hint">같은 코드를 입력한 동료가 들어오면 자동으로 레이드가 시작돼요.</p>
        </div>'''
        ),
        unsafe_allow_html=True,
    )
    if st.button("← 나가기", key="leave_wait"):
        reset_to_lobby(); st.rerun()
    live_refresh(1200, "rf_wait")


def render_round():
    ss = st.session_state
    rd = ss.round or {}
    task = rd.get("task", "")
    model = rd.get("model", "")
    difficulty = rd.get("difficulty", "Mid")
    char_limit = int(rd.get("char_limit", MAX_LEN))
    status = rd.get("status_effect", "—")
    hint = rd.get("hint", "")
    limit = int(rd.get("time_limit", TIME_LIMIT))
    elapsed = time.time() - ss.round_start_ts
    remaining = max(0, int(limit - elapsed))

    # 보스 패널
    st.markdown(
        _boss_panel_html(
            float(rd.get("boss_hp", 100.0)), float(rd.get("boss_max_hp", 100.0)),
            int(rd.get("round", 1)), int(rd.get("max_rounds", 6)), difficulty,
        ),
        unsafe_allow_html=True,
    )

    # 상태효과 / 힌트 (내 슬롯 기준)
    if status and status != "—":
        scls = "buff" if status.startswith("🟢") else "debuff"
        hint_html = f'<span class="hint">💡 {_esc(hint)}</span>' if hint else ""
        st.markdown(f'<div class="pa-status {scls}">{_esc(status)}{hint_html}</div>',
                    unsafe_allow_html=True)

    st.markdown(
        f'''<div class="pa-card">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:8px">
              <span class="pa-tag tomato">라운드 진행 중</span>
              <span class="pa-hint">모델 <b style="font-family:Jua">{model or "—"}</b> · 최대 {char_limit}자</span>
            </div>
            <div class="pa-task"><h4>📌 이번 과제</h4><p>{task or "과제를 불러오는 중…"}</p></div>
        </div>''',
        unsafe_allow_html=True,
    )

    # 부드러운 JS 카운트다운 + 라이브 글자수 (파이썬 rerun 없이 동작 → 입력 방해 없음)
    _render_timer_and_counter(remaining, char_limit)

    if ss.teammate_submitted:
        st.markdown('<p class="pa-hint" style="text-align:center;color:var(--mint-dark)">✅ 동료가 먼저 제출했어요! 함께 보스를 노려봐요.</p>',
                    unsafe_allow_html=True)
    if ss.submit_rejected:
        st.warning(ss.submit_rejected)

    ss.setdefault("editor", "")
    text = st.text_area("프롬프트", key="editor", height=220,
                        placeholder="여기에 프롬프트를 작성하세요.\n예) 당신은 한국어 분류기입니다. 입력을 읽고 정답 한 단어만 출력하세요. 다른 말은 절대 붙이지 마세요. ...",
                        label_visibility="collapsed")

    n = len(text or "")
    over = n > char_limit
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown('<p class="pa-hint" style="margin-top:6px">⚡ 점수가 높을수록 큰 데미지! 짧고 정확할수록 길이 점수가 올라가요.</p>',
                    unsafe_allow_html=True)
    with c2:
        color = "var(--tomato)" if over else "var(--ink)"
        st.markdown(f'<p style="text-align:right;font-family:Space Mono;font-weight:700;margin-top:6px;color:{color}">{n} / {char_limit}자</p>',
                    unsafe_allow_html=True)

    if over:
        st.warning(f"{char_limit}자를 넘었어요. 줄여야 제출할 수 있어요. (현재 {n}자)")

    if st.button("🚀 공격! (제출)", type="primary", key="submit_prompt", disabled=over):
        submit_prompt(text or "")

    # 안전망: 시간이 다 됐는데도 화면이 남아있으면 현재 입력으로 제출 처리
    if remaining <= 0 and not ss.get("submitted_once"):
        submit_prompt(text or "", timed_out=True)


def _render_timer_and_counter(remaining: int, char_limit: int = MAX_LEN):
    """JS로 매끄러운 카운트다운 + 입력창 글자수 실시간 표시 (rerun 불필요)."""
    html = """
    <div style="display:flex;justify-content:center;margin:2px 0 14px">
      <div id="pa-clock" style="font-family:'Space Mono',monospace;font-weight:700;font-size:30px;border:3px solid #171513;
        background:#171513;color:#ffc23c;padding:6px 18px;border-radius:12px;box-shadow:3px 3px 0 #171513;min-width:130px;text-align:center">--:--</div>
    </div>
    <div style="display:flex;align-items:center;gap:10px;max-width:560px;margin:0 auto 6px">
      <div style="flex:1;height:11px;border:2.5px solid #171513;border-radius:30px;background:#fff;overflow:hidden">
        <i id="pa-bar" style="display:block;height:100%;width:0;background:#37cfa0;transition:width .15s,background .2s"></i>
      </div>
    </div>
    <script>
      (function(){
        var remain = __REMAIN__, MAX = __LIMIT__;
        var clock = document.getElementById('pa-clock');
        var bar = document.getElementById('pa-bar');
        var doc = window.parent.document;
        function fmt(s){ s=Math.max(0,s); var m=Math.floor(s/60), x=s%60; return m+':'+String(x).padStart(2,'0'); }
        function tickClock(){
          clock.textContent = fmt(remain);
          if(remain<=30){ clock.style.background='#ff5436'; clock.style.color='#fff'; }
          if(remain<=0){ clearInterval(iv); }
          remain--;
        }
        tickClock(); var iv=setInterval(tickClock,1000);
        function findTA(){ var t=doc.querySelectorAll('textarea'); return t.length?t[t.length-1]:null; }
        function updCount(){
          var ta=findTA(); if(!ta) return;
          var n=ta.value.length, pct=Math.min(100,n/MAX*100);
          bar.style.width=pct+'%';
          bar.style.background = n>MAX ? '#ff5436' : (n>MAX*0.7 ? '#ffc23c' : '#37cfa0');
        }
        var ta=findTA(); if(ta){ ta.addEventListener('input',updCount); }
        setInterval(updCount,400); updCount();
      })();
    </script>
    """.replace("__REMAIN__", str(int(remaining))).replace("__LIMIT__", str(int(char_limit)))
    st.components.v1.html(html, height=98)


def submit_prompt(text: str, timed_out: bool = False):
    ss = st.session_state
    if ss.get("submitted_once"):
        return
    char_limit = int((ss.round or {}).get("char_limit", MAX_LEN))
    if not timed_out and len(text) > char_limit:
        st.warning(f"{char_limit}자를 넘으면 제출할 수 없어요.")
        return
    ss.submitted_once = True
    ss.submit_rejected = None
    if ss.conn:
        ss.conn.send({"action": "SUBMIT", "prompt_text": text})
    ss.phase = "scoring"
    st.rerun()


def render_scoring():
    ss = st.session_state
    mate = "✅ 동료도 제출 완료! 보스를 채점 중…" if ss.teammate_submitted \
        else "🕓 동료의 제출을 기다리는 중…"
    st.markdown(
        _pa_html(
            f'''<div class="pa-card pa-center">
            <div class="pa-load"><div class="coin">P</div><div class="coin">＋</div><div class="coin">P</div></div>
            <h3 style="font-family:'Black Han Sans';font-size:24px;margin:0">공격 판정 중…</h3>
            <p class="pa-hint" style="margin-top:6px">두 프롬프트를 같은 모델에 넣고 테스트를 병렬로 돌려 데미지를 계산해요.</p>
            <p class="pa-hint">{mate}</p>
        </div>'''
        ),
        unsafe_allow_html=True,
    )
    live_refresh(1000, "rf_score")


def _case_grid(cases: list) -> str:
    cells = []
    for c in cases:
        ok = c.get("is_correct")
        cells.append(f'<div class="pa-cse {"ok" if ok else "no"}">{"○" if ok else "✕"}</div>')
    return '<div class="pa-cases">' + "".join(cells) + "</div>"


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _raid_player_card(who: str, data: dict, is_me: bool) -> str:
    """라운드 결과의 한 플레이어 카드 (개인 점수·데미지·정오·총평)."""
    side = "me" if is_me else "foe"
    score = float(data.get("score", 0.0))
    damage = float(data.get("damage", 0.0))
    correct = data.get("correct_count", 0)
    total = data.get("total_count", 0)
    timed_out = data.get("timed_out")
    prompt = (data.get("prompt") or "").strip() or "(제출 없음)"
    resp = (data.get("ai_response") or "").strip()
    resp_html = ""
    if resp and not resp.startswith("__WRONG__"):
        resp_html = (f'<p class="pa-lbl" style="margin-top:10px">모델 대표 출력</p>'
                     f'<div class="pa-quote" style="max-height:70px">{_esc(resp)}</div>')
    cases = data.get("test_case_results", [])
    grid = _case_grid(cases) if cases else '<p class="pa-hint">채점 없음</p>'
    timeout_badge = ' <span class="pa-flag">시간 초과</span>' if timed_out else ""
    return (
        f'<div class="pa-panel {side}">'
        f'<div class="pa-ph"><span>{who}{timeout_badge}</span>'
        f'<span class="pa-acc">⚔️ {damage:.1f} DMG</span></div>'
        f'<div class="pa-pbody">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
        f'<span class="pa-lbl" style="margin:0">개인 점수</span>'
        f'<b style="font-family:Black Han Sans;font-size:22px">{score:.2f}<small style="font-size:12px;color:#8a7e6b"> / 1.00</small></b></div>'
        f'<p class="pa-lbl">제출한 프롬프트</p><div class="pa-quote">{_esc(prompt)}</div>'
        f'{resp_html}'
        f'<p class="pa-lbl" style="margin-top:10px">문제별 정오 ({correct}/{total})</p>{grid}'
        f'</div></div>'
    )


def render_round_result():
    ss = st.session_state
    rr = ss.round_result or {}
    my_slot = ss.my_slot
    mate_slot = "p2" if my_slot == "p1" else "p1"
    me = rr.get(my_slot) or {}
    mate = rr.get(mate_slot) or {}

    # 보스 패널 (데미지 반영 후)
    st.markdown(
        _boss_panel_html(
            float(rr.get("boss_hp", 0.0)), float(rr.get("boss_max_hp", 100.0)),
            int(rr.get("round", 1)),
            int((ss.raid or {}).get("max_rounds", 6)),
            rr.get("next_difficulty", "Mid"),
        ),
        unsafe_allow_html=True,
    )

    st.markdown(
        _pa_html(
            f'''<div class="pa-center">
            <span class="pa-tag tomato">라운드 {rr.get("round","?")} 결과</span>
            <div style="margin:8px 0"><span class="pa-dmg">- {rr.get("damage_dealt",0)} HP</span></div>
            <p style="font-family:Jua;font-size:15px;color:#5b5346;margin-bottom:6px">{_esc(rr.get("system_message",""))}</p>
        </div>'''
        ),
        unsafe_allow_html=True,
    )

    st.markdown(_raid_player_card(f"😎 {ss.nick} (나)", me, True), unsafe_allow_html=True)
    st.markdown(_raid_player_card("🧑‍🚀 동료", mate, False), unsafe_allow_html=True)

    # 내 다음 라운드 상태효과 안내
    nxt = me.get("next_status_effect", "—")
    if nxt and nxt != "—":
        scls = "buff" if nxt.startswith("🟢") else "debuff"
        st.markdown(f'<div class="pa-status {scls}">다음 라운드 — {_esc(nxt)}</div>',
                    unsafe_allow_html=True)

    # 디렉터(LLM/휴리스틱) 판단 근거 — 점수·제출시간·프롬프트를 보고 결정
    rationale = (rr.get("director_rationale") or "").strip()
    if rationale:
        st.markdown(
            f'<p class="pa-hint" style="text-align:center;margin-top:6px">'
            f'🎬 디렉터 판단 — {_esc(rationale)}</p>',
            unsafe_allow_html=True,
        )

    # 내 프롬프트 AI 총평 (있을 때만)
    evaluation = (me.get("prompt_evaluation") or "").strip()
    if evaluation and not evaluation.startswith("__WRONG__"):
        st.markdown(
            f'''<div class="pa-feedback" style="margin-top:12px"><h4 style="font-family:Jua;font-size:16px;margin:0 0 10px">🧐 AI 총평</h4>
                <div class="pa-fb"><span class="pa-pin good">AI</span><span>{_esc(evaluation)}</span></div></div>''',
            unsafe_allow_html=True,
        )

    # 다음 라운드 / 최종 결과로 진행
    if ss.next_round_ready:
        label = "🏁 최종 결과 보기" if ss.pending_end else "다음 라운드로 ▶"
        c = st.columns([1, 2, 1])[1]
        with c:
            if st.button(label, type="primary", key="advance"):
                if ss.pending_end:
                    ss.phase = "raid_end"
                else:
                    ss.round_start_ts = time.time()
                    ss.submitted_once = False
                    ss.teammate_submitted = False
                    ss.submit_rejected = None
                    ss.next_round_ready = False
                    ss.pop("editor", None)
                    ss.phase = "round"
                st.rerun()
    else:
        st.markdown('<p class="pa-hint" style="text-align:center">다음 라운드를 준비하는 중…</p>',
                    unsafe_allow_html=True)
        live_refresh(800, "rf_rr")


def _round_log_table(log: list) -> str:
    rows = []
    for r in log:
        rows.append(
            f'<tr><td>R{r.get("round","?")}</td>'
            f'<td><span class="pa-diff {r.get("difficulty","Mid")}">{r.get("difficulty","Mid")}</span></td>'
            f'<td>팀점수 {r.get("round_score",0)}</td>'
            f'<td>-{r.get("damage_dealt",0)} HP</td>'
            f'<td>P1 {r.get("p1_score",0)} · P2 {r.get("p2_score",0)}</td></tr>'
        )
    return '<table class="pa-log">' + "".join(rows) + "</table>"


def render_raid_end():
    ss = st.session_state
    end = ss.raid_end or {}
    victory = bool(end.get("victory"))
    boss_hp = float(end.get("boss_hp", 0.0))
    boss_max = float(end.get("boss_max_hp", 100.0))
    team_score = float(end.get("team_score", 0.0))
    rounds_played = end.get("rounds_played", 0)
    log = end.get("round_log", [])

    banner = ("win", "보스 처치!") if victory else ("lose", "레이드 실패")
    sub = end.get("message", "")

    confetti = ""
    if victory:
        cols = ["var(--tomato)", "var(--gold)", "var(--mint)", "var(--sky)", "var(--gold)", "var(--tomato)", "var(--mint)"]
        bits = "".join(
            f'<i style="left:{8+i*13}%;background:{c};animation-delay:{(i%4)*0.18:.2f}s"></i>'
            for i, c in enumerate(cols)
        )
        confetti = f'<div class="pa-confetti">{bits}</div>'

    st.markdown(
        _pa_html(
            f'''<div class="pa-center">{confetti}
            <span class="pa-tag tomato">레이드 종료</span>
            <div><span class="pa-burst"><span class="pa-banner {banner[0]}">{banner[1]}</span></span></div>
            <p style="font-family:Jua;font-size:17px;color:#5b5346;margin-bottom:12px">{_esc(sub)}</p>
        </div>'''
        ),
        unsafe_allow_html=True,
    )

    st.markdown(
        _boss_panel_html(boss_hp, boss_max, rounds_played,
                         int((ss.raid or {}).get("max_rounds", 6)),
                         (log[-1].get("difficulty", "Mid") if log else "Mid")),
        unsafe_allow_html=True,
    )

    st.markdown(
        f'''<div class="pa-card pa-center">
            <div style="display:flex;gap:14px;justify-content:center;flex-wrap:wrap">
              <div class="pa-chip"><div class="vl">{rounds_played}</div><div class="lb">진행 라운드</div></div>
              <div class="pa-chip"><div class="vl">{team_score:.2f}</div><div class="lb">팀 누적 점수</div></div>
              <div class="pa-chip"><div class="vl">{boss_hp:.0f}</div><div class="lb">남은 보스 HP</div></div>
            </div>
        </div>''',
        unsafe_allow_html=True,
    )

    if log:
        st.markdown('<div class="pa-center"><span class="pa-h">라운드 기록</span></div>',
                    unsafe_allow_html=True)
        st.markdown(_round_log_table(log), unsafe_allow_html=True)

    _result_buttons()


def _result_buttons():
    c = st.columns([1, 2, 1])[1]
    with c:
        if st.button("🏠 로비로 나가기", type="primary", key="home"):
            reset_to_lobby(); st.rerun()


def render_error():
    ss = st.session_state
    err = ss.error or {}
    code = err.get("code", "SERVER_ERROR")
    msg = err.get("message", "알 수 없는 오류가 발생했어요.")
    action = err.get("action_required", "GO_TO_HOME")
    label = {"OPPONENT_DISCONNECTED": "상대 이탈", "AI_CALL_FAILED": "AI 호출 실패", "SERVER_ERROR": "오류"}.get(code, "오류")
    st.markdown(
        f'''<div class="pa-card pa-center">
            <span class="pa-tag tomato">{label}</span>
            <div style="font-size:48px;margin:10px 0">🛟</div>
            <p style="font-family:Jua;font-size:18px;line-height:1.5">{msg}</p>
        </div>''',
        unsafe_allow_html=True,
    )
    if action == "RETRY_ROUND":
        if st.button("🔁 라운드 다시 시도", type="primary", key="retry"):
            reset_to_lobby(); st.rerun()
    else:
        if st.button("🏠 홈으로", type="primary", key="go_home"):
            reset_to_lobby(); st.rerun()


# =====================================================================
# 라우팅
# =====================================================================
top_bar()
screen = st.session_state.screen
if screen == "login":
    render_login()
elif screen == "lobby":
    render_lobby()
elif screen == "arena":
    render_arena()
