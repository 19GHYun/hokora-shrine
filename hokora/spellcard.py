# -*- coding: utf-8 -*-
"""스펠카드 컷인: 특기를 쓸 때 화면에 스펠카드 이름이 휙 지나간다 (동방 STG 처럼).

캐릭터 그림(특기 장면) + 캐릭터 색 띠 + 「스펠카드 이름」. 클릭은 뒤로 통과, 1.8초쯤 뒤 사라진다.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .play import SHOT_COLORS

SPELLS = {
    "reimu": ("영부", "몽상봉인"),
    "marisa": ("절도", "빌려 갈 뿐이다제"),
    "sakuya": ("환세", "더 월드"),
    "cirno": ("빙부", "아이시클 폴"),
    "sanae": ("비술", "그레이 소머터지"),
    "remilia": ("신술", "흡혈귀 환상"),
    "flandre": ("금기", "레바테인"),
    "youmu": ("인부", "현세참"),
    "meiling": ("채부", "채광난무"),
}
MIN_GAP = 20.0          # 컷인끼리 최소 간격 (초)
SHOW = 1.9              # 보이는 시간
W, H = 600, 132


class CutIn(QWidget):
    def __init__(self, key: str, name: str, portrait, cx: float, ground: float, screen_left: float, screen_right: float):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFixedSize(W, H)
        x = min(max(cx - W / 2, screen_left + 8), screen_right - W - 8)
        self.move(round(x), round(ground - 150 - H))
        self.kind, self.text = SPELLS.get(key, ("", ""))
        self.name = name
        self.portrait = portrait                   # (QImage, 발 위치) 또는 None
        col, rim = SHOT_COLORS.get(key, ("#C8102E", "#FFFFFF"))
        self.col, self.rim = QColor(col), QColor(rim)
        self.start = time.monotonic()
        self.timer = QTimer(self, timeout=self._tick, interval=16)
        self.timer.start()

    def _tick(self) -> None:
        if time.monotonic() - self.start > SHOW:
            self.close()
        else:
            self.update()

    def paintEvent(self, _e) -> None:
        t = time.monotonic() - self.start
        # 들어옴(0.22초) → 머묾 → 나감(마지막 0.3초): 띠가 왼쪽에서 밀려 들어와 오른쪽으로 빠져나감
        if t < 0.22:
            k = 1 - (1 - t / 0.22) ** 3
            shift, alpha = -(1 - k) * W * 0.6, k
        elif t > SHOW - 0.3:
            k = (t - (SHOW - 0.3)) / 0.3
            shift, alpha = k * W * 0.5, 1 - k
        else:
            shift, alpha = (t - 0.22) * 14, 1.0
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setOpacity(max(0.0, min(1.0, alpha)))
        p.translate(shift, 0)
        band = QPainterPath()                      # 비스듬한 띠
        band.moveTo(40, 30)
        band.lineTo(W - 10, 22)
        band.lineTo(W - 40, H - 22)
        band.lineTo(10, H - 14)
        band.closeSubpath()
        g = QLinearGradient(0, 0, W, 0)
        dark = QColor(self.col).darker(170)
        dark.setAlpha(225)
        g.setColorAt(0, dark)
        mid = QColor(self.col)
        mid.setAlpha(215)
        g.setColorAt(0.55, mid)
        g.setColorAt(1, QColor(mid.red(), mid.green(), mid.blue(), 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawPath(band)
        p.setPen(QPen(QColor(255, 255, 255, 170), 2))
        p.drawLine(QPointF(40, 30), QPointF(W - 10, 22))
        p.drawLine(QPointF(10, H - 14), QPointF(W - 40, H - 22))
        if self.portrait is not None:              # 캐릭터 (띠 밖으로 살짝 튀어나오게 크게)
            img, _ = self.portrait
            ph = H + 6
            pw = img.width() * ph / max(1, img.height())
            p.drawImage(QRectF(18, H - ph - 2, pw, ph), img)
        f_small = QFont("Malgun Gothic", 11)
        f_small.setBold(True)
        f_big = QFont("Malgun Gothic", 22)
        f_big.setBold(True)
        x0 = 150
        p.setFont(f_small)
        p.setPen(QColor(255, 255, 255, 220))
        p.drawText(QRectF(x0, 30, W - x0 - 30, 22), Qt.AlignLeft | Qt.AlignVCenter, self.name)
        label = f"{self.kind}「{self.text}」"
        path = QPainterPath()
        path.addText(QPointF(x0, 88), f_big, label)
        p.strokePath(path, QPen(dark, 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.fillPath(path, QColor("#FFFFFF"))
        p.end()
