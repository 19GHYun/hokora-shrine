# -*- coding: utf-8 -*-
"""작업표시줄 위를 돌아다니는 캐릭터 하나 = 작은 투명 창 하나.

매 프레임 캐릭터를 새로 그리면 CPU 를 많이 쓰므로, 동작별 프레임을 한 번 그려 두고(SpriteCache)
붙여넣기만 한다. 찌그러짐·기울기는 붙여넣을 때 변환으로 처리한다.
"""
from __future__ import annotations

import random
import time
from collections import deque
from typing import Protocol

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QWidget

from .render import Character, Pose, draw_character
from .sprites import image_sprites
from .state import PAT_COOLDOWN

# 창은 캐릭터가 빙글 돌아도(대각선 ≈ 94px) 잘리지 않을 만큼 넉넉하게.
# 투명한 부분은 클릭이 뒤로 통과하므로(레이어드 창) 작업표시줄을 가리지 않는다.
WIN_W, WIN_H = 120, 132
CHAR_W, CHAR_H = 56, 67         # 캐릭터 크기
FOOT_MARGIN = 18                # 창 아래쪽과 발 사이 (돌 때 발이 이만큼 아래로 내려감)
SPIN_PIVOT = CHAR_H * 0.5       # 던져져 돌 때의 회전 중심: 발에서 몸 가운데까지
GRAVITY = 2200.0                # px/s²
WALK_SPEED = (22.0, 34.0)       # px/s
MAX_THROW = 2600.0
# 동작 → (프레임 수, 한 바퀴 시간). 애니메이션 식의 주기에 맞춰 끊김 없이 반복되게.
FRAMES = {
    "idle": (12, 2.856),   # sin(2.2t)
    "walk": (8, 0.698),    # sin(9t)
    "sit": (8, 8.0),       # 그림 캐릭터는 4초마다 앉은 자세를 바꿔 두리번거림
    "happy": (8, 0.52),
    "held": (8, 0.628),    # sin(10t)
    "fall": (8, 0.628),
}


class SpriteCache:
    """(캐릭터, 동작, 프레임, 방향, 깜빡임) → (미리 그린 그림, 그림 안의 발 위치).

    그림 파일이 있는 캐릭터(hokora/sprites/<키>/)는 그 그림을, 없으면 코드 그림을 쓴다.
    """

    def __init__(self):
        self._cache: dict[tuple, tuple[QPixmap, QPointF]] = {}
        screen = QGuiApplication.primaryScreen()
        self.dpr = max(1.0, screen.devicePixelRatio() if screen else 1.0)

    def get(self, ch: Character, kind: str, frame: int, facing: int, blink: bool) -> tuple[QPixmap, QPointF]:
        key = (ch.key, kind, frame, facing, blink)
        hit = self._cache.get(key)
        if hit is None:
            n, loop = FRAMES[kind]
            t = frame * loop / n
            images = image_sprites(ch.key)
            if images is not None:
                hit = images.render(kind, t, facing, blink, self.dpr)
            else:
                pm = QPixmap(round(CHAR_W * self.dpr), round(CHAR_H * self.dpr))
                pm.setDevicePixelRatio(self.dpr)
                pm.fill(Qt.transparent)
                p = QPainter(pm)
                draw_character(p, ch, Pose(kind=kind, t=t, facing=facing, blink=blink),
                               QRectF(0, 0, CHAR_W, CHAR_H))
                p.end()
                hit = (pm, QPointF(CHAR_W / 2, CHAR_H))
            self._cache[key] = hit
        return hit


_sprites: SpriteCache | None = None


def sprites() -> SpriteCache:
    global _sprites
    if _sprites is None:
        _sprites = SpriteCache()
    return _sprites


class World(Protocol):
    """캐릭터가 사는 곳 (Game 이 구현)."""
    ground_y: float
    left: float
    right: float
    top: float

    def on_pat(self, pet: "PetWindow") -> None: ...
    def on_context_menu(self, global_pos) -> None: ...


