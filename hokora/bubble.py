# -*- coding: utf-8 -*-
"""신사나 캐릭터 위에 잠깐 떴다 사라지는 말풍선 (캐릭터 도착, 신사 업그레이드 등)."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

PAD_X, PAD_Y, TAIL = 12, 7, 8


class Bubble(QWidget):
    def __init__(self, text: str, seconds: float = 4.0):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowDoesNotAcceptFocus
                         | Qt.WindowTransparentForInput)   # 클릭은 통과
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.text = text
        self.font_ = QFont("Malgun Gothic", 10)
        self.font_.setBold(True)
        fm = QFontMetricsF(self.font_)
        self.setFixedSize(int(fm.horizontalAdvance(text) + PAD_X * 2 + 4), int(fm.height() + PAD_Y * 2 + TAIL + 4))
        QTimer.singleShot(int(seconds * 1000), self.close)

    def show_at(self, cx: float, bottom: float) -> None:
        """말풍선 꼬리 끝이 (cx, bottom) 에 오게."""
        self.move(round(cx - self.width() / 2), round(bottom - self.height()))
        self.show()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        body = QRectF(2, 2, self.width() - 4, self.height() - TAIL - 4)
        path = QPainterPath()
        path.addRoundedRect(body, body.height() / 2, body.height() / 2)
        tail = QPainterPath()
        cx = self.width() / 2
        tail.moveTo(cx - 7, body.bottom() - 1)
        tail.lineTo(cx, self.height() - 2)
        tail.lineTo(cx + 7, body.bottom() - 1)
        tail.closeSubpath()
        path = path.united(tail)
        p.setPen(QPen(QColor(200, 16, 46, 170), 1.4))
        p.setBrush(QColor(255, 255, 255, 245))
        p.drawPath(path)
        p.setFont(self.font_)
        p.setPen(QColor("#9E1027"))
        p.drawText(body, Qt.AlignCenter, self.text)
        p.end()


_alive: list[Bubble] = []


def say(text: str, cx: float, bottom: float, seconds: float = 4.0) -> None:
    b = Bubble(text, seconds)
    _alive.append(b)
    b.destroyed.connect(lambda *_: _alive.remove(b) if b in _alive else None)
    b.show_at(cx, bottom)

