# -*- coding: utf-8 -*-
"""캐릭터 해금 조건. 조건을 채우면 그 캐릭터가 신사로 찾아온다."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .state import GameState


@dataclass(frozen=True)
class Goal:
    text: str                                   # 도감에 보여줄 조건
    current: Callable[[GameState], float]       # 지금 값
    target: float                               # 목표 값
    unit: str = ""

    def ratio(self, s: GameState) -> float:
        return min(1.0, self.current(s) / self.target) if self.target else 1.0

    def done(self, s: GameState) -> bool:
        return self.current(s) >= self.target

    def label(self, s: GameState) -> str:
        cur = min(self.current(s), self.target)
        return f"{self.text}  {_fmt(cur, self.unit, bare=True)} / {_fmt(self.target, self.unit)}"


@dataclass(frozen=True)
class Unlock:
    key: str
    arrive_line: str        # 찾아올 때 말풍선
    goals: tuple[Goal, ...]  # 모두 채워야 해금

    def done(self, s: GameState) -> bool:
        return all(g.done(s) for g in self.goals)


def _fmt(v: float, unit: str, bare: bool = False) -> str:
    """bare=True 면 단위 없이 숫자만 (앞쪽 값: "0 / 50번")."""
    if unit == "시간":
        return f"{v / 3600:.1f}" if bare else f"{v / 3600:.1f}시간"
    return f"{int(v):,}" if bare else f"{int(v):,}{unit}"


UNLOCKS: dict[str, Unlock] = {
    "reimu": Unlock("reimu", "", ()),
    "marisa": Unlock(
        "marisa", "새전 냄새를 맡고 마리사가 찾아왔다!",
        (Goal("새전 모으기", lambda s: s.saisen_total, 100),)),
    "cirno": Unlock(
        "cirno", "재밌어 보여서 치르노가 놀러 왔다!",
        (Goal("쓰다듬기", lambda s: s.pats, 50, "번"),)),
    "sakuya": Unlock(
        "sakuya", "제대로 된 신사가 생겨서 사쿠야가 들렀다.",
        (Goal("신사 키우기", lambda s: s.shrine_level, 2, "단계"),
         Goal("함께한 시간", lambda s: s.runtime_sec, 2 * 3600, "시간"))),
}


def newly_unlocked(s: GameState) -> list[str]:
    """조건을 채웠지만 아직 안 온 캐릭터들."""
    return [k for k, u in UNLOCKS.items() if k not in s.unlocked and u.done(s)]
