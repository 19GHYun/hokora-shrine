# -*- coding: utf-8 -*-
"""식년천궁(式年遷宮): 다 자란 신사를 새로 지어 올린다 (이세 신궁이 20년마다 하는 것처럼).

- 신사가 가장 높은 단계일 때만. 값은 처음 50만, 할 때마다 2배 — 쌓아 둔 새전을 크게 쓰는 곳.
- 1시간 동안 짓는 중 (신사에 대나무 비계와 가림막). 그동안도 새전은 그대로 들어온다.
- 다 지으면 새전 수입이 영구히 +10% (n번 지었으면 +10%·n, 꺼져 있는 동안의 수입도), "N대째 신사".
- 진행은 아무것도 되돌리지 않는다 (벌 없는 프레스티지).
끝나는 시각은 실제 시계(time.time) 기준이라 꺼 둔 동안에도 공사는 이어진다.
"""
from __future__ import annotations

import time

from . import shintoku
from .state import MAX_STAGE, GameState

BASE_COST = 500_000
BUILD_SECONDS = 3600.0
BOOST_EACH = 0.10


def cost(s: GameState) -> int:
    """값 (신덕 '목수'면 Lv 마다 -2%). 정수로만 셈 — 30대째도 정확하게."""
    return BASE_COST * 2 ** s.sengu * (50 - shintoku.level(s, "carpenter")) // 50


def build_seconds(s: GameState) -> float:
    """공사 시간 (신덕 '목수'면 Lv 마다 -5분)."""
    return BUILD_SECONDS - shintoku.build_cut(s)


def fmt_build(s: GameState) -> str:
    m = round(build_seconds(s) / 60)
    return "1시간" if m == 60 else f"{m}분"


def multiplier(s: GameState) -> float:
    """지은 횟수만큼 수입 배율 (짓는 중인 것은 다 지어야 들어감).

    다 지었지만 아직 완성 처리(finish) 전인 것도 센다 — 꺼 둔 동안 끝났으면 그동안의 수입에도 들어가게.
    """
    done = 1 if s.sengu_until and not building(s) else 0
    return 1 + BOOST_EACH * (s.sengu + done)


def building(s: GameState, now: float | None = None) -> bool:
    return s.sengu_until > (now if now is not None else time.time())


def left(s: GameState, now: float | None = None) -> float:
    return max(0.0, s.sengu_until - (now if now is not None else time.time()))


def generation(s: GameState) -> int:
    """지금 신사가 몇 대째인지 (처음 신사 = 1대째)."""
    return s.sengu + 1


def blocked(s: GameState, now: float | None = None) -> str:
    """할 수 없는 까닭 (할 수 있으면 "")."""
    if s.shrine_level < MAX_STAGE:
        return "신사를 가장 높은 단계까지 올리면 할 수 있어요"
    if building(s, now) or s.sengu_until:
        return "새 신사를 짓는 중이에요"
    if s.saisen < cost(s):
        return f"새전이 {cost(s) - s.saisen:,} 모자라요"
    return ""


def start(s: GameState, now: float | None = None) -> bool:
    if blocked(s, now):
        return False
    s.saisen -= cost(s)
    s.sengu_until = (now if now is not None else time.time()) + build_seconds(s)
    return True


def finish(s: GameState, now: float | None = None) -> bool:
    """공사가 끝났으면 완성 처리 (True). 짓는 중이 아니거나 아직이면 False."""
    if not s.sengu_until or building(s, now):
        return False
    s.sengu += 1
    s.sengu_until = 0.0
    return True
