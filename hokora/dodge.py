# -*- coding: utf-8 -*-
"""탄막 피하기 (언더테일 오마주): 작은 상자 안에서 마우스로 하트를 움직여 정해진 시간 동안 탄을 피한다.

- 친구마다 · 이변 흑막마다 탄 색과 패턴이 다르다 (링 · 조준탄 · 비 · 나선 · 벽 · 나이프).
- 목숨 3개, 맞으면 잠깐 무적. 끝까지 버티면 승리. 오른쪽 클릭이나 ✕ 로 그만둘 수 있다.
- 연습(친구)은 하루 5번까지 새전, 한 대도 안 맞으면 2배. 이변의 흑막 승부도 이 창으로 한다.
"""
from __future__ import annotations

import math
import random
import time
from datetime import date
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .state import GameState

ARENA_W, ARENA_H = 340, 240
PAD, HEADER, FOOTER = 14, 46, 24
SOUL_R = 6.0
HIT_R = 3.0              # 하트의 실제 맞는 크기 (보이는 것보다 작게)
LIVES = 3
INVINCIBLE = 1.1
READY = 1.6
END_SHOW = 1.4
PRACTICE_SECONDS = 15.0
BOSS_SECONDS = 20.0
DAILY_REWARDS = 5
SPIRAL_CYCLE, SPIRAL_ON = 1.3, 0.65   # 나선은 1.3초마다 0.65초만 쏨

# 키 → (탄 색 ("rainbow" 면 무지개), 패턴들, 세기)
STYLES: dict[str, tuple[str, tuple[str, ...], float]] = {
    "reimu": ("#E8343F", ("ring", "aimed"), 1.0),
    "marisa": ("#F2C230", ("spiral", "aimed"), 1.0),
    "cirno": ("#7FD8F0", ("rain", "aimed"), 0.9),
    "sakuya": ("#C8D0E0", ("knives",), 1.05),
    "sanae": ("#5CC87A", ("ring", "spiral"), 1.0),
    "remilia": ("#D0283C", ("ring", "knives"), 1.1),
    "flandre": ("rainbow", ("spiral", "ring"), 1.1),
    "youmu": ("#B8F0D0", ("wall", "aimed"), 1.0),
    "meiling": ("rainbow", ("spiral",), 0.95),
    "yuyuko": ("#F7A8C8", ("rain", "ring"), 1.15),        # 이변 흑막
    "reisen": ("#E04848", ("aimed", "wall"), 1.1),
    "suika": ("#E8A050", ("ring", "rain"), 1.15),
    "yukari": ("#9A6AD8", ("spiral", "wall"), 1.2),
    "nue": ("#D03040", ("aimed", "spiral"), 1.1),
}
DEFAULT_STYLE = ("#E8343F", ("ring", "aimed"), 1.0)


def rewards_left(s: GameState) -> int:
    return DAILY_REWARDS - (s.dodge_today if s.dodge_day == date.today().isoformat() else 0)


def practice_reward(s: GameState, won: bool, hits: int) -> int:
    """연습 결과 → 받은 새전 (하루 5번까지, 노피탄이면 2배)."""
    today = date.today().isoformat()
    if s.dodge_day != today:
        s.dodge_day, s.dodge_today = today, 0
    if not won:
        return 0
    s.dodge_clears += 1
    if hits == 0:
        s.dodge_perfect += 1
    if s.dodge_today >= DAILY_REWARDS:
        return 0
    s.dodge_today += 1
    amount = max(50, s.income_per_min * 4) * (2 if hits == 0 else 1)
    s.add_saisen(amount)
    return amount


