# -*- coding: utf-8 -*-
"""작업표시줄 위의 신사 건물. 단계가 오를수록 커진다 (호코라 → 신사 → 대신사)."""
from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .season import night_glow

GROUND_MARGIN = 2
LABEL_SPACE = 32          # 건물 위 말풍선(새전 수·+N) 자리
STAGE_SIZE = {1: (100, 100), 2: (150, 120), 3: (200, 140), 4: (244, 160), 5: (304, 196)}   # 단계별 건물 그림 크기 (바닥 = 아래)
OUTLINE = QColor(50, 34, 30, 210)


class ShrineHost(Protocol):
    left: float
    right: float

    def ground_under(self, x: float): ...     # x 에 있는 바닥 발판 (winutil.Platform)

    def on_shrine_clicked(self, global_pos) -> None: ...
    def on_shrine_moved(self, x: float) -> None: ...
    def on_context_menu(self, global_pos) -> None: ...


class ShrineWindow(QWidget):
    def __init__(self, host: ShrineHost, x: float, level: int):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.host = host
        self.pos_x = x  # 가운데 x (QWidget.x() 와 겹치지 않게)
        self.level = 0
        self.saisen = 0
        self.pops: list[list] = []      # [나이, 글자]
        self.hover = False
        self.night = False
        self._press = None
        self._dragging = False
        self.set_level(level)

    def set_night(self, on: bool) -> None:
        """밤엔 푸르스름하게, 등불이 켜진 듯이."""
        self.night = on
        self.update()

    @property
    def _k(self) -> float:
        return float(getattr(self.host, "scale", 1.0))

    def set_level(self, level: int) -> None:
        """신사 모양(단계)이나 크기가 바뀌면 창 크기도 건물에 맞게."""
        self.level = level
        w, h = STAGE_SIZE[level]
        self.setFixedSize(round(w * self._k) + 20, round(h * self._k) + LABEL_SPACE)
        self.pos_x = self._clamp(self.pos_x)
        self._place()
        self.update()

    def _clamp(self, x: float) -> float:
        """신사가 바닥(모니터) 밖으로 나가지 않게."""
        g = self.host.ground_under(x)
        half = self.width() / 2
        return min(max(x, g.x1 + half), g.x2 - half)

    def _place(self) -> None:
        ground = self.host.ground_under(self.pos_x).y
        self.move(round(self.pos_x - self.width() / 2), round(ground - self.height() + GROUND_MARGIN))

    def set_saisen(self, amount: int) -> None:
        self.saisen = amount
        self.update()

    def pop(self, text: str) -> None:
        self.pops.append([0.0, text])

    def step(self, dt: float) -> None:
        if not self.pops and not self.hover:
            return
        for pp in self.pops:
            pp[0] += dt
        self.pops = [pp for pp in self.pops if pp[0] < 1.6]
        self.update()

    # ── 그리기 ──
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # 건물은 창 아래쪽에 (바닥 = 창 아래)
        bw, bh = STAGE_SIZE[self.level]
        k = self._k
        p.save()
        p.translate((self.width() - bw * k) / 2, self.height() - GROUND_MARGIN - bh * k)
        p.scale(k, k)
        DRAW_STAGE[self.level](p)
        if self.night:
            night_glow(p, bw, bh)
        p.restore()
        f = QFont("Malgun Gothic", 9)
        f.setBold(True)
        p.setFont(f)
        if self.hover and not self._dragging:
            _label(p, QRectF(0, 0, self.width(), 22), f"새전 {self.saisen:,}")
        for age, text in self.pops:
            a = max(0.0, 1 - age / 1.6)
            y = 26 - age * 18
            p.setPen(QColor(200, 140, 20, int(255 * a)))
            p.drawText(QRectF(0, y, self.width(), 20), Qt.AlignCenter, text)
        p.end()

    # ── 마우스: 누르면 메뉴, 끌면 옆으로 옮기기 ──
    def enterEvent(self, e) -> None:
        self.hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self.hover = False
        self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._press = (e.globalPosition(), self.pos_x)
            self._dragging = False
        elif e.button() == Qt.RightButton:
            self.host.on_context_menu(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e) -> None:
        if self._press is None:
            return
        start, x0 = self._press
        dx = e.globalPosition().x() - start.x()
        if not self._dragging and abs(dx) < 5:
            return
        self._dragging = True
        self.setCursor(Qt.SizeHorCursor)
        self.pos_x = self._clamp(x0 + dx)
        self._place()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.LeftButton or self._press is None:
            return
        self._press = None
        self.setCursor(Qt.PointingHandCursor)
        if self._dragging:
            self._dragging = False
            self.host.on_shrine_moved(self.pos_x)
        else:
            self.host.on_shrine_clicked(e.globalPosition().toPoint())
        self.update()


