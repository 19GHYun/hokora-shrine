# -*- coding: utf-8 -*-
"""계절·밤 연출.

- 신사 둘레에 계절 따라 봄엔 벚꽃잎, 가을엔 단풍잎, 겨울엔 눈이 흩날리고, 여름밤엔 반딧불이 날아다닌다.
  신사 주변의 작은 창에서만 그리므로(클릭은 통과) 일에 방해되지 않고 CPU 도 거의 안 쓴다.
- 밤(저녁 7시~새벽 5시)엔 신사가 푸르스름해지고 등불이 켜진다.
- 설날(1월 1~3일)은 새해 첫 참배: 새전 수입 2배.

시험용 환경변수: HOKORA_SEASON=spring|summer|autumn|winter, HOKORA_NIGHT=1|0
"""
from __future__ import annotations

import math
import os
import random
import time
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

SEASON_OF_MONTH = {3: "spring", 4: "spring", 5: "spring", 6: "summer", 7: "summer", 8: "summer",
                   9: "autumn", 10: "autumn", 11: "autumn", 12: "winter", 1: "winter", 2: "winter"}
SEASON_NAME = {"spring": "봄", "summer": "여름", "autumn": "가을", "winter": "겨울"}
NIGHT_FROM, NIGHT_TO = 19, 5          # 연출용 밤 (레밀리아의 밤 조건과는 따로)
NEW_YEAR_BOOST = 2
LEAF_COLORS = ["#E8742A", "#D9412E", "#F2B233", "#C4561F"]


def season(now: datetime | None = None) -> str:
    forced = os.environ.get("HOKORA_SEASON", "")
    if forced in SEASON_NAME:
        return forced
    return SEASON_OF_MONTH[(now or datetime.now()).month]


def is_night(now: datetime | None = None) -> bool:
    forced = os.environ.get("HOKORA_NIGHT", "")
    if forced in ("0", "1"):
        return forced == "1"
    h = (now or datetime.now()).hour
    return h >= NIGHT_FROM or h < NIGHT_TO


def is_new_year(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    return now.month == 1 and now.day <= 3


def fx_kind(now: datetime | None = None) -> str:
    """지금 흩날릴 것: petal / leaf / snow / firefly / "" (여름 낮은 없음)."""
    s = season(now)
    if s == "summer":
        return "firefly" if is_night(now) else ""
    return {"spring": "petal", "autumn": "leaf", "winter": "snow"}[s]


# ── 그리기 (사진 찍기에서도 씀) ──
def draw_petal(p: QPainter, x: float, y: float, size: float, angle: float, alpha: float) -> None:
    p.save()
    p.translate(x, y)
    p.rotate(angle)
    path = QPainterPath()
    path.moveTo(0, -size)
    path.cubicTo(size * 0.9, -size * 0.6, size * 0.6, size * 0.8, 0, size * 0.55)
    path.cubicTo(-size * 0.6, size * 0.8, -size * 0.9, -size * 0.6, 0, -size)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 183, 206, int(235 * alpha)))
    p.drawPath(path)
    p.restore()


def draw_leaf(p: QPainter, x: float, y: float, size: float, angle: float, alpha: float, color: str) -> None:
    p.save()
    p.translate(x, y)
    p.rotate(angle)
    path = QPainterPath()
    path.moveTo(0, -size * 1.2)
    path.cubicTo(size * 0.95, -size * 0.5, size * 0.7, size * 0.7, 0, size)
    path.cubicTo(-size * 0.7, size * 0.7, -size * 0.95, -size * 0.5, 0, -size * 1.2)
    c = QColor(color)
    c.setAlphaF(alpha * 0.95)
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawPath(path)
    vein = QColor(120, 50, 20, int(120 * alpha))
    p.setPen(QPen(vein, 0.8))
    p.drawLine(QPointF(0, -size * 0.9), QPointF(0, size * 1.3))       # 잎맥 + 꼭지
    p.restore()


def draw_snow(p: QPainter, x: float, y: float, size: float, alpha: float) -> None:
    p.setPen(QPen(QColor(150, 175, 215, int(170 * alpha)), 0.8))
    p.setBrush(QColor(255, 255, 255, int(240 * alpha)))
    p.drawEllipse(QPointF(x, y), size, size)


