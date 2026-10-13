# -*- coding: utf-8 -*-
"""원정 보내기: 친구를 몇 시간 심부름 보내면 새전·옷감·부적을 들고 돌아온다.

- 원정 중인 친구는 작업표시줄에서 사라진다. 실제 시각(time.time)으로 재므로 꺼 둔 동안에도 다녀온다.
- 보상은 떠날 때의 분당 수입으로 정해 둔다 (그 사이 신사를 키워도 바뀌지 않음).
- 그곳에 어울리는 친구(적성)를 보내면 보상 ×1.5.
- 동시에 보낼 수 있는 친구: 신사 1~2단계 1명, 3~4단계 2명, 5단계 3명.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass

from . import omamori
from .state import GameState


@dataclass(frozen=True)
class Place:
    key: str
    icon: str
    name: str
    hours: float
    saisen: float          # × 분당 수입
    cloth: int
    charm: bool            # 부적 뽑기 1번
    fits: tuple[str, ...]  # 적성 친구
    lines: tuple[str, ...]  # 원정 보고에 쓰는 이야기 ({n} = 친구 이름)


PLACES = {p.key: p for p in [
    Place("village", "🏘", "인간 마을 심부름", 1, 45, 0, False, ("sakuya", "sanae"),
          ("{n}, 인간 마을에서 장을 봐 왔다.", "{n}, 찻집에서 경단을 얻어먹고 왔다.", "{n}, 길 잃은 아이를 집에 데려다줬다.")),
    Place("forest", "🍄", "마법의 숲 채집", 2, 95, 5, False, ("marisa", "cirno"),
          ("{n}, 버섯을 한 바구니 따 왔다.", "{n}, 숲에서 반짝이는 돌을 주웠다.", "{n}, 요정들과 숨바꼭질하다 왔다.")),
    Place("youkai", "👹", "요괴 퇴치", 4, 200, 15, False, ("reimu", "youmu", "meiling"),
          ("{n}, 말썽 부리던 요괴를 혼내 주고 사례금을 받았다.", "{n}, 밤길의 요괴를 쫓아냈다.", "{n}, 퇴치 의뢰를 깔끔하게 끝냈다.")),
    Place("mansion", "🏰", "홍마관 다과회", 8, 420, 30, True, ("remilia", "flandre", "sakuya", "meiling"),
          ("{n}, 홍마관 다과회에서 실컷 놀다 왔다.", "{n}, 도서관에서 책을 빌려 왔다 (진짜로 빌렸다).", "{n}, 홍차와 케이크를 잔뜩 먹고 왔다.")),
]}
FIT_BONUS = 1.5


def slots(s: GameState) -> int:
    return 1 if s.shrine_level <= 2 else 2 if s.shrine_level <= 4 else 3


def away(s: GameState) -> set[str]:
    return {e["char"] for e in s.expeditions}


def reward_for(s: GameState, char: str, place: str) -> dict:
    p = PLACES[place]
    k = FIT_BONUS if char in p.fits else 1.0
    per = max(10, s.income_per_min)
    return {"saisen": int(per * p.saisen * k), "cloth": int(p.cloth * k), "charm": p.charm}


def can_send(s: GameState, char: str) -> str:
    """보낼 수 없는 이유 (보낼 수 있으면 빈 문자열)."""
    if char not in s.unlocked:
        return "아직 못 만난 친구예요"
    if char in away(s):
        return "벌써 원정 중이에요"
    if len(s.expeditions) >= slots(s):
        return f"한 번에 {slots(s)}명까지 보낼 수 있어요"
    return ""


def send(s: GameState, char: str, place: str, now: float | None = None) -> bool:
    if place not in PLACES or can_send(s, char):
        return False
    now = now or time.time()
    s.expeditions.append({"char": char, "place": place, "start": now, "end": now + PLACES[place].hours * 3600,
                          "reward": reward_for(s, char, place)})
    return True


def left(e: dict, now: float | None = None) -> float:
    return max(0.0, e["end"] - (now or time.time()))


def finished(s: GameState, now: float | None = None) -> list[dict]:
    now = now or time.time()
    return [e for e in s.expeditions if e["end"] <= now]


def collect(s: GameState, e: dict, rng: random.Random | None = None) -> tuple[list[str], str]:
    """다녀온 원정의 보상을 받는다 → (이야기 줄들, 보상 한 줄)."""
    rng = rng or random.Random()
    s.expeditions.remove(e)
    r = e["reward"]
    s.add_saisen(r["saisen"])
    s.cloth += r["cloth"]
    parts = [f"새전 +{r['saisen']:,}"]
    if r["cloth"]:
        parts.append(f"옷감 +{r['cloth']}")
    if r.get("charm"):
        s.saisen += omamori.price(s)                      # 부적 한 번 공짜
        res = omamori.pull(s, 1)
        if res:
            parts.append(omamori.CHARMS[res[0][0]].name)
    s.expedition_done += 1
    return [rng.choice(PLACES[e["place"]].lines)], "  ·  ".join(parts)


def fmt_left(sec: float) -> str:
    h, m = int(sec // 3600), int(sec % 3600 // 60)
    return f"{h}시간 {m}분" if h else f"{max(1, m)}분"