class DodgeWindow(QWidget):
    """탄막 상자. 마우스가 상자 위에 있으면 하트가 따라오고, 밖이면 가장자리에 붙는다."""

    W = ARENA_W + PAD * 2
    H = HEADER + ARENA_H + PAD + FOOTER

    def __init__(self, key: str, name: str, on_end: Callable[[bool, int], None], seconds: float = PRACTICE_SECONDS,
                 boss: bool = False, rng: random.Random | None = None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFixedSize(self.W, self.H)
        self.setMouseTracking(True)
        self.key, self.name, self.on_end, self.seconds, self.boss = key, name, on_end, seconds, boss
        self.color, self.patterns, self.power = STYLES.get(key, DEFAULT_STYLE)
        self.rng = rng or random.Random()
        self.wall_left = self.rng.random() < 0.5
        self.bullets: list[list[float]] = []      # [x, y, vx, vy, 반지름, 색상(hue, -1 이면 고정색)]
        self.soul = QPointF(ARENA_W / 2, ARENA_H * 0.75)
        self.soul_override: QPointF | None = None  # 시험용: 커서 대신
        self.lives, self.hits = LIVES, 0
        self.t = 0.0                               # 시작(준비 끝)부터 흐른 시간
        self.ready = READY
        self.inv_until = 0.0
        self.result: bool | None = None
        self.end_at = 0.0
        self._acc: dict[str, float] = {}
        self._last = time.monotonic()
        self.timer = QTimer(self, timeout=self._tick, interval=16)
        self.timer.start()

    # ── 진행 ──
    def _tick(self) -> None:
        now = time.monotonic()
        dt = min(0.05, now - self._last)
        self._last = now
        self.step(dt)

    def step(self, dt: float) -> None:
        if self.result is not None:
            self.end_at -= dt
            if self.end_at <= 0:
                self.finish()
            self.update()
            return
        self._move_soul()
        if self.ready > 0:
            self.ready -= dt
            self.update()
            return
        self.t += dt
        self._spawn(dt)
        for b in self.bullets:
            b[0] += b[2] * dt
            b[1] += b[3] * dt
        m = 30
        self.bullets = [b for b in self.bullets if -m < b[0] < ARENA_W + m and -m < b[1] < ARENA_H + m]
        if self.t >= self.inv_until:
            sx, sy = self.soul.x(), self.soul.y()
            for b in self.bullets:
                if (b[0] - sx) ** 2 + (b[1] - sy) ** 2 < (b[4] + HIT_R) ** 2:
                    self._hit()
                    break
        if self.result is None and self.t >= self.seconds:
            self._end(True)
        self.update()

    def _move_soul(self) -> None:
        if self.soul_override is not None:
            p = self.soul_override
        else:
            local = self.mapFromGlobal(QCursor.pos())
            p = QPointF(local.x() - PAD, local.y() - HEADER)
        self.soul = QPointF(min(max(p.x(), SOUL_R), ARENA_W - SOUL_R), min(max(p.y(), SOUL_R), ARENA_H - SOUL_R))

    def _hit(self) -> None:
        self.hits += 1
        self.lives -= 1
        self.inv_until = self.t + INVINCIBLE
        if self.lives <= 0:
            self._end(False)

    def _end(self, won: bool) -> None:
        self.result = won
        self.end_at = END_SHOW
        self.unsetCursor()

    def give_up(self) -> None:
        if self.result is None:
            self.hits = max(self.hits, LIVES)
            self._end(False)
        self.finish()

    def finish(self) -> None:
        if not self.timer.isActive():
            return
        self.timer.stop()
        won = bool(self.result)
        self.close()
        self.on_end(won, self.hits)

    def closeEvent(self, e) -> None:
        if self.timer.isActive():                       # finish() 를 거치지 않고 닫힘 → 그만둔 것으로
            self.timer.stop()
            if self.result is None:
                self.hits = max(self.hits, LIVES)
            self.on_end(bool(self.result), self.hits)
        super().closeEvent(e)

    # ── 탄 ──
    def _every(self, name: str, period: float, dt: float) -> int:
        """period 초마다 한 번 → 이번 틱에 쏠 횟수."""
        acc = self._acc.get(name, period * 0.5) + dt
        n = int(acc // period)
        self._acc[name] = acc - n * period
        return n

    def _add(self, x: float, y: float, ang: float, speed: float, r: float = 4.5, hue: float = -1) -> None:
        self.bullets.append([x, y, math.cos(ang) * speed, math.sin(ang) * speed, r, hue])

    def _hue(self, i: int) -> float:
        return (i * 0.13 + self.t * 0.2) % 1.0 if self.color == "rainbow" else -1

    def _spawn(self, dt: float) -> None:
        d = self.power * (1 + 0.2 * self.t / self.seconds)            # 갈수록 조금씩 세짐
        rng = self.rng
        sx, sy = self.soul.x(), self.soul.y()
        for pat in self.patterns:
            if pat == "ring":
                for _ in range(self._every("ring", 1.5 / d, dt)):
                    cx, cy = rng.uniform(60, ARENA_W - 60), rng.uniform(16, 50)
                    n, off = 12 + int(4 * d), rng.uniform(0, math.tau)
                    for i in range(n):
                        self._add(cx, cy, off + i / n * math.tau, 68 * d, 4.5, self._hue(i))
            elif pat == "aimed":
                for _ in range(self._every("aimed", 0.6 / d, dt)):
                    side = rng.random()
                    if side < 0.5:
                        x, y = rng.uniform(0, ARENA_W), -6
                    elif side < 0.75:
                        x, y = -6, rng.uniform(0, ARENA_H * 0.6)
                    else:
                        x, y = ARENA_W + 6, rng.uniform(0, ARENA_H * 0.6)
                    base = math.atan2(sy - y, sx - x)
                    for k in (-1, 0, 1) if d > 1.2 else (0,):
                        self._add(x, y, base + k * 0.22, 95 * d, 4.0, self._hue(k))
            elif pat == "knives":
                for _ in range(self._every("knives", 1.0 / d, dt)):
                    x, y = rng.uniform(30, ARENA_W - 30), -6
                    base = math.atan2(sy - y, sx - x)
                    for k in range(-2, 3):
                        self._add(x, y, base + k * 0.16, 135 * d, 3.5, self._hue(k))
            elif pat == "rain":
                for i in range(self._every("rain", 0.13 / d, dt)):
                    self._add(rng.uniform(0, ARENA_W), -6, math.pi / 2 + rng.uniform(-0.25, 0.25),
                              rng.uniform(55, 85) * d, rng.uniform(3.5, 5.0), self._hue(i))
            elif pat == "spiral":
                n = self._every("spiral", 0.1 / d, dt)
                if self.t % SPIRAL_CYCLE > SPIRAL_ON:               # 쏘다 쉬다 — 나선 사이로 빠져나갈 틈
                    continue
                for _ in range(n):
                    cx, cy = ARENA_W / 2, ARENA_H * 0.32
                    ang = self.t * 1.9
                    for k in range(2):
                        self._add(cx, cy, ang + k * math.pi, 62 * d, 4.0, self._hue(k + int(self.t * 10)))
            elif pat == "wall":
                for _ in range(self._every("wall", 2.6 / d, dt)):
                    gap = rng.uniform(30, ARENA_H - 50)
                    y = 6.0
                    while y < ARENA_H:                          # 한 판 동안 벽은 한쪽에서만 (마주 오면 못 피함)
                        if not gap - 28 < y < gap + 28:
                            self._add(-6 if self.wall_left else ARENA_W + 6, y, 0 if self.wall_left else math.pi,
                                      80 * d, 4.0)
                        y += 15

    # ── 마우스 ──
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.RightButton or (e.position().y() < HEADER and e.position().x() > self.W - 34):
            self.give_up()

    def enterEvent(self, e) -> None:
        if self.result is None:
            self.setCursor(Qt.BlankCursor)
        super().enterEvent(e)

    def show_above(self, cx: float, bottom: float, area) -> None:
        x = min(max(cx - self.W / 2, area.left() + 8), area.right() - self.W - 8)
        y = min(max(bottom - self.H - 12, area.top() + 8), area.bottom() - self.H - 8)
        self.move(round(x), round(y))
        self.show()
        self.raise_()

    # ── 그리기 ──
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        outer = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        bg = QPainterPath()
        bg.addRoundedRect(outer, 10, 10)
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.setBrush(QColor(12, 10, 20, 240))
        p.drawPath(bg)
        f = QFont("Malgun Gothic", 10)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRectF(PAD, 6, self.W - 120, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   ("⚔ " if self.boss else "🎯 ") + f"VS {self.name}")
        p.setPen(QColor(255, 255, 255, 140))
        p.drawText(QRectF(self.W - 30, 6, 20, 20), Qt.AlignCenter, "✕")
        for i in range(LIVES):                                       # 목숨
            self._heart(p, QPointF(self.W - 100 + i * 20, 16), 6, QColor("#E8343F") if i < self.lives
                        else QColor(255, 255, 255, 50))
        frac = min(1.0, self.t / self.seconds)                       # 남은 시간 막대
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawRoundedRect(QRectF(PAD, 30, ARENA_W, 6), 3, 3)
        p.setBrush(QColor("#F2C230"))
        p.drawRoundedRect(QRectF(PAD, 30, ARENA_W * frac, 6), 3, 3)
        arena = QRectF(PAD, HEADER, ARENA_W, ARENA_H)
        p.setPen(QPen(QColor("#FFFFFF"), 3))
        p.setBrush(QColor(0, 0, 0))
        p.drawRect(arena)
        p.save()
        p.setClipRect(arena.adjusted(2, 2, -2, -2))
        p.translate(PAD, HEADER)
        base = QColor(self.color) if self.color != "rainbow" else QColor("#FFFFFF")
        for x, y, _vx, _vy, r, hue in self.bullets:
            col = QColor.fromHsvF(hue, 0.75, 1.0) if hue >= 0 else base
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawEllipse(QPointF(x, y), r + 1.5, r + 1.5)
            p.setBrush(QColor(255, 255, 255, 230))
            p.drawEllipse(QPointF(x, y), r * 0.55, r * 0.55)
        blink = self.t < self.inv_until and int(self.t * 12) % 2 == 0
        if not blink and self.result is not False:
            self._heart(p, self.soul, SOUL_R, QColor("#FF2A3A"))
        p.restore()
        p.setFont(QFont("Malgun Gothic", 9))
        p.setPen(QColor(255, 255, 255, 150))
        p.drawText(QRectF(PAD, HEADER + ARENA_H + 2, ARENA_W, FOOTER), Qt.AlignCenter,
                   "마우스로 하트를 움직여 탄을 피해요!" if self.ready > 0 else
                   f"{max(0.0, self.seconds - self.t):.1f}초 남음  ·  오른쪽 클릭 = 그만두기")
        big = QFont("Malgun Gothic", 18)
        big.setBold(True)
        p.setFont(big)
        if self.ready > 0:
            p.setPen(QColor("#FFFFFF"))
            p.drawText(arena, Qt.AlignCenter, "준비…" if self.ready > 0.6 else "시작!")
        elif self.result is not None:
            p.setPen(QColor("#F2C230") if self.result else QColor("#FF6A6A"))
            p.drawText(arena, Qt.AlignCenter, ("버텼다! ✨" + ("  노피탄!" if self.hits == 0 else "")) if self.result
                       else "피탄…")
        p.end()

    @staticmethod
    def _heart(p: QPainter, c: QPointF, r: float, color: QColor) -> None:
        path = QPainterPath()
        x, y = c.x(), c.y()
        path.moveTo(x, y + r)
        path.cubicTo(x - r * 1.6, y - r * 0.2, x - r * 0.8, y - r * 1.4, x, y - r * 0.5)
        path.cubicTo(x + r * 0.8, y - r * 1.4, x + r * 1.6, y - r * 0.2, x, y + r)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPath(path)
