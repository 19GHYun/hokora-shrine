# -*- coding: utf-8 -*-
"""친구 수련: 새전을 들여 친구의 특기를 Lv.10 까지 키운다.

- Lv.1 은 지금까지와 같고, 오를수록 특기를 더 자주(쿨타임 Lv 마다 -4%, Lv.10 이면 64%) · 더 세게 쓴다.
- 값은 5천에서 시작해 레벨마다 2배 (Lv.9 → 10 은 128만) — 친구 9명 모두 키우려면 꽤 든다.
- 무엇이 세지는지는 EFFECTS. 실제 효과는 events.py (특기) · omikuji.py (레밀리아) 에서 level() 로 읽는다.
"""
from __future__ import annotations

from .state import GameState

MAX_LV = 10
BASE_COST = 5_000
COOL_STEP = 0.04          # 레벨마다 쿨타임 -4%

# 친구 → (특기 이름, 레벨이 오르면 좋아지는 것)
EFFECTS: dict[str, tuple[str, str]] = {
    "reimu": ("마당 쓸기", "쓸 때마다 새전 (분당 수입 × 10%·Lv)"),
    "marisa": ("빌려 가기", "붙잡았을 때 돌려받는 보너스 +10%p·Lv"),
    "cirno": ("얼음 던지기", "얼음 조각을 팔아 새전 (분당 수입 × 5%·Lv)"),
    "sakuya": ("시간 정지", "멈추는 시간 +0.5초·Lv"),
    "sanae": ("기적", "기적 새전 + 분당 수입 × 30%·Lv"),
    "remilia": ("운명 조작", "조작된 오미쿠지 보상 +5%·Lv, Lv.5 부터 대길만"),
    "flandre": ("레바테인", "날려 보내는 범위 +20px·Lv"),
    "youmu": ("정원 손질", "손질 새전 +50%·Lv"),
    "meiling": ("문지기", "도둑을 막는 확률 +3%p·Lv, 덜 졺"),
}


def level(s: GameState, key: str) -> int:
    return max(1, min(MAX_LV, int(s.skill_lv.get(key, 1))))


def bonus(s: GameState, key: str) -> int:
    """Lv.1 보다 몇 단계 위인지 (효과 계산용)."""
    return level(s, key) - 1


def cost(s: GameState, key: str) -> int | None:
    """다음 레벨로 올리는 값 (이미 Lv.10 이면 None)."""
    lv = level(s, key)
    return None if lv >= MAX_LV else BASE_COST * 2 ** (lv - 1)


def cooldown_scale(s: GameState, key: str) -> float:
    return 1 - COOL_STEP * bonus(s, key)


def blocked(s: GameState, key: str) -> str:
    if key not in EFFECTS:
        return "특기가 없어요"
    if key not in s.unlocked:
        return "아직 만나지 않은 친구예요"
    c = cost(s, key)
    if c is None:
        return "이미 최고 레벨이에요"
    if s.saisen < c:
        return f"새전이 {c - s.saisen:,} 모자라요"
    return ""


def train(s: GameState, key: str) -> int | None:
    """한 단계 수련 → 새 레벨 (못 하면 None)."""
    if blocked(s, key):
        return None
    s.saisen -= cost(s, key)
    s.skill_lv[key] = level(s, key) + 1
    return s.skill_lv[key]


def spent(s: GameState) -> int:
    """지금까지 수련에 쓴 새전."""
    return sum(BASE_COST * (2 ** (level(s, k) - 1) - 1) for k in EFFECTS)