class PetWindow(QWidget):
    def __init__(self, ch: Character, world: World, x: float):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(WIN_W, WIN_H)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip(ch.name)
        self.ch = ch
        self.world = world
        # 발 위치(화면 좌표, 논리 픽셀). QWidget.x()/y() 와 겹치지 않게 pos_ 로.
        self.pos_x, self.pos_y = x, world.ground_y
        self.vx = self.vy = 0.0
        self.facing = random.choice((-1, 1))
        self.state = "idle"
        self.state_until = time.monotonic() + random.uniform(1, 3)
        self.t = random.uniform(0, 10)   # 애니메이션 시간 (캐릭터마다 어긋나게)
        self.blink_at = time.monotonic() + random.uniform(2, 5)
        self.squash = 0.0
        self.tilt = 0.0
        self.hearts: list[list[float]] = []  # [나이, x, y]
        self.last_reward = 0.0
        self._press_pos = None
        self._drag_offset = QPointF()
        self._trail: deque[tuple[float, QPointF]] = deque(maxlen=6)
        self._drawn_key = None
        self._placed = None
        self._place()

    @property
    def busy(self) -> bool:
        """부드럽게 움직여야 하는 중(던져짐·잡힘) — 이때만 프레임을 올린다."""
        return self.state in ("fall", "held")

    # ── 상태 ──
    def _choose_next(self) -> None:
        now = time.monotonic()
        r = random.random()
        if r < 0.5:
            self.state = "walk"
            self.facing = random.choice((-1, 1))
            self.vx = self.facing * random.uniform(*WALK_SPEED)
            self.state_until = now + random.uniform(3, 8)
        elif r < 0.8:
            self.state = "idle"
            self.vx = 0
            self.state_until = now + random.uniform(2, 6)
        else:
            self.state = "sit"
            self.vx = 0
            self.state_until = now + random.uniform(5, 12)

    def step(self, dt: float) -> None:
        self.t += dt
        now = time.monotonic()
        w = self.world
        self.squash = self.squash * max(0.0, 1 - dt * 8) if self.squash > 0.01 else 0.0
        if self.hearts:
            for h in self.hearts:
                h[0] += dt
            self.hearts = [h for h in self.hearts if h[0] < 1.2]

        if self.state == "held":
            pass  # 마우스가 옮김
        elif self.state == "fall":
            self.vy += GRAVITY * dt
            self.pos_x += self.vx * dt
            self.pos_y += self.vy * dt
            self.tilt += self.vx * dt * 0.35
            lo, hi = w.left + CHAR_W / 2, w.right - CHAR_W / 2
            if self.pos_x < lo or self.pos_x > hi:
                self.pos_x = min(max(self.pos_x, lo), hi)
                self.vx = -self.vx * 0.5
            if self.pos_y - CHAR_H < w.top:
                self.pos_y = w.top + CHAR_H
                self.vy = abs(self.vy) * 0.3
            if self.pos_y >= w.ground_y:
                self.pos_y = w.ground_y
                if self.vy > 350:                        # 통통 튀기
                    self.vy = -self.vy * 0.35
                    self.vx *= 0.7
                    self.squash = 0.28
                else:
                    self.vy = self.vx = 0
                    self.squash = 0.2
                    self.tilt = 0
                    self.state = "idle"
                    self.state_until = now + random.uniform(1, 2)
        else:
            if self.pos_y < w.ground_y - 1:              # 작업표시줄 높이가 바뀌면 떨어짐
                self.state, self.vy = "fall", 0.0
            elif self.state == "walk":
                self.pos_x += self.vx * dt
                lo, hi = w.left + CHAR_W / 2, w.right - CHAR_W / 2
                if self.pos_x <= lo or self.pos_x >= hi:
                    self.pos_x = min(max(self.pos_x, lo), hi)
                    self.vx = -self.vx
                    self.facing = 1 if self.vx > 0 else -1
            self.tilt = self.tilt * max(0.0, 1 - dt * 10) if abs(self.tilt) > 0.5 else 0.0
            if self.state in ("idle", "walk", "sit", "happy") and now >= self.state_until:
                self._choose_next()
        self._place()
        # 그림이 바뀔 때만 다시 그림
        if self._frame_key() != self._drawn_key or self.squash or self.tilt or self.hearts:
            self.update()

    def _frame_key(self) -> tuple:
        kind = self.state if self.state in FRAMES else "idle"
        n, loop = FRAMES[kind]
        frame = int((self.t % loop) / loop * n)
        now = time.monotonic()
        blink = self.blink_at <= now < self.blink_at + 0.14
        if now >= self.blink_at + 0.14:
            self.blink_at = now + random.uniform(2.5, 5.5)
        return kind, frame, self.facing, blink

    def _place(self) -> None:
        pos = (round(self.pos_x - WIN_W / 2), round(self.pos_y - (WIN_H - FOOT_MARGIN)))
        if pos != self._placed:
            self._placed = pos
            self.move(*pos)

    def pat(self) -> bool:
        """쓰다듬기. 보상을 받을 수 있으면 True."""
        self.state = "happy"
        self.vx = 0
        self.state_until = time.monotonic() + 1.0
        self.squash = 0.18
        self.hearts.append([0.0, WIN_W / 2 + random.uniform(-10, 10), WIN_H - FOOT_MARGIN - CHAR_H])
        now = time.monotonic()
        if now - self.last_reward >= PAT_COOLDOWN:
            self.last_reward = now
            return True
        return False

    # ── 그리기 ──
    def paintEvent(self, _e) -> None:
        key = self._frame_key()
        self._drawn_key = key
        kind, frame, facing, blink = key
        pm, anchor = sprites().get(self.ch, kind, frame, facing, blink)
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        # 찌그러짐은 발을 기준으로, 빙글 도는 건 몸 가운데를 기준으로 (발 기준이면 몸이 창 밖으로 휘둘려 잘림)
        fx, fy = WIN_W / 2, WIN_H - FOOT_MARGIN
        p.translate(fx, fy)
        if self.tilt:
            p.translate(0, -SPIN_PIVOT)
            p.rotate(self.tilt)
            p.translate(0, SPIN_PIVOT)
        if self.squash:
            sq = min(0.3, self.squash)
            p.scale(1 + sq * 0.6, 1 - sq)
        p.drawPixmap(-anchor, pm)
        p.resetTransform()
        if self.hearts:
            p.setRenderHint(QPainter.Antialiasing)
            for age, hx, hy in self.hearts:
                a = max(0.0, 1 - age / 1.2)
                _heart(p, hx, hy - age * 26, 9 + age * 3, QColor(235, 70, 100, int(230 * a)))
        p.end()

    # ── 마우스: 짧게 누르면 쓰다듬기, 끌면 들어서 던지기 ──
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._press_pos = e.globalPosition()
            self._drag_offset = e.position()
            self._trail.clear()
            self._trail.append((time.monotonic(), e.globalPosition()))
        elif e.button() == Qt.RightButton:
            self.world.on_context_menu(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e) -> None:
        if self._press_pos is None:
            return
        g = e.globalPosition()
        if self.state != "held":
            if (g - self._press_pos).manhattanLength() < 5:
                return
            self.state = "held"
            self.vx = self.vy = 0
            self.tilt = 0.0
            self.setCursor(Qt.ClosedHandCursor)
        self._trail.append((time.monotonic(), g))
        # 잡은 지점이 커서를 따라가게
        self.pos_x = g.x() - self._drag_offset.x() + WIN_W / 2
        self.pos_y = g.y() - self._drag_offset.y() + (WIN_H - FOOT_MARGIN)
        self._place()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.LeftButton or self._press_pos is None:
            return
        self._press_pos = None
        self.setCursor(Qt.OpenHandCursor)
        if self.state == "held":
            vx = vy = 0.0
            if len(self._trail) >= 2:
                (t0, p0), (t1, p1) = self._trail[0], self._trail[-1]
                if t1 - t0 > 0.005:
                    vx, vy = (p1.x() - p0.x()) / (t1 - t0), (p1.y() - p0.y()) / (t1 - t0)
            speed = (vx * vx + vy * vy) ** 0.5
            if speed > MAX_THROW:
                vx, vy = vx * MAX_THROW / speed, vy * MAX_THROW / speed
            self.vx, self.vy = vx, vy
            self.state = "fall"
        else:
            self.world.on_pat(self)


def _heart(p: QPainter, cx: float, cy: float, size: float, color: QColor) -> None:
    s = size / 2
    path = QPainterPath()
    path.moveTo(cx, cy + s * 0.9)
    path.cubicTo(cx - s * 1.6, cy - s * 0.2, cx - s * 0.6, cy - s * 1.3, cx, cy - s * 0.45)
    path.cubicTo(cx + s * 0.6, cy - s * 1.3, cx + s * 1.6, cy - s * 0.2, cx, cy + s * 0.9)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawPath(path)
