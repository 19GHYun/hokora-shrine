# -*- coding: utf-8 -*-
"""작업표시줄 위를 돌아다니는 캐릭터 하나 = 작은 투명 창 하나.

매 프레임 캐릭터를 새로 그리면 CPU 를 많이 쓰므로, 동작별 프레임을 한 번 그려 두고(SpriteCache)
붙여넣기만 한다. 찌그러짐·기울기는 붙여넣을 때 변환으로 처리한다.
"""
from __future__ import annotations

import math
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
JUMP_CHANCE = 0.18              # 다음 행동을 고를 때 창으로 점프할 확률 (창 위 걷기를 켰을 때)
JUMP_CLEAR = 40.0               # 목표보다 이만큼 더 높이 뛰어오름
EDGE = 10.0                     # 창 끝에서 이만큼 앞에서 돌아서거나 떨어질지 정함
# 동작 → (프레임 수, 한 바퀴 시간). 애니메이션 식의 주기에 맞춰 끊김 없이 반복되게.
# 프레임 수는 그림 장수(2·3·4·6장)로 나누어떨어지게 12.
FRAMES = {
    "idle": (12, 2.856),   # sin(2.2t) — 숨쉬기 한 번
    "walk": (12, 0.698),   # sin(9t) — 두 발짝(왼발+오른발)
    "sit": (8, 8.0),       # 그림 캐릭터는 4초마다 앉은 자세를 바꿔 두리번거림
    "happy": (12, 1.0),    # 쓰다듬은 순간부터 1초 동안 한 번 (움츠림 → 점프 → 착지)
    "held": (12, 0.628),   # sin(10t) — 버둥 한 번
    "fall": (12, 0.628),
    "jump": (1, 1.0),      # 점프는 만세 자세 한 장
}


