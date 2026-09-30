# -*- coding: utf-8 -*-
"""신사 장식 하나 = 바닥 위의 작은 창. 좌우로 끌어서 옮기고, 누르면 신사 관리 창이 열린다."""
from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QWidget

from .season import lamp_glow

from .sprites import SPRITE_DIR
from .state import DECOR

GROUND_MARGIN = 2


class DecorHost(Protocol):
    def ground_under(self, x: float): ...
    def on_decor_moved(self, key: str, x: float) -> None: ...
    def on_shrine_clicked(self, global_pos=None) -> None: ...
    def on_context_menu(self, global_pos) -> None: ...


_images: dict[str, QImage] = {}


def decor_image(key: str) -> QImage:
    if key not in _images:
        _images[key] = QImage(str(SPRITE_DIR / "props" / f"{key}.png"))
    return _images[key]


class DecorWindow(QWidget):
    def __init__(self, host: DecorHost, key: str, x: float):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setCursor(Qt.PointingHandCursor)
        self.host, self.key = host, key
        name, _, bonus, height = DECOR[key]
        self.setToolTip(f"{name}  (분당 새전 +{bonus})")
        img = decor_image(key)
        self.scale = height / max(1, img.height())
        self.setFixedSize(max(10, round(img.width() * self.scale)), height + GROUND_MARGIN)
        self.pos_x = x
        self.night = False
        self._press = None
        self._dragging = False
        self.pos_x = self._clamp(x)
        self._place()

    @staticmethod
    def width_for(key: str) -> float:
        img = decor_image(key)
        return img.width() * DECOR[key][3] / max(1, img.height())

    def _clamp(self, x: float) -> float:
        g = self.host.ground_under(x)
        half = self.width() / 2
        return min(max(x, g.x1 + half), g.x2 - half)

    def _place(self) -> None:
        ground = self.host.ground_under(self.pos_x).y
        self.move(round(self.pos_x - self.width() / 2), round(ground - self.height() + GROUND_MARGIN))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        h = self.height() - GROUND_MARGIN
        p.drawImage(QRectF(0, 0, self.width(), h), decor_image(self.key))
        if self.night and self.key == "lantern":           # 밤: 돌등롱에 불
            p.setRenderHint(QPainter.Antialiasing)
            lamp_glow(p, self.width() / 2, h * 0.37, min(self.width(), h) * 0.5)
        p.end()

    def set_night(self, on: bool) -> None:
        if on != self.night:
            self.night = on
            self.update()

    # ── 마우스: 끌면 옆으로 옮기기, 누르면 신사 관리 창 ──
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
            self.host.on_decor_moved(self.key, self.pos_x)
        else:
            self.host.on_shrine_clicked()
