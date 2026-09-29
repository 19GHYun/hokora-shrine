# -*- coding: utf-8 -*-
"""작업표시줄 위의 신사 건물. 단계가 오를수록 커진다 (1단계: 작은 호코라)."""
from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

WIN_W, WIN_H = 120, 132
GROUND_MARGIN = 2
OUTLINE = QColor(50, 34, 30, 210)


class ShrineHost(Protocol):
    ground_y: float
    left: float
    right: float

    def on_shrine_clicked(self, global_pos) -> None: ...
    def on_shrine_moved(self, x: float) -> None: ...
    def on_context_menu(self, global_pos) -> None: ...


class ShrineWindow(QWidget):
    def __init__(self, host: ShrineHost, x: float, level: int):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(WIN_W, WIN_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.host = host
        self.pos_x = x  # 가운데 x (QWidget.x() 와 겹치지 않게)
        self.level = level
        self.saisen = 0
        self.pops: list[list] = []      # [나이, 글자]
        self.hover = False
        self._press = None
        self._dragging = False
        self._place()

    def _place(self) -> None:
        self.move(round(self.pos_x - WIN_W / 2), round(self.host.ground_y - WIN_H + GROUND_MARGIN))

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
        # 건물은 창 아래쪽 100×100 영역에 (바닥 = 창 아래)
        p.save()
        p.translate((WIN_W - 100) / 2, WIN_H - GROUND_MARGIN - 100)
        draw_hokora(p)
        p.restore()
        f = QFont("Malgun Gothic", 9)
        f.setBold(True)
        p.setFont(f)
        if self.hover and not self._dragging:
            _label(p, QRectF(0, 0, WIN_W, 22), f"새전 {self.saisen:,}")
        for age, text in self.pops:
            a = max(0.0, 1 - age / 1.6)
            y = 26 - age * 18
            p.setPen(QColor(200, 140, 20, int(255 * a)))
            p.drawText(QRectF(0, y, WIN_W, 20), Qt.AlignCenter, text)
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
        half = WIN_W / 2
        self.pos_x = min(max(x0 + dx, self.host.left + half), self.host.right - half)
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
