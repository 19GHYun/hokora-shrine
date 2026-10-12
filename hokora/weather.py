# -*- coding: utf-8 -*-
"""天候 (날씨) — 동방 비상천칙처럼 몇 시간마다 날씨가 바뀌고, 날씨마다 효과가 있다.

- 쾌청: 새전 수입 ×1.2          - 흐림: 평범한 날
- 안개비: 요정들이 장난치러 오기 좋은 날 (손님 중 세 요정이 잘 옴)
- 여우비: 오미쿠지 대길·중길이 잘 나옴
- 풍우: 가끔 센 바람에 친구가 날아감
- 짙은 안개: 손님이 자주 옴
- 오로라: 아주 드문 날. 새전 수입 ×2

날씨는 날짜·시간대(3시간)로 정해져서, 껐다 켜도 같은 시간대엔 같은 날씨.
시험용: HOKORA_WEATHER=clear|cloudy|drizzle|sunshower|storm|fog|aurora
"""
from __future__ import annotations

import math
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

SLOT_HOURS = 3


@dataclass(frozen=True)
class Weather:
    key: str
    icon: str
    name: str
    kanji: str
    desc: str
    weight: float
    income: float = 1.0       # 새전 수입 배수
    guests: float = 1.0       # 손님 방문 확률 배수
    lucky: bool = False       # 오미쿠지 대길·중길 2배


WEATHERS = {w.key: w for w in [
    Weather("clear", "☀", "쾌청", "快晴", "새전 수입 ×1.2", 25, income=1.2),
    Weather("cloudy", "☁", "흐림", "曇天", "평범한 하루", 25),
    Weather("drizzle", "🌦", "안개비", "霧雨", "세 요정이 장난치러 오기 좋은 날", 14, guests=1.3),
    Weather("sunshower", "🌈", "여우비", "天気雨", "오미쿠지 대길·중길 확률 2배", 11, lucky=True),
    Weather("storm", "🌀", "풍우", "風雨", "가끔 센 바람에 친구가 날아가요", 10),
    Weather("fog", "🌫", "짙은 안개", "濃霧", "손님이 자주 와요 (방문 ×2)", 11, guests=2.0),
    Weather("aurora", "✨", "오로라", "極光", "아주 드문 날! 새전 수입 ×2", 4, income=2.0),
]}


