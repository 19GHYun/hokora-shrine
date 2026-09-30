# -*- coding: utf-8 -*-
"""참배: 새전을 넣고 소원을 빈다. 잠깐 동안의 효과(버프)나 소소한 즐거움을 산다.

효과가 끝나는 시각은 실제 시계(time.time) 기준으로 저장해서, 껐다 켜도 이어지고
꺼 둔 동안에도 시간은 흐른다.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from . import season
from .state import GameState

INCOME_BOOST = 2        # 번영 기원: 수입 배수
PAT_BOOST = 5           # 인연 기원: 쓰다듬기 보상 배수
NEWS_BOOST = 1.5        # 붕붕마루 신문 기사 효과: 수입 배수 (news.py)
NEWS_SECONDS = 30 * 60


@dataclass(frozen=True)
class Wish:
    key: str
    icon: str
    name: str
    desc: str
    cost: Callable[[GameState], int]
    field: str = ""          # 시간 효과면 끝나는 시각을 담는 GameState 항목
    seconds: float = 0.0


WISHES: dict[str, Wish] = {
    "snack": Wish("snack", "🍡", "간식 나눠 주기", "모두 신사 앞에 모여 폴짝 기뻐해요.",
                  lambda s: 20),
    "prosper": Wish("prosper", "💰", "번영 기원", f"1시간 동안 새전 수입 {INCOME_BOOST}배.",
                    lambda s: s.income_per_min * 40, "buff_income_until", 3600),
    "bond": Wish("bond", "💕", "인연 기원", f"30분 동안 쓰다듬기 보상 {PAT_BOOST}배.",
                 lambda s: 50, "buff_pat_until", 1800),
    "omikuji": Wish("omikuji", "🔮", "오미쿠지 한 번 더", "오늘 한 번 더 뽑아요 (이미 뽑았을 때).",
                    lambda s: 100 * s.shrine_level),
    "charm": Wish("charm", "🧿", "도둑 방지 부적", "24시간 동안 마리사가 새전을 안 훔쳐요.",
                  lambda s: 100, "charm_until", 24 * 3600),
}


def left(s: GameState, key: str, now: float | None = None) -> float:
    """시간 효과의 남은 초 (없으면 0)."""
    w = WISHES[key]
    if not w.field:
        return 0.0
    return max(0.0, getattr(s, w.field) - (now or time.time()))


def income_multiplier(s: GameState) -> float:
    """번영 기원 ×2, 붕붕마루 신문 기사 효과 ×1.5, 설날 ×2 (겹치면 곱함)."""
    m = float(INCOME_BOOST if left(s, "prosper") else 1)
    if news_active(s):
        m *= NEWS_BOOST
    if season.is_new_year():
        m *= season.NEW_YEAR_BOOST
    return m


def news_active(s: GameState) -> bool:
    return s.news_until > time.time()


def pat_multiplier(s: GameState) -> int:
    return PAT_BOOST if left(s, "bond") else 1


def charm_active(s: GameState) -> bool:
    return left(s, "charm") > 0


def blocked(s: GameState, key: str, can_draw_omikuji: bool) -> str:
    """지금 빌 수 없는 이유 (빌 수 있으면 빈 문자열)."""
    w = WISHES[key]
    if key == "omikuji" and can_draw_omikuji:
        return "오늘 오미쿠지를 아직 안 뽑았어요"
    if w.field and left(s, key):
        return "효과가 이미 켜져 있어요"
    if s.saisen < w.cost(s):
        return "새전이 모자라요"
    return ""


def buy(s: GameState, key: str, can_draw_omikuji: bool) -> bool:
    """새전을 내고 효과를 건다. 간식처럼 화면에서 보여줄 일은 부른 쪽(Game)이 한다."""
    if blocked(s, key, can_draw_omikuji):
        return False
    w = WISHES[key]
    s.saisen -= w.cost(s)
    if w.field:
        setattr(s, w.field, time.time() + w.seconds)
    if key == "omikuji":
        s.omikuji_extra += 1
    s.wishes_made += 1
    return True


def fmt_left(sec: float) -> str:
    if sec >= 3600:
        return f"{int(sec // 3600)}시간 {int(sec % 3600 // 60)}분 남음"
    return f"{int(sec // 60)}분 {int(sec % 60)}초 남음"
