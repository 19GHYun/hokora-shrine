# -*- coding: utf-8 -*-
"""요술 붓: 화면에 그은 선이 발판이 된다. 친구들이 그 위를 걷고, 가파른 내리막에선 미끄럼을 탄다.

선 하나를 x 가 한쪽으로만 가는 조각(InkPath)들로 나누어, 조각마다 y(x) 로 높이를 구한다
(되돌아가는 곳·벽처럼 선 곳에서 끊음). 그린 길은 INK_LIFE 동안 남았다가 서서히 사라진다.
"""
from __future__ import annotations

import bisect
import math
import random
import time
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

INK_LIFE = 10 * 60.0     # 그린 길이 남아 있는 시간 (초)
INK_FADE = 20.0          # 마지막 이만큼 동안 흐려지며 사라짐
MAX_STROKES = 12         # 더 그리면 가장 오래된 길부터 지워짐
MIN_LEN = 40.0           # 이보다 짧은 선은 무시
STEP = 6.0               # 선을 이 간격으로 다시 찍음 (손떨림 줄이기)
WALL_SLOPE = 3.0         # 이보다 가파른 곳(약 72°)은 벽 — 설 수 없어서 조각을 끊음
SLIDE_SLOPE = 0.45       # 이보다 가파른 내리막(약 24°)은 미끄럼
UPHILL_MAX = 1.0         # 이보다 가파른 오르막(45°)은 못 올라가서 돌아섬
MIN_PIECE = 24.0
INK0 = -2000             # 발판 번호: -2000, -2001, … (작업표시줄 -1…, 커서 -1000 과 겹치지 않게)
BRUSH_W = 11.0
COLORS = {"sumi": ("먹", "#2B2224"), "shu": ("주홍", "#D2412E"), "sakura": ("벚꽃", "#EE8AAE"),
          "sora": ("하늘", "#3F8FD8")}

Point = tuple[float, float]


def is_ink(hwnd: int | None) -> bool:
    return hwnd is not None and hwnd <= INK0


def length(pts: list[Point]) -> float:
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def resample(pts: list[Point], step: float = STEP) -> list[Point]:
    """같은 간격으로 다시 찍고 살짝 부드럽게 (끝점은 그대로)."""
    pts = [(float(x), float(y)) for x, y in pts]
    if len(pts) < 2:
        return pts
    out = [pts[0]]
    need = step                                  # 다음 점까지 남은 거리
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        pos = 0.0
        while seg - pos >= need:
            pos += need
            t = pos / seg
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
            need = step
        need -= seg - pos
    if math.dist(out[-1], pts[-1]) > step * 0.3:
        out.append(pts[-1])
    for _ in range(2):
        if len(out) > 2:
            out = [out[0]] + [((a[0] + 2 * b[0] + c[0]) / 4, (a[1] + 2 * b[1] + c[1]) / 4)
                              for a, b, c in zip(out, out[1:], out[2:])] + [out[-1]]
    return out


def split(pts: list[Point]) -> list[list[Point]]:
    """x 가 한 방향으로만 가는 조각들로 (되돌아가는 곳·벽처럼 가파른 곳에서 끊음). 조각은 왼쪽 → 오른쪽."""
    pieces: list[list[Point]] = []
    cur, d0 = [pts[0]], 0
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        if abs(dx) < 1e-6 or abs(dy / dx) > WALL_SLOPE:      # 벽: 여기서 끊고 다음 점부터 새 조각
            if len(cur) > 1:
                pieces.append(cur)
            cur, d0 = [b], 0
            continue
        d = 1 if dx > 0 else -1
        if d0 and d != d0:                                    # 되돌아감
            pieces.append(cur)
            cur = [a]
        d0 = d
        cur.append(b)
    if len(cur) > 1:
        pieces.append(cur)
    out = []
    for pc in pieces:
        if pc[0][0] > pc[-1][0]:
            pc = pc[::-1]
        if pc[-1][0] - pc[0][0] >= MIN_PIECE:
            out.append(pc)
    return out