def _label(p: QPainter, rect: QRectF, text: str) -> None:
    w = p.fontMetrics().horizontalAdvance(text) + 16
    r = QRectF(rect.center().x() - w / 2, rect.top() + 2, w, rect.height() - 4)
    path = QPainterPath()
    path.addRoundedRect(r, r.height() / 2, r.height() / 2)
    p.setPen(QPen(QColor(200, 16, 46, 140), 1))
    p.setBrush(QColor(255, 255, 255, 235))
    p.drawPath(path)
    p.setPen(QColor("#9E1027"))
    p.drawText(r, Qt.AlignCenter, text)


def _poly(points) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(*points[0])
    for pt in points[1:]:
        path.lineTo(*pt)
    path.closeSubpath()
    return path


def draw_hokora(p: QPainter) -> None:
    """1단계 호코라: 돌 받침 위의 작은 나무 사당 + 금줄 + 새전함. 100×100, 바닥 y=100."""
    pen = QPen(OUTLINE, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    # 그림자
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 45))
    p.drawEllipse(QRectF(14, 95, 72, 7))
    p.setPen(pen)
    # 돌 받침 (2단)
    stone = QLinearGradient(0, 78, 0, 98)
    stone.setColorAt(0, QColor("#B9B4AE"))
    stone.setColorAt(1, QColor("#8E8882"))
    p.setBrush(stone)
    p.drawRoundedRect(QRectF(18, 86, 64, 12), 3, 3)
    p.drawRoundedRect(QRectF(24, 76, 52, 11), 3, 3)
    # 사당 몸체 (나무)
    wood = QLinearGradient(30, 0, 70, 0)
    wood.setColorAt(0, QColor("#C08A57"))
    wood.setColorAt(1, QColor("#9C6A3E"))
    p.setBrush(wood)
    p.drawRect(QRectF(32, 50, 36, 27))
    # 문짝 두 개 + 가운데 금장
    p.setBrush(QColor("#7C5230"))
    p.drawRect(QRectF(36, 55, 13, 20))
    p.drawRect(QRectF(51, 55, 13, 20))
    p.setBrush(QColor("#E8C048"))
    p.drawEllipse(QRectF(47.5, 63, 5, 5))
    # 지붕 (휘어 올라간 박공 지붕)
    roof = QPainterPath()
    roof.moveTo(18, 54)
    roof.quadTo(34, 50, 50, 30)
    roof.quadTo(66, 50, 82, 54)
    roof.lineTo(78, 58)
    roof.quadTo(64, 54, 50, 38)
    roof.quadTo(36, 54, 22, 58)
    roof.closeSubpath()
    roofg = QLinearGradient(0, 30, 0, 58)
    roofg.setColorAt(0, QColor("#5B4A4E"))
    roofg.setColorAt(1, QColor("#3A2E32"))
    p.setBrush(roofg)
    p.drawPath(roof)
    # 박공 아래 삼각형 벽
    p.setBrush(QColor("#A8744A"))
    p.drawPath(_poly([(34, 50), (50, 38), (66, 50)]))
    # 용마루 장식
    p.setBrush(QColor("#E8C048"))
    p.drawEllipse(QRectF(47, 27, 6, 6))
    # 금줄(시메나와) + 시데(흰 번개 모양 종이)
    rope = QPainterPath()
    rope.moveTo(30, 52)
    rope.quadTo(50, 60, 70, 52)
    p.setPen(QPen(QColor("#E6D29A"), 3.2, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawPath(rope)
    p.setPen(QPen(OUTLINE, 1.0))
    p.setBrush(QColor("#FFFFFF"))
    for sx in (38, 50, 62):
        sy = 55.5 if sx == 50 else 54
        p.drawPath(_poly([(sx - 2, sy), (sx + 2, sy), (sx + 0.5, sy + 4), (sx + 3, sy + 4),
                          (sx - 1, sy + 10), (sx, sy + 6), (sx - 3, sy + 6)]))
    # 새전함 (받침 앞)
    p.setPen(pen)
    box = QLinearGradient(0, 84, 0, 98)
    box.setColorAt(0, QColor("#B77E4C"))
    box.setColorAt(1, QColor("#8A5A32"))
    p.setBrush(box)
    p.drawRect(QRectF(38, 86, 24, 12))
    p.setPen(QPen(QColor(60, 36, 20, 170), 1.2))
    for i in range(5):
        x = 41 + i * 4.5
        p.drawLine(QPointF(x, 87.5), QPointF(x, 91))
    p.setPen(QPen(OUTLINE, 1.0))
    p.setFont(QFont("Malgun Gothic", 5))
    p.setPen(QColor("#F3E3B0"))
    p.drawText(QRectF(38, 91, 24, 7), Qt.AlignCenter, "賽銭")


# ─────────────────────────────── 2·3단계 ───────────────────────────────
VERMILION = QColor("#D9412E")       # 신사 주홍색
VERMILION_DARK = QColor("#A82A1E")


def _torii(p: QPainter, x: float, ground: float, w: float, h: float) -> None:
    """빨간 도리이. x = 왼쪽 끝."""
    p.setPen(QPen(OUTLINE, 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    post_w = w * 0.12
    top = ground - h
    grad = QLinearGradient(x, 0, x + w, 0)
    grad.setColorAt(0, VERMILION)
    grad.setColorAt(1, VERMILION_DARK)
    p.setBrush(grad)
    for px in (x + w * 0.14, x + w * 0.86 - post_w):          # 기둥 두 개
        p.drawRect(QRectF(px, top + h * 0.14, post_w, h * 0.86))
    p.drawRect(QRectF(x + w * 0.08, top + h * 0.32, w * 0.84, h * 0.07))   # 아래 가로대(누키)
    kasagi = QPainterPath()                                   # 위 가로대(가사기): 양끝이 살짝 올라감
    kasagi.moveTo(x - w * 0.06, top)
    kasagi.quadTo(x + w / 2, top + h * 0.08, x + w * 1.06, top)
    kasagi.lineTo(x + w * 1.0, top + h * 0.12)
    kasagi.quadTo(x + w / 2, top + h * 0.17, x, top + h * 0.12)
    kasagi.closeSubpath()
    p.setBrush(QColor("#3A2E32"))
    p.drawPath(kasagi)
    p.setBrush(VERMILION)
    p.drawRect(QRectF(x + w * 0.02, top + h * 0.12, w * 0.96, h * 0.06))
    p.drawRect(QRectF(x + w * 0.46, top + h * 0.17, w * 0.08, h * 0.15))   # 가운데 현판 기둥


def _lantern(p: QPainter, cx: float, ground: float, h: float) -> None:
    """돌등롱."""
    p.setPen(QPen(OUTLINE, 1.2))
    stone = QLinearGradient(cx - h * 0.3, 0, cx + h * 0.3, 0)
    stone.setColorAt(0, QColor("#C4BFB8"))
    stone.setColorAt(1, QColor("#8E8882"))
    p.setBrush(stone)
    w = h * 0.42
    p.drawRect(QRectF(cx - w * 0.55, ground - h * 0.12, w * 1.1, h * 0.12))         # 받침
    p.drawRect(QRectF(cx - w * 0.14, ground - h * 0.55, w * 0.28, h * 0.43))        # 기둥
    p.drawRect(QRectF(cx - w * 0.42, ground - h * 0.78, w * 0.84, h * 0.23))        # 불집
    p.setBrush(QColor(255, 214, 120, 230))
    p.drawRect(QRectF(cx - w * 0.2, ground - h * 0.73, w * 0.4, h * 0.13))          # 불빛
    p.setBrush(stone)
    p.drawPath(_poly([(cx - w * 0.62, ground - h * 0.78), (cx, ground - h * 0.98),
                      (cx + w * 0.62, ground - h * 0.78)]))                          # 지붕


def _hall(p: QPainter, x: float, ground: float, w: float, h: float, grand: bool) -> None:
    """본전: 돌 기단 + 주홍 기둥과 흰 벽 + 휘어 올라간 지붕(대신사는 2층 지붕)."""
    pen = QPen(OUTLINE, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    base_h = h * 0.14
    stone = QLinearGradient(0, ground - base_h, 0, ground)
    stone.setColorAt(0, QColor("#B9B4AE"))
    stone.setColorAt(1, QColor("#8E8882"))
    p.setBrush(stone)
    p.drawRoundedRect(QRectF(x, ground - base_h, w, base_h), 2, 2)
    body_top = ground - base_h - h * 0.34
    body = QRectF(x + w * 0.12, body_top, w * 0.76, h * 0.34)
    p.setBrush(QColor("#F4EDE2"))
    p.drawRect(body)
    p.setBrush(VERMILION)
    for i in range(4):                                         # 주홍 기둥
        px = body.left() + i * (body.width() - w * 0.05) / 3
        p.drawRect(QRectF(px, body_top, w * 0.05, body.height()))
    p.setBrush(QColor("#7C5230"))                              # 가운데 문
    p.drawRect(QRectF(x + w * 0.42, body_top + body.height() * 0.3, w * 0.16, body.height() * 0.7))

    def roof(top_y: float, span: float, depth: float) -> None:
        cx = x + w / 2
        path = QPainterPath()
        path.moveTo(cx - span / 2, top_y + depth)
        path.quadTo(cx - span * 0.25, top_y + depth * 0.8, cx, top_y)
        path.quadTo(cx + span * 0.25, top_y + depth * 0.8, cx + span / 2, top_y + depth)
        path.lineTo(cx + span / 2 - 4, top_y + depth + 4)
        path.quadTo(cx, top_y + depth * 0.45, cx - span / 2 + 4, top_y + depth + 4)
        path.closeSubpath()
        g = QLinearGradient(0, top_y, 0, top_y + depth)
        g.setColorAt(0, QColor("#5B4A4E"))
        g.setColorAt(1, QColor("#3A2E32"))
        p.setPen(pen)
        p.setBrush(g)
        p.drawPath(path)
        p.setBrush(QColor("#E8C048"))
        p.drawEllipse(QRectF(cx - 3, top_y - 3, 6, 6))           # 용마루 금장식

    if grand:  # 2층: 작은 벽 위에 윗지붕 (아래 지붕보다 먼저 그려 아래 지붕이 벽 밑동을 덮게)
        p.setPen(pen)
        p.setBrush(QColor("#F4EDE2"))
        p.drawRect(QRectF(x + w * 0.3, body_top - h * 0.36, w * 0.4, h * 0.24))
        p.setBrush(VERMILION)
        for fx in (0.3, 0.675):
            p.drawRect(QRectF(x + w * fx, body_top - h * 0.36, w * 0.025, h * 0.24))
        roof(body_top - h * 0.56, w * 0.62, h * 0.24)
    roof(body_top - h * 0.30, w * 1.02, h * 0.34)
    # 금줄 + 방울 줄
    rope = QPainterPath()
    rope.moveTo(x + w * 0.2, body_top + 3)
    rope.quadTo(x + w / 2, body_top + 12, x + w * 0.8, body_top + 3)
    p.setPen(QPen(QColor("#E6D29A"), 3.2, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawPath(rope)
    p.setPen(QPen(QColor("#C8102E"), 2.0))
    p.drawLine(QPointF(x + w / 2, body_top + 8), QPointF(x + w / 2, body_top + body.height() * 0.8))
    p.setPen(QPen(OUTLINE, 1.0))
    p.setBrush(QColor("#E8C048"))
    p.drawEllipse(QRectF(x + w / 2 - 4, body_top + 6, 8, 8))     # 방울
    # 새전함
    p.setPen(pen)
    box = QRectF(x + w * 0.34, ground - base_h - 2, w * 0.32, base_h * 0.9)
    g = QLinearGradient(0, box.top(), 0, box.bottom())
    g.setColorAt(0, QColor("#B77E4C"))
    g.setColorAt(1, QColor("#8A5A32"))
    p.setBrush(g)
    p.drawRect(box)
    p.setPen(QPen(QColor(60, 36, 20, 170), 1.2))
    for i in range(6):
        bx = box.left() + 3 + i * (box.width() - 6) / 5
        p.drawLine(QPointF(bx, box.top() + 2), QPointF(bx, box.top() + box.height() * 0.45))


def _shadow(p: QPainter, x: float, w: float, ground: float) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 45))
    p.drawEllipse(QRectF(x, ground - 4, w, 8))


def draw_jinja(p: QPainter) -> None:
    """2단계 신사: 도리이 + 본전. 150×120, 바닥 y=120."""
    _shadow(p, 4, 142, 120)
    _torii(p, 4, 120, 50, 78)
    _hall(p, 58, 120, 90, 100, grand=False)


def draw_taisha(p: QPainter) -> None:
    """3단계 대신사: 도리이 + 돌등롱 + 2층 지붕 본전. 200×140, 바닥 y=140."""
    _shadow(p, 4, 192, 140)
    _torii(p, 4, 140, 58, 96)
    _lantern(p, 74, 140, 44)
    _hall(p, 84, 140, 112, 132, grand=True)


def _pagoda(p: QPainter, cx: float, ground: float, w: float, h: float, tiers: int = 5) -> None:
    """오층탑: 층마다 좁아지는 몸체와 휘어 올라간 지붕, 꼭대기에 금색 상륜."""
    pen = QPen(OUTLINE, 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    base_h = h * 0.06
    p.setPen(pen)
    p.setBrush(QColor("#A9A39C"))
    p.drawRoundedRect(QRectF(cx - w * 0.5, ground - base_h, w, base_h), 2, 2)
    spire_h = h * 0.16
    tier_h = (h - base_h - spire_h) / tiers
    top = ground - base_h
    for i in range(tiers):
        k = 1 - i * 0.11                            # 위로 갈수록 좁게
        bw, rw = w * 0.52 * k, w * 1.0 * k
        body_top = top - tier_h * 0.55
        p.setPen(pen)
        p.setBrush(QColor("#F4EDE2"))
        p.drawRect(QRectF(cx - bw / 2, body_top, bw, top - body_top))
        p.setBrush(VERMILION)
        for fx in (-0.5, 0.5 - 0.14):
            p.drawRect(QRectF(cx + bw * fx, body_top, bw * 0.14, top - body_top))
        roof = QPainterPath()                       # 휘어 올라간 처마
        ry = body_top
        roof.moveTo(cx - rw / 2, ry + 2)
        roof.quadTo(cx - rw * 0.3, ry - tier_h * 0.05, cx - bw * 0.35, ry - tier_h * 0.42)
        roof.lineTo(cx + bw * 0.35, ry - tier_h * 0.42)
        roof.quadTo(cx + rw * 0.3, ry - tier_h * 0.05, cx + rw / 2, ry + 2)
        roof.quadTo(cx, ry - tier_h * 0.12, cx - rw / 2, ry + 2)
        roof.closeSubpath()
        g = QLinearGradient(0, ry - tier_h * 0.42, 0, ry)
        g.setColorAt(0, QColor("#5B4A4E"))
        g.setColorAt(1, QColor("#3A2E32"))
        p.setBrush(g)
        p.drawPath(roof)
        top = ry - tier_h * 0.42
    p.setPen(QPen(QColor("#B8912E"), 2.2, Qt.SolidLine, Qt.RoundCap))   # 상륜 (금색 기둥 + 고리)
    p.drawLine(QPointF(cx, top), QPointF(cx, top - spire_h))
    p.setPen(QPen(OUTLINE, 0.9))
    p.setBrush(QColor("#E8C048"))
    for i in range(5):
        ry = top - spire_h * (0.2 + i * 0.15)
        p.drawEllipse(QRectF(cx - 4.5 + i * 0.5, ry - 1.5, 9 - i, 3))
    p.drawEllipse(QRectF(cx - 3.5, top - spire_h - 5, 7, 7))


def _fence(p: QPainter, x: float, ground: float, w: float, h: float) -> None:
    """낮은 주홍 울타리 (다마가키)."""
    p.setPen(QPen(OUTLINE, 1.0))
    p.setBrush(VERMILION)
    n = max(3, int(w // 9))
    for i in range(n + 1):
        px = x + i * w / n
        p.drawRect(QRectF(px - 1.6, ground - h, 3.2, h))
    for ry in (0.25, 0.65):
        p.drawRect(QRectF(x - 2, ground - h * (1 - ry) - 1.5, w + 4, 3))


def draw_meisho(p: QPainter) -> None:
    """4단계 명소 신사: 겹 도리이 + 돌등롱 + 2층 본전 앞 주홍 울타리 + 곁에 작은 호코라. 244×160, 바닥 y=160."""
    _shadow(p, 4, 236, 160)
    _torii(p, 20, 160, 46, 84)            # 뒤쪽 작은 도리이
    _torii(p, 2, 160, 60, 110)            # 앞쪽 큰 도리이
    _lantern(p, 76, 160, 48)
    _hall(p, 88, 160, 116, 144, grand=True)
    _fence(p, 92, 160, 34, 16)
    _fence(p, 166, 160, 34, 16)
    p.save()
    p.translate(206, 160 - 36)
    p.scale(0.36, 0.36)
    draw_hokora(p)
    p.restore()


def draw_gensokyo(p: QPainter) -> None:
    """5단계 환상향 제일 신사: 오층탑 + 큰 도리이 + 돌등롱 둘 + 2층 본전. 304×196, 바닥 y=196."""
    _shadow(p, 4, 296, 196)
    _pagoda(p, 36, 196, 62, 192)
    _torii(p, 90, 196, 50, 96)            # 뒤쪽 작은 도리이
    _torii(p, 72, 196, 68, 128)
    _lantern(p, 150, 196, 50)
    _hall(p, 162, 196, 116, 160, grand=True)
    _fence(p, 166, 196, 36, 18)
    _fence(p, 238, 196, 36, 18)
    _lantern(p, 290, 196, 44)


DRAW_STAGE = {1: draw_hokora, 2: draw_jinja, 3: draw_taisha, 4: draw_meisho, 5: draw_gensokyo}
