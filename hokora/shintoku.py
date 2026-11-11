# -*- coding: utf-8 -*-
"""신덕(神徳): 식년천궁을 할 때마다 쌓이는 점수로 신사를 영구히 강화한다.

- n대째 신사를 다 지으면 신덕 n점 (2대째 → 2점, 14대째 → 14점). 점수는 천궁 횟수로 정해지므로
  이 기능이 생기기 전에 한 천궁도 그대로 들어온다.
- 강화마다 다음 레벨 값 = 지금 레벨 + 1점 (Lv.1 은 1점, Lv.2 는 2점 …). 다 찍으려면 30대째쯤.
- 다시 나누기: 다음 천궁 값의 10% 새전을 내면 찍은 점수를 모두 돌려받는다.
실제 효과는 각 모듈(prayer·diary·guests·omikuji·expedition·incident·sengu·fishing)이 여기 함수로 읽는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .state import GameState

RESET_SHARE = 0.10        # 다시 나누기: 다음 천궁 값의 10%


@dataclass(frozen=True)
class Perk:
    key: str
    icon: str
    name: str
    max_lv: int
    desc: str                                  # 한 레벨마다 좋아지는 것
    effect: Callable[[int], str]               # 레벨 → 지금 효과 글


PERKS: dict[str, Perk] = {p.key: p for p in [
    Perk("harvest", "🌾", "풍요", 20, "새전 수입 +3%", lambda lv: f"새전 수입 +{3 * lv}%"),
    Perk("box", "🏺", "새전함", 10, "꺼 둔 동안 모으는 새전 +15% · 최대 시간 +1시간",
         lambda lv: f"꺼 둔 동안 +{15 * lv}%·+{lv}시간"),
    Perk("guests", "🎐", "참배객", 10, "손님이 올 확률 +8%", lambda lv: f"손님 +{8 * lv}%"),
    Perk("fortune", "🎋", "운세", 10, "오미쿠지 새전 + 분당 수입 × 10분",
         lambda lv: f"오미쿠지 +수입 {10 * lv}분치"),
    Perk("journey", "🗺", "원정", 10, "원정 시간 -5%", lambda lv: f"원정 시간 -{5 * lv}%"),
    Perk("exorcism", "⚔", "퇴마", 10, "흑막 보상 +20% · 단서가 5% 더 자주",
         lambda lv: f"흑막 보상 +{20 * lv}%·단서 -{5 * lv}%"),
    Perk("carpenter", "🔨", "목수", 10, "천궁 값 -2% · 공사 시간 -5분",
         lambda lv: f"천궁 값 -{2 * lv}%·공사 -{5 * lv}분"),
    Perk("bait", "🎣", "미끼", 5, "하루 낚시 미끼 +3개", lambda lv: f"미끼 +{3 * lv}개"),
]}


# ── 점수 ──
def earned(s: GameState) -> int:
    """지금까지 받은 신덕 = 2 + 3 + … + (지금 대수). 천궁을 안 했으면 0."""
    g = s.sengu + 1
    return g * (g + 1) // 2 - 1 if s.sengu > 0 else 0


def gain_for(generation: int) -> int:
    """n대째 신사를 다 지으면 받는 신덕."""
    return generation


def level(s: GameState, key: str) -> int:
    p = PERKS.get(key)
    return 0 if p is None else max(0, min(p.max_lv, int(s.perks.get(key, 0))))


def spent(s: GameState) -> int:
    return sum(lv * (lv + 1) // 2 for lv in (level(s, k) for k in PERKS))


def points(s: GameState) -> int:
    return max(0, earned(s) - spent(s))


def next_cost(s: GameState, key: str) -> int | None:
    """다음 레벨 값 (이미 최고면 None)."""
    lv = level(s, key)
    return None if lv >= PERKS[key].max_lv else lv + 1


def blocked(s: GameState, key: str) -> str:
    if key not in PERKS:
        return "없는 강화예요"
    c = next_cost(s, key)
    if c is None:
        return "이미 최고 레벨이에요"
    if points(s) < c:
        return "식년천궁으로 신덕을 모아요" if earned(s) == 0 else f"신덕이 {c - points(s)}점 모자라요"
    return ""


def buy(s: GameState, key: str) -> int | None:
    """한 레벨 올림 → 새 레벨 (못 올리면 None)."""
    if blocked(s, key):
        return None
    s.perks[key] = level(s, key) + 1
    return s.perks[key]


def reset_cost(s: GameState) -> int:
    from . import sengu
    return int(sengu.cost(s) * RESET_SHARE)


def reset_blocked(s: GameState) -> str:
    if not spent(s):
        return "아직 찍은 신덕이 없어요"
    if s.saisen < reset_cost(s):
        return f"새전이 {reset_cost(s) - s.saisen:,} 모자라요"
    return ""


def reset(s: GameState) -> bool:
    if reset_blocked(s):
        return False
    s.saisen -= reset_cost(s)
    s.perks = {}
    s.perk_resets += 1
    return True


# ── 효과 (각 모듈이 읽음) ──
def income_mult(s: GameState) -> float:
    return 1 + 0.03 * level(s, "harvest")


def offline_mult(s: GameState) -> float:
    return 1 + 0.15 * level(s, "box")


def offline_hours(s: GameState) -> int:
    return level(s, "box")


def guest_mult(s: GameState) -> float:
    return 1 + 0.08 * level(s, "guests")


def omikuji_bonus(s: GameState) -> int:
    return s.income_per_min * 10 * level(s, "fortune")


def journey_scale(s: GameState) -> float:
    return 1 - 0.05 * level(s, "journey")


def boss_mult(s: GameState) -> float:
    return 1 + 0.2 * level(s, "exorcism")


def clue_scale(s: GameState) -> float:
    return 1 - 0.05 * level(s, "exorcism")


def sengu_cost_scale(s: GameState) -> float:
    return 1 - 0.02 * level(s, "carpenter")


def build_cut(s: GameState) -> float:
    """천궁 공사 시간에서 빼는 초."""
    return 300.0 * level(s, "carpenter")


def extra_bait(s: GameState) -> int:
    return 3 * level(s, "bait")


# ── 신덕 창 ──
class ShintokuBoard(QWidget):
    """강화 목록. 누르면 on_buy(키) → 새 레벨, 다시 나누기는 on_reset() (두 번 눌러야 함)."""

    def __init__(self, s: GameState, on_buy: Callable[[str], object], on_reset: Callable[[], bool]):
        super().__init__(None, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

        from .panel import STYLE
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("panel")
        self.setStyleSheet(STYLE)
        self.setFixedWidth(520)
        self.s, self.on_buy, self.on_reset = s, on_buy, on_reset
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 16)
        v.setSpacing(6)
        v.addWidget(QLabel("✨  신덕(神徳)", objectName="title"))
        self.points_label = QLabel(objectName="sub")
        v.addWidget(self.points_label)
        tip = QLabel("식년천궁으로 n대째 신사를 지을 때마다 신덕 n점. 강화는 영구히 남고, "
                     "다음 레벨 값은 지금 레벨 + 1점이에요.", objectName="goal")
        tip.setWordWrap(True)
        v.addWidget(tip)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(5)
        self.rows: dict[str, tuple] = {}
        for row, (key, perk) in enumerate(PERKS.items()):
            name = QLabel(f"{perk.icon} {perk.name}", objectName="name")
            name.setToolTip(f"한 레벨마다: {perk.desc}")
            lv = QLabel(objectName="goal")
            now = QLabel(objectName="goal")
            now.setWordWrap(True)
            now.setToolTip(f"한 레벨마다: {perk.desc}")
            btn = QPushButton(objectName="small")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._buy(k))
            grid.addWidget(name, row, 0)
            grid.addWidget(lv, row, 1)
            grid.addWidget(now, row, 2)
            grid.addWidget(btn, row, 3)
            self.rows[key] = (lv, now, btn)
        grid.setColumnStretch(2, 1)
        v.addLayout(grid)
        bottom = QHBoxLayout()
        self.reset_label = QLabel(objectName="sub")
        self.reset_label.setWordWrap(True)
        self.reset_btn = QPushButton(objectName="ghost")
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.clicked.connect(self._reset)
        bottom.addWidget(self.reset_label, 1)
        bottom.addWidget(self.reset_btn)
        v.addLayout(bottom)
        self._armed = False
        self.refresh()

    def refresh(self) -> None:
        s = self.s
        self.points_label.setText(f"신덕 {points(s)}점   ·   지금까지 받은 신덕 {earned(s)}점")
        for key, (lv_label, now, btn) in self.rows.items():
            perk, lv = PERKS[key], level(s, key)
            lv_label.setText(f"Lv.{lv}/{perk.max_lv}")
            if lv >= perk.max_lv:
                now.setText(perk.effect(lv) + "  (최고)")
            else:
                now.setText((perk.effect(lv) + "  →  " if lv else "→  ") + perk.effect(lv + 1))
            cost = next_cost(s, key)
            why = blocked(s, key)
            btn.setText("최고" if cost is None else f"+1  ({cost}점)")
            btn.setEnabled(not why)
            btn.setToolTip(why or f"신덕 {cost}점으로 {perk.name} Lv.{lv + 1}")
        self.reset_label.setText(f"다시 나누기: 새전 {reset_cost(s):,} (다음 천궁 값의 10%)")
        why = reset_blocked(s)
        self.reset_btn.setText("정말요? 한 번 더" if self._armed else "다시 나누기")
        self.reset_btn.setEnabled(not why)
        self.reset_btn.setToolTip(why or "찍은 신덕을 모두 돌려받아요")

    def _buy(self, key: str) -> None:
        self._armed = False
        self.on_buy(key)
        self.refresh()

    def _reset(self) -> None:
        if not self._armed:                              # 실수로 누르지 않게 두 번
            self._armed = True
            QTimer.singleShot(3000, self._disarm)
        else:
            self._armed = False
            self.on_reset()
        self.refresh()

    def _disarm(self) -> None:
        if self._armed:
            self._armed = False
            self.refresh()

    def show_near(self, pos: QPoint) -> None:
        from PySide6.QtGui import QGuiApplication
        self.adjustSize()
        sc = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        area = sc.availableGeometry()
        x = min(max(pos.x() - self.width() // 2, area.left() + 8), area.right() - self.width() - 8)
        y = min(max(pos.y() - self.height() - 10, area.top() + 8), area.bottom() - self.height() - 8)
        self.move(x, y)
        self.show()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        p.setPen(QPen(QColor(184, 134, 11, 150), 1.2))
        p.setBrush(QColor(255, 250, 240, 250))
        p.drawPath(path)
        p.save()
        p.setClipPath(path)
        p.fillRect(QRectF(r.left(), r.top(), r.width(), 4), QColor("#D4A017"))   # 위쪽 금색 띠
        p.restore()
        p.end()