class InkPath:
    """그린 길 한 조각: x1 ≤ x ≤ x2 에서 높이 y(x)."""

    def __init__(self, pid: int, pts: list[Point]):
        self.id = pid
        self.xs = [p[0] for p in pts]
        self.ys = [p[1] for p in pts]
        self.x1, self.x2 = self.xs[0], self.xs[-1]

    def y_at(self, x: float) -> float:
        xs, ys = self.xs, self.ys
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        i = bisect.bisect_right(xs, x) - 1
        x0, x1 = xs[i], xs[i + 1]
        return ys[i] + (ys[i + 1] - ys[i]) * ((x - x0) / (x1 - x0) if x1 > x0 else 0.0)

    def slope_at(self, x: float) -> float:
        """기울기 dy/dx (오른쪽으로 내려가면 +)."""
        a, b = max(self.x1, x - 5), min(self.x2, x + 5)
        return (self.y_at(b) - self.y_at(a)) / (b - a) if b > a else 0.0


class Stroke:
    """그은 선 하나 = 그림 창 하나 + 발판 조각들."""

    def __init__(self, pts: list[Point], color: str, first_id: int):
        self.pts = pts
        self.color = color if color in COLORS else "sumi"
        self.born = time.monotonic()
        self.pieces = [InkPath(first_id - i, pc) for i, pc in enumerate(split(pts))]
        self.win = InkWindow(self)

    def alpha(self, now: float) -> float:
        return max(0.0, min(1.0, (self.born + INK_LIFE - now) / INK_FADE))


def brush_path(pts: list[Point], width: float, seed: int) -> QPainterPath:
    """붓 자국: 가운데가 굵고 양 끝이 가늘어지는 면 (살짝 들쭉날쭉)."""
    rng = random.Random(seed)
    n = len(pts)
    left: list[QPointF] = []
    right: list[QPointF] = []
    wobble = 1.0
    for i, (x, y) in enumerate(pts):
        a = pts[max(0, i - 1)]
        b = pts[min(n - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / d, dx / d
        t = i / max(1, n - 1)
        wobble = wobble * 0.8 + rng.uniform(0.85, 1.15) * 0.2
        w = width * (0.3 + 0.7 * math.sin(math.pi * min(1.0, 0.08 + t * 0.92)) ** 0.45) * wobble / 2
        left.append(QPointF(x + nx * w, y + ny * w))
        right.append(QPointF(x - nx * w, y - ny * w))
    path = QPainterPath(left[0])
    for q in left[1:]:
        path.lineTo(q)
    for q in reversed(right):
        path.lineTo(q)
    path.closeSubpath()
    return path


class InkWindow(QWidget):
    """그린 길 그림. 클릭은 통과."""

    PAD = 14

    def __init__(self, stroke: Stroke):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.stroke = stroke
        xs = [p[0] for p in stroke.pts]
        ys = [p[1] for p in stroke.pts]
        self.ox, self.oy = math.floor(min(xs)) - self.PAD, math.floor(min(ys)) - self.PAD
        self.setGeometry(self.ox, self.oy, math.ceil(max(xs)) - self.ox + self.PAD,
                         math.ceil(max(ys)) - self.oy + self.PAD)
        local = [(x - self.ox, y - self.oy) for x, y in stroke.pts]
        self.path = brush_path(local, BRUSH_W, len(local))
        self.shadow = self.path.translated(0, 2.5)
        self.local = local

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(COLORS[self.stroke.color][1])
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 45))                   # 그림자
        p.drawPath(self.shadow)
        p.setBrush(color)
        p.drawPath(self.path)
        hi = QColor(255, 255, 255, 70)                     # 마른 붓 결
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(hi, 1.1, Qt.SolidLine, Qt.RoundCap))
        for off in (-1.6, 1.4):
            seg = QPainterPath(QPointF(self.local[0][0], self.local[0][1] + off))
            for x, y in self.local[1:]:
                seg.lineTo(x, y + off)
            p.drawPath(seg)
        p.end()