def slot(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return f"{now:%Y-%m-%d}-{now.hour // SLOT_HOURS}"


_magic: tuple[str, float] = ("", 0.0)       # 파츄리의 날씨 마법: (날씨, 끝나는 시각 time.time)


def set_magic(key: str, until: float) -> None:
    global _magic
    _magic = (key, until) if key in WEATHERS else ("", 0.0)


def magic_left() -> float:
    """날씨 마법이 남은 초 (없으면 0)."""
    return max(0.0, _magic[1] - time.time()) if _magic[0] else 0.0


def current(now: datetime | None = None) -> Weather:
    forced = os.environ.get("HOKORA_WEATHER", "")
    if forced in WEATHERS:
        return WEATHERS[forced]
    if magic_left() > 0:
        return WEATHERS[_magic[0]]
    rng = random.Random(slot(now))
    ws = list(WEATHERS.values())
    return rng.choices(ws, weights=[w.weight for w in ws])[0]


def next_change(now: datetime | None = None) -> str:
    now = now or datetime.now()
    h = (now.hour // SLOT_HOURS + 1) * SLOT_HOURS
    return "자정" if h >= 24 else f"{h}시"


class WeatherFx(QWidget):
    """신사 둘레의 날씨 (비·안개·바람·오로라). 클릭은 뒤로 통과."""

    W, H = 760, 300

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(self.W, self.H)
        self.kind = ""
        self.rng = random.Random()
        self.drops: list[list[float]] = []
        self.start = time.monotonic()
        self._last = self.start
        self._pos = None
        self.timer = QTimer(self, timeout=self._tick, interval=50)

    @staticmethod
    def wants(kind: str) -> bool:
        return kind in ("drizzle", "sunshower", "storm", "fog", "aurora")

    def set_kind(self, kind: str) -> None:
        if kind != self.kind:
            self.kind = kind
            self.drops.clear()
            self.update()

    def follow(self, cx: float, ground: float) -> None:
        pos = (round(cx - self.W / 2), round(ground - self.H + 4))
        if pos != self._pos:
            self._pos = pos
            self.move(*pos)

    def showEvent(self, e) -> None:
        self._last = time.monotonic()
        self.timer.start()
        super().showEvent(e)

    def hideEvent(self, e) -> None:
        self.timer.stop()
        super().hideEvent(e)

    def _rain(self) -> tuple[int, float, float]:
        """(빗줄기 수, 떨어지는 속도, 옆으로 기울기)."""
        return {"drizzle": (26, 260.0, 30.0), "sunshower": (16, 320.0, 15.0), "storm": (40, 520.0, 260.0)}.get(
            self.kind, (0, 0.0, 0.0))

    def _tick(self) -> None:
        now = time.monotonic()
        dt, self._last = min(now - self._last, 0.2), now
        n, vy, vx = self._rain()
        while len(self.drops) < n:
            self.drops.append([self.rng.uniform(-80, self.W), self.rng.uniform(-self.H, 0), self.rng.uniform(0.7, 1.2)])
        for d in self.drops:
            d[0] += vx * d[2] * dt
            d[1] += vy * d[2] * dt
            if d[1] > self.H - 4 or d[0] > self.W + 20:
                d[0], d[1] = self.rng.uniform(-80, self.W), self.rng.uniform(-60, -5)
        self.update()

    def _edge(self, x: float) -> float:
        return max(0.0, min(1.0, x / 90, (self.W - x) / 90))

    def paintEvent(self, _e) -> None:
        if not self.kind:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = time.monotonic() - self.start
        if self.kind == "fog":
            for i in range(7):
                x = (i * 137 + t * (14 + i * 3)) % (self.W + 300) - 150
                y = self.H - 40 - (i % 3) * 32
                g = QRadialGradient(QPointF(x, y), 130)
                a = int(70 * self._edge(min(max(x, 0), self.W)) + 20)
                g.setColorAt(0, QColor(236, 238, 244, a))
                g.setColorAt(1, QColor(236, 238, 244, 0))
                p.setPen(Qt.NoPen)
                p.setBrush(g)
                p.drawEllipse(QPointF(x, y), 150, 60)
        elif self.kind == "aurora":
            for i, (hue, off) in enumerate(((0.38, 0.0), (0.5, 1.7), (0.8, 3.1))):
                path_y = 50 + i * 22
                for x in range(0, self.W, 6):
                    wave = math.sin(x / 70 + t * 0.6 + off) * 14 + math.sin(x / 31 + t * 0.9) * 5
                    a = self._edge(x) * (0.55 + 0.45 * math.sin(t * 0.8 + x / 120 + off))
                    g = QLinearGradient(0, path_y + wave - 40, 0, path_y + wave + 30)
                    c = QColor.fromHsvF(hue, 0.6, 1.0, 0.0)
                    g.setColorAt(0, c)
                    c.setAlphaF(0.32 * a)
                    g.setColorAt(0.6, c)
                    c.setAlphaF(0.0)
                    g.setColorAt(1, c)
                    p.fillRect(QRectF(x, path_y + wave - 40, 6, 70), g)
        else:
            n, vy, vx = self._rain()
            if self.kind == "sunshower":                       # 여우비: 햇살 + 작은 무지개
                g = QRadialGradient(QPointF(self.W * 0.7, -20), 260)
                g.setColorAt(0, QColor(255, 236, 170, 60))
                g.setColorAt(1, QColor(255, 236, 170, 0))
                p.fillRect(self.rect(), g)
                for i, hue in enumerate((0.0, 0.08, 0.16, 0.33, 0.55, 0.75)):
                    c = QColor.fromHsvF(hue, 0.5, 1.0, 0.16)
                    p.setPen(QPen(c, 4))
                    r = 200 - i * 5
                    p.drawArc(QRectF(self.W * 0.62 - r, self.H - 40 - r, r * 2, r * 2), 30 * 16, 120 * 16)
            for x, y, k in self.drops:
                a = self._edge(x) * min(1.0, (y + 40) / 60) * 0.8
                if a <= 0:
                    continue
                ln = (9 if self.kind != "storm" else 16) * k
                dx = ln * vx / max(1.0, vy)
                p.setPen(QPen(QColor(180, 200, 235, int(200 * a)), 1.2 if self.kind != "storm" else 1.5))
                p.drawLine(QPointF(x, y), QPointF(x - dx, y - ln))
            if self.kind == "storm":                           # 바람 줄기
                for i in range(3):
                    x = (t * 380 + i * 280) % (self.W + 200) - 100
                    y = 60 + i * 60 + math.sin(t + i) * 10
                    p.setPen(QPen(QColor(255, 255, 255, int(110 * self._edge(min(max(x, 0), self.W)))), 2))
                    p.drawArc(QRectF(x, y, 120, 26), 0, 150 * 16)
        # 창 테두리가 보이지 않게 네 가장자리를 부드럽게 지움
        p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        for horizontal in (True, False):
            g = QLinearGradient(0, 0, self.W, 0) if horizontal else QLinearGradient(0, 0, 0, self.H)
            g.setColorAt(0, QColor(0, 0, 0, 0))
            g.setColorAt(0.14, QColor(0, 0, 0, 255))
            g.setColorAt(0.86 if horizontal else 1.0, QColor(0, 0, 0, 255))
            if horizontal:
                g.setColorAt(1, QColor(0, 0, 0, 0))
            p.fillRect(self.rect(), g)
        p.end()
