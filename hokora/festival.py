# -*- coding: utf-8 -*-
"""예대제 (축제): 새전을 크게 내고 2시간 동안 신사 축제를 연다.

- 축제 동안: 새전 수입 ×2, 손님이 훨씬 자주 옴, 신사 위로 등롱 줄, 친구들이 가끔 다 같이 춤 (밤엔 불꽃놀이).
- 끝나면 참배객이 두고 간 새전(분당 수입 × 120)과 함께 축제 결산 카드.
- 한 번 열면 24시간 뒤에 다시 열 수 있다.
"""
from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from .state import GameState

DURATION = 2 * 3600
COOLDOWN = 24 * 3600
INCOME_BOOST = 2.0
GUEST_BOOST = 3.0
COST_PER = 300           # 비용 = 분당 수입 × 이만큼 (최소 3,000)
TIPS_PER = 120           # 끝날 때 참배객 새전 = 분당 수입 × 이만큼


def cost(s: GameState) -> int:
    return max(3000, int(round(s.income_per_min * COST_PER / 100)) * 100)


def active(s: GameState, now: float | None = None) -> bool:
    return s.festival_until > (now or time.time())


def left(s: GameState, now: float | None = None) -> float:
    return max(0.0, s.festival_until - (now or time.time()))


def blocked(s: GameState, now: float | None = None) -> str:
    """열 수 없는 이유 (열 수 있으면 빈 문자열)."""
    now = now or time.time()
    if active(s, now):
        return "축제 중이에요"
    if s.festival_next > now:
        h = (s.festival_next - now) / 3600
        return f"{h:.0f}시간 뒤에 다시 열 수 있어요" if h >= 1 else f"{(s.festival_next - now) / 60:.0f}분 뒤에 다시 열 수 있어요"
    if s.saisen < cost(s):
        return "새전이 모자라요"
    return ""


def hold(s: GameState, now: float | None = None) -> bool:
    now = now or time.time()
    if blocked(s, now):
        return False
    s.saisen -= cost(s)
    s.festival_until = now + DURATION
    s.festival_next = now + COOLDOWN
    s.festival_start_total = s.saisen_total
    s.festival_reported = False
    s.festivals += 1
    return True


def finish(s: GameState) -> tuple[int, int] | None:
    """끝난 축제를 정산 → (축제 동안 모인 새전, 참배객 새전). 정산할 게 없으면 None."""
    if s.festival_reported or not s.festival_until or active(s):
        return None
    s.festival_reported = True
    earned = max(0, s.saisen_total - s.festival_start_total)
    tips = max(500, s.income_per_min * TIPS_PER)
    s.add_saisen(tips)
    return earned, tips


class FestivalFx(QWidget):
    """신사 위로 걸린 등롱 줄과 (밤엔) 불꽃놀이. 클릭은 통과."""

    W, H = 900, 300

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(self.W, self.H)
        self.night = False
        self.rng = random.Random()
        self.bursts: list[list] = []          # [x, y, 나이, 색상, 조각 수]
        self.start = time.monotonic()
        self._pos = None
        self._next_burst = 0.0
        self.timer = QTimer(self, timeout=self._tick, interval=50)

    def follow(self, cx: float, ground: float) -> None:
        pos = (round(cx - self.W / 2), round(ground - self.H + 4))
        if pos != self._pos:
            self._pos = pos
            self.move(*pos)

    def showEvent(self, e) -> None:
        self.timer.start()
        super().showEvent(e)

    def hideEvent(self, e) -> None:
        self.timer.stop()
        super().hideEvent(e)

    def _tick(self) -> None:
        now = time.monotonic()
        for b in self.bursts:
            b[2] += 0.05
        self.bursts = [b for b in self.bursts if b[2] < 1.6]
        if self.night and now >= self._next_burst:
            self._next_burst = now + self.rng.uniform(1.2, 3.0)
            self.bursts.append([self.rng.uniform(120, self.W - 120), self.rng.uniform(30, 90), 0.0,
                                self.rng.random(), self.rng.randint(14, 22)])
        self.update()

    def _rope(self, x: float) -> float:
        """등롱 줄의 높이 (가운데가 처진 줄)."""
        t = (x - 40) / (self.W - 80)
        return 120 + math.sin(t * math.pi) * 34

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = time.monotonic() - self.start
        for x, y, age, hue, n in self.bursts:            # 불꽃놀이
            a = max(0.0, 1 - age / 1.6)
            r = 10 + age * 55
            for i in range(n):
                ang = i / n * math.tau
                c = QColor.fromHsvF((hue + i * 0.02) % 1.0, 0.55, 1.0, a)
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                p.drawEllipse(QPointF(x + math.cos(ang) * r, y + math.sin(ang) * r + age * 12), 2.2, 2.2)
        rope = QPainterPath()                             # 줄
        rope.moveTo(40, self._rope(40))
        for x in range(40, self.W - 39, 10):
            rope.lineTo(x, self._rope(x))
        p.setPen(QPen(QColor(90, 60, 40, 200), 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawPath(rope)
        f = QFont("Malgun Gothic", 7)
        f.setBold(True)
        p.setFont(f)
        for i, x in enumerate(range(70, self.W - 60, 56)):   # 등롱 (빨강·하양 번갈아)
            sway = math.sin(t * 1.6 + i) * 2
            y = self._rope(x) + 4
            red = i % 2 == 0
            if self.night:
                g = QRadialGradient(QPointF(x + sway, y + 16), 26)
                g.setColorAt(0, QColor(255, 200, 110, 120))
                g.setColorAt(1, QColor(255, 200, 110, 0))
                p.setPen(Qt.NoPen)
                p.setBrush(g)
                p.drawEllipse(QPointF(x + sway, y + 16), 26, 26)
            p.setPen(QPen(QColor(60, 40, 30), 1.2))
            p.setBrush(QColor("#E0313F") if red else QColor("#FFF6E8"))
            p.drawRoundedRect(QRectF(x - 9 + sway, y + 4, 18, 24), 8, 8)
            p.setBrush(QColor(50, 36, 30))
            p.drawRect(QRectF(x - 6 + sway, y + 1, 12, 4))
            p.drawRect(QRectF(x - 6 + sway, y + 27, 12, 3))
            p.setPen(QColor("#FFFFFF") if red else QColor("#C8102E"))
            p.drawText(QRectF(x - 9 + sway, y + 6, 18, 20), Qt.AlignCenter, "祭")
        p.end()
