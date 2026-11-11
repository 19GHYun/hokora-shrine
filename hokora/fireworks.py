# -*- coding: utf-8 -*-
"""불꽃놀이 봉납: 새전을 넣고 작업표시줄 위 하늘에 불꽃을 쏘아 올린다. 효과는 없는 순수한 구경거리.

- 소 · 중 · 대 · 특대: 클수록 더 많이, 더 오래, 더 화려하게. 마지막엔 한꺼번에 터지는 피날레.
- 특대는 피날레 뒤 하늘에 「奉納」 글자.
- 친구들은 올려다보며 "타~마야~!" "카~기야~!" (일본 불꽃놀이 구호).
창은 신사 위쪽 하늘 (화면을 다 덮지 않게 — 전체화면으로 잘못 알아보지 않도록), 클릭은 뒤로 통과.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from .state import GameState


@dataclass(frozen=True)
class Show:
    key: str
    name: str
    price: int
    shells: int          # 쏘는 발 수
    seconds: float       # 전체 길이


SIZES: dict[str, Show] = {
    "s": Show("s", "소", 1_000, 10, 12.0),
    "m": Show("m", "중", 5_000, 24, 22.0),
    "l": Show("l", "대", 20_000, 48, 35.0),
    "xl": Show("xl", "특대", 100_000, 90, 55.0),
}
CHEERS = ["타~마야~!", "카~기야~!", "와아~ 예쁘다!", "또 올라간다!", "우와아~!"]
RISE = 0.9               # 불꽃이 올라가는 시간
LIFE = 2.4               # 터진 뒤 사라질 때까지
FINALE = 0.2             # 마지막 20% 시간에 발 수의 35% 를 몰아서
TEXT_TIME = 5.0          # 특대: 「奉納」 글자가 떠 있는 시간


def blocked(s: GameState, key: str, running: bool = False) -> str:
    if key not in SIZES:
        return "없는 불꽃이에요"
    if running:
        return "불꽃놀이가 끝나면 또 쏠 수 있어요"
    if s.saisen < SIZES[key].price:
        return f"새전이 {SIZES[key].price - s.saisen:,} 모자라요"
    return ""


def pay(s: GameState, key: str) -> bool:
    if blocked(s, key):
        return False
    s.saisen -= SIZES[key].price
    s.fireworks += 1
    s.fireworks_spent += SIZES[key].price
    return True


def schedule(show: Show, rng: random.Random) -> list[float]:
    """발마다 쏘는 시각 (초). 앞쪽은 고르게, 마지막엔 몰아서 피날레."""
    end = show.seconds - LIFE - RISE - (TEXT_TIME if show.key == "xl" else 0.0)
    finale_n = max(2, round(show.shells * 0.35))
    main_n = show.shells - finale_n
    finale_at = end * (1 - FINALE)
    times = [finale_at * (i + rng.uniform(0.1, 0.9)) / max(1, main_n) for i in range(main_n)]
    times += [finale_at + rng.uniform(0, end - finale_at) for _ in range(finale_n)]
    return sorted(times)


class FireworksShow(QWidget):
    """작업표시줄 바로 위 하늘에 뜨는 불꽃놀이. 다 쏘고 나면 스스로 닫힌다."""

    PALETTE = [0.0, 0.08, 0.14, 0.33, 0.55, 0.62, 0.78, 0.9]     # 빨강 · 주황 · 금 · 초록 · 하늘 · 파랑 · 보라 · 분홍

    def __init__(self, show: Show, area: QRect, center_x: float, text: str = "",
                 hidden: Callable[[], bool] | None = None, on_burst: Callable[[int], None] | None = None,
                 rng: random.Random | None = None, big: str = "奉納"):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.show_ = show
        self.text = text
        self.big = big                       # 특대 끝에 뜨는 큰 글자 (새해엔 「謹賀新年」)
        self.hidden = hidden or (lambda: False)
        self.on_burst = on_burst
        self.rng = rng or random.Random()
        w = min(area.width(), 1400)
        h = min(560, int(area.height() * 0.55))
        x = int(min(max(center_x - w / 2, area.left()), area.right() - w + 1))
        self.setGeometry(x, area.bottom() - h + 1, w, h)
        self.shells: list[dict] = []
        for t in schedule(show, self.rng):
            kind = self.rng.choices(("peony", "willow", "ring", "chrys"), weights=(4, 2, 2, 3))[0]
            self.shells.append({
                "t": t, "x": self.rng.uniform(w * 0.1, w * 0.9), "y": self.rng.uniform(h * 0.12, h * 0.5),
                "hue": self.rng.choice(self.PALETTE), "kind": kind,
                "n": self.rng.randint(28, 44) if show.key in ("l", "xl") else self.rng.randint(20, 32),
                "r": self.rng.uniform(70, 120) * (1.25 if show.key == "xl" else 1.0),
                "burst": False})
        self.started = time.monotonic()
        self.bursts = 0
        self.timer = QTimer(self, timeout=self._tick, interval=40)
        self.timer.start()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    @property
    def done(self) -> bool:
        return self.elapsed >= self.show_.seconds

    def _tick(self) -> None:
        t = self.elapsed
        if t >= self.show_.seconds:
            self.timer.stop()
            self.close()
            return
        for sh in self.shells:
            if not sh["burst"] and t >= sh["t"] + RISE:
                sh["burst"] = True
                self.bursts += 1
                if self.on_burst:
                    self.on_burst(self.bursts)
        if self.hidden():                                   # 전체화면 게임 중엔 숨김 (시간은 그대로 흐름)
            if self.isVisible():
                self.hide()
            return
        if not self.isVisible():
            self.show()
        self.update()

    # ── 그리기 ──
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.elapsed
        h = self.height()
        for sh in self.shells:
            age = t - sh["t"]
            if age < 0 or age > RISE + LIFE:
                continue
            if age < RISE:                                      # 올라가는 불꽃 (꼬리)
                u = age / RISE
                ease = 1 - (1 - u) ** 2
                y = h - (h - sh["y"]) * ease
                p.setPen(QPen(QColor(255, 230, 180, 150), 2))
                p.drawLine(QPointF(sh["x"], y), QPointF(sh["x"], min(h, y + 26)))
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 245, 220))
                p.drawEllipse(QPointF(sh["x"], y), 2.6, 2.6)
                continue
            self._burst(p, sh, age - RISE)
        if self.show_.key == "xl" and self.text:
            self._text(p, t)
        p.end()

    def _burst(self, p: QPainter, sh: dict, a: float) -> None:
        fade = max(0.0, 1 - a / LIFE)
        spread = 1 - math.exp(-a * 3.2)                        # 확 퍼졌다가 느려짐
        fall = 26 * a * a                                       # 중력
        n, r, x0, y0 = sh["n"], sh["r"], sh["x"], sh["y"]
        if a < 0.25:                                            # 터지는 순간 번쩍
            g = QRadialGradient(QPointF(x0, y0), r * 0.7)
            g.setColorAt(0, QColor(255, 255, 240, int(150 * (1 - a / 0.25))))
            g.setColorAt(1, QColor(255, 255, 240, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(QPointF(x0, y0), r * 0.7, r * 0.7)
        kind = sh["kind"]
        p.setPen(Qt.NoPen)
        for i in range(n):
            ang = i / n * math.tau + sh["t"]
            dist = r * spread * (1.0 if kind == "ring" else 0.75 + 0.25 * math.sin(i * 2.7))
            px, py = x0 + math.cos(ang) * dist, y0 + math.sin(ang) * dist + fall
            if kind == "willow":                                # 금빛 버들
                hue, sat = 0.11, 0.7
            else:                                               # 두 가지 색이 섞이게
                hue, sat = (sh["hue"] + (0.08 if i % 2 else 0.0)) % 1.0, 0.85
            if kind in ("willow", "chrys"):                     # 꼬리를 끄는 불꽃
                tail = 0.55 if kind == "willow" else 0.35
                bx = x0 + math.cos(ang) * dist * (1 - tail)
                by = y0 + math.sin(ang) * dist * (1 - tail) + fall * (1 - tail)
                p.setPen(QPen(QColor.fromHsvF(hue, sat * 0.8, 1.0, fade * 0.8), 2.0, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(bx, by), QPointF(px, py))
                p.setPen(Qt.NoPen)
            if fade < 0.35 and (i + int(a * 20)) % 3 == 0:     # 사라질 때 반짝반짝
                continue
            size = 3.2 if kind != "willow" else 2.4
            p.setBrush(QColor.fromHsvF(hue, sat, 1.0, fade * 0.28))     # 번지는 빛
            p.drawEllipse(QPointF(px, py), size * 2.4, size * 2.4)
            p.setBrush(QColor.fromHsvF(hue, sat * 0.6, 1.0, fade))      # 가운데는 밝게
            p.drawEllipse(QPointF(px, py), size, size)

    def _text(self, p: QPainter, t: float) -> None:
        """특대 마지막: 하늘에 「奉納」 + 신사 이름."""
        start = self.show_.seconds - TEXT_TIME - 0.5
        u = (t - start) / TEXT_TIME
        if not 0 <= u <= 1:
            return
        alpha = min(1.0, u / 0.15, (1 - u) / 0.2)
        w, h = self.width(), self.height()
        big = QFont("Yu Gothic UI")
        big.setBold(True)
        big.setPixelSize(int(min(h * 0.32, 150)))
        path = QPainterPath()
        path.addText(0, 0, big, self.big)
        br = path.boundingRect()
        path.translate(w / 2 - br.center().x(), h * 0.42 - br.center().y())
        glow = QColor(255, 210, 120, int(90 * alpha))
        for width in (14, 8):
            p.setPen(QPen(glow, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        p.setPen(QPen(QColor(255, 255, 255, int(200 * alpha)), 2))
        p.setBrush(QColor(255, 236, 170, int(255 * alpha)))
        p.drawPath(path)
        small = QFont("Malgun Gothic")
        small.setBold(True)
        small.setPixelSize(int(min(h * 0.07, 30)))
        p.setFont(small)
        p.setPen(QColor(255, 245, 225, int(230 * alpha)))
        p.drawText(QRectF(0, h * 0.42 + br.height() / 2 + 6, w, h * 0.12), Qt.AlignHCenter | Qt.AlignTop, self.text)