def brush_cursor() -> QCursor:
    """붓 모양 커서 (붓끝이 클릭 지점)."""
    pm = QPixmap(28, 28)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#8A5A32"), 4, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(24, 4), QPointF(10, 18))           # 자루
    p.setPen(QPen(QColor("#C9A06A"), 4, Qt.SolidLine, Qt.FlatCap))
    p.drawLine(QPointF(12, 16), QPointF(9, 19))           # 쇠테
    path = QPainterPath(QPointF(8, 17))                   # 붓털
    path.quadTo(QPointF(1, 22), QPointF(1, 27))
    path.quadTo(QPointF(6, 26), QPointF(11, 20))
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#2B2224"))
    p.drawPath(path)
    p.end()
    return QCursor(pm, 1, 27)


class _Bar(QWidget):
    """그리기 도구 띠 (위쪽 가운데)."""

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(200, 16, 46, 120), 1.2))
        p.setBrush(QColor(255, 247, 248, 245))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 14, 14)
        p.end()


class InkCanvas(QWidget):
    """길 그리기 판: 마우스가 있는 모니터 전체를 덮고, 드래그한 선을 on_stroke 로 넘긴다.
    우클릭·Esc·'다 그렸어요' 로 끝."""

    def __init__(self, color: str, on_stroke: Callable[[list[Point], str], object],
                 on_clear: Callable[[], None], on_close: Callable[[str], None], style: str = ""):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.on_stroke, self.on_clear, self.on_close = on_stroke, on_clear, on_close
        self.color = color if color in COLORS else "sumi"
        self.cur: list[Point] = []
        self.count = 0
        sc = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self.setGeometry(sc.geometry())
        self.setCursor(brush_cursor())

        bar = _Bar(self)
        bar.setStyleSheet(style)
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 8, 10, 8)
        h.setSpacing(6)
        self.hint = QLabel("✏️ 드래그해서 길을 그려요 · 가파른 곳은 미끄럼틀!", objectName="goal")
        h.addWidget(self.hint)
        self.swatches: dict[str, QPushButton] = {}
        for key, (name, hexc) in COLORS.items():
            b = QPushButton()
            b.setFixedSize(24, 24)
            b.setToolTip(name)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, key=key: self.pick(key))
            h.addWidget(b)
            self.swatches[key] = b
        for text, fn, name in (("🧽 모두 지우기", self._clear, "ghost"), ("다 그렸어요", self.close, "small")):
            b = QPushButton(text, objectName=name)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            h.addWidget(b)
        bar.adjustSize()
        bar.move((self.width() - bar.width()) // 2, 18)
        self.bar = bar
        self.pick(self.color)

    def pick(self, key: str) -> None:
        self.color = key
        for k, b in self.swatches.items():
            ring = "#C8102E" if k == key else "rgba(0,0,0,40)"
            b.setStyleSheet(f"QPushButton {{ background: {COLORS[k][1]}; border: {3 if k == key else 1}px solid {ring};"
                            f" border-radius: 12px; }}")

    def _clear(self) -> None:
        self.on_clear()
        self.setFocus()

    # ── 마우스 ──
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.RightButton:
            self.close()
            return
        if e.button() == Qt.LeftButton:
            g = e.globalPosition()
            self.cur = [(g.x(), g.y())]

    def mouseMoveEvent(self, e) -> None:
        if not self.cur:
            return
        g = e.globalPosition()
        if math.dist(self.cur[-1], (g.x(), g.y())) >= 3:
            self.cur.append((g.x(), g.y()))
            self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.LeftButton or not self.cur:
            return
        pts, self.cur = self.cur, []
        if length(pts) >= MIN_LEN and self.on_stroke(pts, self.color) is not None:
            self.count += 1
            self.hint.setText(f"✏️ 길 {self.count}개 — 더 그려도 돼요 (우클릭·Esc 로 끝)")
        self.update()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e) -> None:
        self.on_close(self.color)
        super().closeEvent(e)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(255, 250, 240, 34))            # 그리는 중임을 알리는 옅은 막 (클릭을 받으려면 꼭 필요)
        if len(self.cur) > 1:
            ox, oy = self.x(), self.y()
            path = QPainterPath(QPointF(self.cur[0][0] - ox, self.cur[0][1] - oy))
            for x, y in self.cur[1:]:
                path.lineTo(x - ox, y - oy)
            p.setPen(QPen(QColor(COLORS[self.color][1]), BRUSH_W * 0.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        p.end()