ONE_SHOT = {"happy"}


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
            phase = frame / n
            images = image_sprites(ch.key)
            if images is not None:
                hit = images.render(kind, phase, t, facing, blink, self.dpr)
            else:
                pm = QPixmap(round(CHAR_W * self.dpr), round(CHAR_H * self.dpr))
                pm.setDevicePixelRatio(self.dpr)
                pm.fill(Qt.transparent)
                p = QPainter(pm)
                draw_character(p, ch, Pose(kind="happy" if kind == "jump" else kind, t=t, facing=facing, blink=blink),
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

    climbing: bool     # 창 위에도 올라가기 켜짐
    platforms: list    # 지금 올라설 수 있는 창 윗변들 (winutil.Platform)

    def on_pat(self, pet: "PetWindow") -> None: ...
    def on_context_menu(self, global_pos) -> None: ...
    def find_landing(self, x: float, y0: float, y1: float) -> tuple[float, int | None] | None: ...
    def platform(self, hwnd: int, x: float, win_left: float): ...  # 그 창 윗변 중 올라선 구간 (없으면 None)
    def jump_target(self, pet: "PetWindow") -> tuple[float, float] | None: ...


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
        self._anim_kind, self._anim_start = self.state, self.t
        self.on: int | None = None       # 올라서 있는 창 (None = 작업표시줄)
        self._on_left = 0.0              # 그 창의 왼쪽 끝 — 창이 옮겨지면 같이 따라감
        self._edge_choice: bool | None = None   # 창 끝에 왔을 때 떨어질지(True) 돌아설지(False)
        self._place()

    @property
    def busy(self) -> bool:
        """부드럽게 움직여야 하는 중(던져짐·잡힘) — 이때만 프레임을 올린다."""
        return self.state in ("fall", "held", "jump")

    # ── 상태 ──
    def _choose_next(self) -> None:
        now = time.monotonic()
        if self.world.climbing and random.random() < JUMP_CHANCE:
            target = self.world.jump_target(self)
            if target and self._jump_to(*target):
                return
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

    def _jump_to(self, tx: float, ty: float) -> bool:
        """(tx, ty) 에 내려앉도록 포물선으로 점프."""
        apex = max(self.pos_y - ty, 0.0) + JUMP_CLEAR     # 지금 발 위치에서 최고점까지 높이
        vy0 = -math.sqrt(2 * GRAVITY * apex)
        # 발 높이가 ty 가 되는 (내려오는 쪽) 시간: g/2·t² + vy0·t + (y - ty) = 0
        a, b, c = GRAVITY / 2, vy0, self.pos_y - ty
        disc = b * b - 4 * a * c
        if disc < 0:
            return False
        t = (-b + math.sqrt(disc)) / (2 * a)
        if t <= 0.05:
            return False
        self.vx, self.vy = (tx - self.pos_x) / t, vy0
        self.facing = 1 if self.vx >= 0 else -1
        self.state, self.on = "jump", None
        self.squash = 0.12
        return True

    def _drop(self) -> None:
        """발판이 사라지거나 끝에서 걸어 나감 → 떨어지기 (걷던 속도는 유지)."""
        self.state, self.vy, self.on = "fall", 0.0, None
        self._edge_choice = None

    def _land(self, y: float, hwnd: int | None, now: float) -> None:
        self.pos_y = y
        self.vy = self.vx = 0
        self.squash = 0.2
        self.tilt = 0
        self.state = "idle"
        self.state_until = now + random.uniform(1, 2)
        self.on = hwnd
        self._edge_choice = None
        if hwnd is not None:
            plats = [p for p in self.world.platforms if p.hwnd == hwnd]
            self._on_left = plats[0].win_left if plats else 0.0

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
        elif self.state in ("fall", "jump"):
            prev_y = self.pos_y
            # 등가속도 운동의 정확한 식 → 프레임 간격(15/30fps)이 달라도 계산한 포물선 그대로 날아감
            self.pos_x += self.vx * dt
            self.pos_y += self.vy * dt + 0.5 * GRAVITY * dt * dt
            self.vy += GRAVITY * dt
            if self.state == "fall":
                self.tilt += self.vx * dt * 0.35
            lo, hi = w.left + CHAR_W / 2, w.right - CHAR_W / 2
            if self.pos_x < lo or self.pos_x > hi:
                self.pos_x = min(max(self.pos_x, lo), hi)
                self.vx = -self.vx * 0.5
            if self.pos_y - CHAR_H < w.top:
                self.pos_y = w.top + CHAR_H
                self.vy = abs(self.vy) * 0.3
            if self.vy > 0:                                   # 내려올 때만 창·작업표시줄에 착지
                hit = w.find_landing(self.pos_x, prev_y, self.pos_y)
                if hit is not None:
                    y, hwnd = hit
                    if self.state == "fall" and self.vy > 350:   # 세게 떨어지면 통통
                        self.pos_y = y
                        self.vy = -self.vy * 0.35
                        self.vx *= 0.7
                        self.squash = 0.28
                    else:
                        self._land(y, hwnd, now)
        else:
            plat = None
            if self.on is not None:                           # 창 위: 창이 사라지거나 끝을 벗어나면 떨어짐
                plat = w.platform(self.on, self.pos_x, self._on_left)
                if plat is None:
                    self._drop()
                else:
                    if plat.win_left != self._on_left:        # 창을 끌어 옮기면 같이
                        self.pos_x += plat.win_left - self._on_left
                        self._on_left = plat.win_left
                    self.pos_y = plat.y
            elif self.pos_y < w.ground_y - 1:                 # 작업표시줄 높이가 바뀌면 떨어짐
                self._drop()
            if self.state == "walk":
                self.pos_x += self.vx * dt
                if plat is not None:                          # 창 끝: 돌아서거나 폴짝 떨어지기
                    at_edge = (self.vx > 0 and self.pos_x > plat.x2 - EDGE) or (self.vx < 0 and self.pos_x < plat.x1 + EDGE)
                    if at_edge:
                        if self._edge_choice is None:
                            self._edge_choice = random.random() < 0.45
                        if not self._edge_choice:
                            self.vx = -self.vx
                            self.facing = 1 if self.vx > 0 else -1
                            self._edge_choice = None
                else:
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
        if kind != self._anim_kind:          # 새 동작은 첫 장면부터
            self._anim_kind, self._anim_start = kind, self.t
        n, loop = FRAMES[kind]
        if kind in ONE_SHOT:                 # 한 번만 재생하고 마지막 장면에서 멈춤
            frame = min(n - 1, int((self.t - self._anim_start) / loop * n))
        else:
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
        self._anim_kind, self._anim_start = "happy", self.t   # 연달아 쓰다듬어도 다시 폴짝
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
            self.on = None
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