def draw_firefly(p: QPainter, x: float, y: float, glow: float) -> None:
    g = QRadialGradient(QPointF(x, y), 11)
    g.setColorAt(0, QColor(236, 255, 150, int(230 * glow)))
    g.setColorAt(0.25, QColor(200, 245, 110, int(140 * glow)))
    g.setColorAt(1, QColor(180, 240, 90, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(QPointF(x, y), 11, 11)


def scatter(p: QPainter, kind: str, rect: QRectF, count: int, rng: random.Random) -> None:
    """사진 배경에 계절 입자를 흩뿌림 (멈춘 장면)."""
    for _ in range(count):
        x, y = rng.uniform(rect.left(), rect.right()), rng.uniform(rect.top(), rect.bottom())
        if kind == "petal":
            draw_petal(p, x, y, rng.uniform(4, 7), rng.uniform(0, 360), 0.9)
        elif kind == "leaf":
            draw_leaf(p, x, y, rng.uniform(4, 6.5), rng.uniform(0, 360), 0.95, rng.choice(LEAF_COLORS))
        elif kind == "snow":
            draw_snow(p, x, y, rng.uniform(1.6, 3.2), 0.95)
        elif kind == "firefly":
            draw_firefly(p, x, y, rng.uniform(0.5, 1.0))


class SeasonFx(QWidget):
    """신사 둘레의 흩날림 창. 신사를 따라다니고, 클릭은 뒤로 통과한다."""

    W, H = 720, 280
    COUNT = {"petal": 9, "leaf": 7, "snow": 13, "firefly": 7}

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(self.W, self.H)
        self.kind = ""
        self.parts: list[dict] = []
        self.rng = random.Random()
        self._last = time.monotonic()
        self._spawn_at = 0.0
        self._pos = None
        self.timer = QTimer(self, timeout=self._tick, interval=66)   # 15fps 면 충분

    def set_kind(self, kind: str) -> None:
        if kind != self.kind:
            self.kind = kind
            self.parts.clear()
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

    def _spawn(self) -> dict:
        r = self.rng
        if self.kind == "firefly":
            return {"x": r.uniform(40, self.W - 40), "y": r.uniform(self.H * 0.35, self.H - 20),
                    "vx": r.uniform(-12, 12), "vy": r.uniform(-8, 8), "age": 0.0, "life": r.uniform(7, 13),
                    "ph": r.uniform(0, 6.28)}
        speed = {"petal": (28, 50), "leaf": (30, 55), "snow": (18, 34)}[self.kind]
        return {"x0": r.uniform(0, self.W), "y": -10.0, "vy": r.uniform(*speed), "sway": r.uniform(10, 28),
                "ph": r.uniform(0, 6.28), "size": r.uniform(4, 7) if self.kind != "snow" else r.uniform(2.0, 3.6),
                "spin": r.uniform(-90, 90), "rest": 0.0, "color": r.choice(LEAF_COLORS), "age": 0.0}

    def _tick(self) -> None:
        now = time.monotonic()
        dt, self._last = min(now - self._last, 0.2), now
        if not self.kind:
            return
        target = self.COUNT[self.kind]
        if len(self.parts) < target and now >= self._spawn_at:
            self.parts.append(self._spawn())
            self._spawn_at = now + self.rng.uniform(0.4, 1.2)
        ground = self.H - 6
        alive = []
        for pt in self.parts:
            pt["age"] += dt
            if self.kind == "firefly":
                pt["vx"] += self.rng.uniform(-20, 20) * dt
                pt["vy"] += self.rng.uniform(-20, 20) * dt
                pt["vx"], pt["vy"] = max(-18, min(18, pt["vx"])), max(-14, min(14, pt["vy"]))
                pt["x"] += pt["vx"] * dt
                pt["y"] = min(max(pt["y"] + pt["vy"] * dt, self.H * 0.25), self.H - 14)
                if pt["age"] < pt["life"]:
                    alive.append(pt)
                continue
            if pt["rest"]:                                   # 땅에 내려앉아 잠깐 있다가 사라짐
                pt["rest"] += dt
                if pt["rest"] < 2.0:
                    alive.append(pt)
                continue
            pt["y"] += pt["vy"] * dt
            if pt["y"] >= ground:
                pt["y"], pt["rest"] = ground, 1e-3
            alive.append(pt)
        self.parts = alive
        self.update()

    def _edge(self, x: float, y: float) -> float:
        """창 가장자리에서 옅어지게 (네모난 창 테두리가 보이지 않게)."""
        a = min(1.0, x / 70, (self.W - x) / 70)
        a = min(a, max(0.0, (y + 10) / 40))
        return max(0.0, a)

    def paintEvent(self, _e) -> None:
        if not self.parts:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for pt in self.parts:
            if self.kind == "firefly":
                life = pt["life"]
                fade = min(1.0, pt["age"] / 1.5, (life - pt["age"]) / 1.5)
                glow = (0.55 + 0.45 * math.sin(pt["age"] * 2.4 + pt["ph"])) * fade * self._edge(pt["x"], pt["y"])
                draw_firefly(p, pt["x"], pt["y"], max(0.0, glow))
                continue
            t = pt["age"]
            x = pt["x0"] + math.sin(t * 1.7 + pt["ph"]) * pt["sway"]
            if pt["rest"]:
                x = pt.setdefault("rest_x", x)
            a = self._edge(x, pt["y"]) * (1 - pt["rest"] / 2.0 if pt["rest"] else 1)
            if a <= 0:
                continue
            angle = t * pt["spin"] if not pt["rest"] else pt.setdefault("rest_a", t * pt["spin"])
            if self.kind == "petal":
                draw_petal(p, x, pt["y"], pt["size"], angle, a)
            elif self.kind == "leaf":
                draw_leaf(p, x, pt["y"], pt["size"], angle, a, pt["color"])
            else:
                draw_snow(p, x, pt["y"], pt["size"], a)
        p.end()


def night_glow(p: QPainter, w: float, h: float) -> None:
    """밤: 신사 그림을 푸르스름하게 물들이고 앞에 등불빛을 켬. 그림이 그려진 뒤에 부른다."""
    p.save()
    p.setCompositionMode(QPainter.CompositionMode_SourceAtop)      # 그림이 있는 곳만
    p.fillRect(QRectF(0, 0, w, h), QColor(28, 36, 96, 95))
    g = QRadialGradient(QPointF(w * 0.6, h * 0.72), w * 0.55)
    g.setColorAt(0, QColor(255, 196, 96, 150))
    g.setColorAt(1, QColor(255, 196, 96, 0))
    p.fillRect(QRectF(0, 0, w, h), g)
    p.restore()


def lamp_glow(p: QPainter, cx: float, cy: float, r: float) -> None:
    """등롱 불빛 번짐 (그림 바깥까지)."""
    g = QRadialGradient(QPointF(cx, cy), r)
    g.setColorAt(0, QColor(255, 214, 120, 150))
    g.setColorAt(0.4, QColor(255, 190, 90, 60))
    g.setColorAt(1, QColor(255, 190, 90, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(QPointF(cx, cy), r, r)
