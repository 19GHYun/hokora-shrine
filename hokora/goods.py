# -*- coding: utf-8 -*-
"""새전으로 여는 놀잇감: 요술 붓(길 그리기)·미닫이문(신사 안 들여다보기). 처음 쓰려고 하면 사는 카드가 뜬다."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .panel import STYLE

if TYPE_CHECKING:
    from .app import Game


@dataclass(frozen=True)
class Goods:
    key: str
    icon: str
    name: str
    price: int
    desc: str
    use: str           # 사고 나서 쓰는 메뉴 이름


GOODS = {g.key: g for g in [
    Goods("brush", "✏️", "요술 붓", 20_000,
          "화면에 선을 그으면 길이 돼요. 친구들이 그 위를 걸어 다니고, 가파른 곳에선 미끄럼을 타요.\n"
          "그린 길은 10분 뒤 사라지고, 색은 먹·주홍·벚꽃·하늘 네 가지예요.",
          "✏️ 길 그리기"),
    Goods("room", "🏠", "신사 미닫이문", 30_000,
          "신사 안을 들여다볼 수 있어요. 쉬는 친구들이 코타츠에서 귤을 까먹거나 낮잠을 자요.\n"
          "둥근 창으로는 오늘의 날씨·계절·진짜 달이 보이고, 낚은 물고기는 어항에서 헤엄쳐요.",
          "🏠 신사 안 들여다보기"),
]}


class GoodsCard(QWidget):
    """놀잇감 사기 카드."""

    def __init__(self, game: "Game", key: str):
        super().__init__(None, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("panel")
        self.setStyleSheet(STYLE)
        self.game, self.goods = game, GOODS[key]
        g, s = self.goods, game.state
        self.setFixedWidth(380)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 16)
        v.setSpacing(8)
        v.addWidget(QLabel(f"{g.icon}  {g.name}", objectName="title"))
        desc = QLabel(g.desc, objectName="goal")
        desc.setWordWrap(True)
        v.addWidget(desc)
        row = QHBoxLayout()
        have = QLabel(f"가진 새전 {s.saisen:,}", objectName="sub")
        row.addWidget(have, 1)
        later = QPushButton("다음에", objectName="ghost")
        later.setCursor(Qt.PointingHandCursor)
        later.clicked.connect(self.close)
        self.buy_btn = QPushButton(f"새전 {g.price:,}으로 사기", objectName="upgrade")
        self.buy_btn.setCursor(Qt.PointingHandCursor)
        self.buy_btn.setEnabled(s.saisen >= g.price)
        if s.saisen < g.price:
            self.buy_btn.setToolTip(f"새전이 {g.price - s.saisen:,} 모자라요")
        self.buy_btn.clicked.connect(self._buy)
        row.addWidget(later)
        row.addWidget(self.buy_btn)
        v.addLayout(row)

    def _buy(self) -> None:
        if self.game.buy_goods(self.goods.key):
            self.close()
            self.game.use_goods(self.goods.key)

    def show_near(self, pos: QPoint) -> None:
        self.adjustSize()
        sc = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        area = sc.availableGeometry()
        x = min(max(pos.x() - self.width() // 2, area.left() + 8), area.right() - self.width() - 8)
        y = min(max(pos.y() - self.height() - 10, area.top() + 8), area.bottom() - self.height() - 8)
        self.move(x, y)
        self.show()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        p.setPen(QPen(QColor(200, 16, 46, 120), 1.2))
        p.setBrush(QColor(255, 247, 248, 248))
        p.drawPath(path)
        p.save()
        p.setClipPath(path)
        p.fillRect(QRectF(r.left(), r.top(), r.width(), 4), QColor("#C8102E"))
        p.restore()
        p.end()
