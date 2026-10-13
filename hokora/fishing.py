# -*- coding: utf-8 -*-
"""연못 낚시: 연못 장식을 누르면 낚싯대를 드리운다. 찌가 쏙 들어가는 순간 클릭!

- 미끼는 하루 15개 (날마다 채워짐). 너무 빨리 누르거나 늦으면 놓침 (미끼는 씀).
- 낚은 것은 바로 새전으로 (오이는 옷감, 용궁 상자는 새전 + 옷감). 낚시 도감에 기록.
- 밤엔 메기·장어가, 비 오는 날엔 물고기가, 여우비·오로라엔 귀한 것이 잘 걸린다.
- 그림: hokora/sprites/fish/<키>.png 가 있으면 그 그림, 없으면 코드로 그린 그림.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from datetime import date
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import season, weather
from .sprites import SPRITE_DIR
from .state import GameState

BAIT_PER_DAY = 15


@dataclass(frozen=True)
class Catch:
    key: str
    name: str
    weight: float
    value: float          # × 분당 수입
    cloth: int = 0
    kind: str = "fish"    # fish / junk / treasure
    night: bool = False   # 밤에 잘 걸림
    color: str = "#9AA0A6"


FISH = {c.key: c for c in [
    Catch("medaka", "송사리", 22, 2, color="#C9D3DC"),
    Catch("funa", "붕어", 20, 4, color="#9A7A4E"),
    Catch("goldfish", "금붕어", 12, 6, color="#F07A3A"),
    Catch("koi", "비단잉어", 8, 12, color="#E8E0D8"),
    Catch("catfish", "메기", 6, 14, night=True, color="#7A7E86"),
    Catch("eel", "장어", 5, 18, night=True, color="#5A4632"),
    Catch("can", "빈 깡통", 10, 0.5, kind="junk", color="#A8ADB4"),
    Catch("boot", "낡은 장화", 8, 0.5, kind="junk", color="#4E4038"),
    Catch("coins", "옛 동전 꾸러미", 4, 40, kind="treasure", color="#C89A3A"),
    Catch("cucumber", "오이", 3, 0, cloth=10, kind="treasure", color="#4FA34E"),
    Catch("tamatebako", "용궁 상자", 1.5, 80, cloth=20, kind="treasure", color="#2A2226"),
    Catch("golden_koi", "황금 잉어", 0.6, 200, kind="treasure", color="#F2C230"),
]}


def bait(s: GameState) -> int:
    """오늘 남은 미끼 (날이 바뀌면 다시 채워짐)."""
    if s.fish_bait_date != date.today().isoformat():
        return BAIT_PER_DAY
    return s.fish_bait


def use_bait(s: GameState) -> bool:
    n = bait(s)
    if n <= 0:
        return False
    s.fish_bait_date, s.fish_bait = date.today().isoformat(), n - 1
    return True


def roll(rng: random.Random | None = None) -> Catch:
    rng = rng or random.Random()
    w = weather.current().key
    night = season.is_night()
    weights = []
    for c in FISH.values():
        k = c.weight
        if c.night and night:
            k *= 3
        if w in ("drizzle", "storm") and c.kind == "fish":
            k *= 1.5
        if w in ("sunshower", "aurora") and c.kind == "treasure":
            k *= 2
        if w == "aurora" and c.key == "golden_koi":
            k *= 2
        weights.append(k)
    return rng.choices(list(FISH.values()), weights=weights)[0]


def reward(s: GameState, c: Catch) -> tuple[int, int]:
    """(새전, 옷감)."""
    return int(max(10, s.income_per_min) * c.value), c.cloth


def record(s: GameState, c: Catch) -> tuple[int, int, bool]:
    """낚은 것을 받고 기록 → (새전, 옷감, 처음 낚았는지)."""
    saisen, cloth = reward(s, c)
    first = c.key not in s.fish
    s.fish[c.key] = s.fish.get(c.key, 0) + 1
    if c.kind == "fish" or c.key == "golden_koi":            # 물고기만 셈 (깡통·장화·보물은 빼고)
        s.fish_caught += 1
    s.add_saisen(saisen)
    s.cloth += cloth
    return saisen, cloth, first


# ── 그림 ──
_images: dict[str, QImage | None] = {}


def image(key: str) -> QImage | None:
    if key not in _images:
        path = SPRITE_DIR / "fish" / f"{key}.png"
        img = QImage(str(path)) if path.exists() else QImage()
        _images[key] = None if img.isNull() else img
    return _images[key]


def draw_icon(p: QPainter, rect: QRectF, key: str, dim: bool = False) -> None:
    """낚을거리 그림 (그림 파일이 없으면 코드로). dim 이면 아직 못 낚은 실루엣."""
    c = FISH[key]
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    img = image(key)
    if img is not None:
        k = min(rect.width() / img.width(), rect.height() / img.height())
        w, h = img.width() * k, img.height() * k
        target = QRectF(rect.center().x() - w / 2, rect.center().y() - h / 2, w, h)
        if dim:
            sil = QImage(img.size(), QImage.Format_ARGB32_Premultiplied)
            sil.fill(Qt.transparent)
            sp = QPainter(sil)
            sp.drawImage(0, 0, img)
            sp.setCompositionMode(QPainter.CompositionMode_SourceIn)
            sp.fillRect(sil.rect(), QColor(70, 50, 58, 200))
            sp.end()
            p.drawImage(target, sil)
        else:
            p.drawImage(target, img)
        p.restore()
        return
    col = QColor(70, 50, 58, 170) if dim else QColor(c.color)
    out = QPen(QColor(70, 46, 40, 220 if not dim else 0), 1.4)
    cx, cy = rect.center().x(), rect.center().y()
    s = min(rect.width(), rect.height()) / 2
    p.setPen(out)
    p.setBrush(col)
    if c.kind == "fish" or key == "golden_koi":
        long = 1.6 if key == "eel" else 1.0
        body = QRectF(cx - s * 0.75 * long, cy - s * 0.38, s * 1.3 * long, s * 0.76)
        tail = QPainterPath()
        tx = body.left() + 2
        tail.moveTo(tx, cy)
        tail.lineTo(tx - s * 0.4, cy - s * 0.3)
        tail.lineTo(tx - s * 0.4, cy + s * 0.3)
        tail.closeSubpath()
        p.drawPath(tail)
        p.drawEllipse(body)
        if not dim:
            if key == "koi":
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#D9412E"))
                p.drawEllipse(QRectF(cx - s * 0.2, cy - s * 0.3, s * 0.4, s * 0.3))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(30, 20, 20))
            p.drawEllipse(QPointF(body.right() - s * 0.25, cy - s * 0.08), s * 0.07, s * 0.07)
            if key == "golden_koi":
                p.setBrush(QColor(255, 250, 200))
                for dx, dy in ((-0.6, -0.6), (0.7, -0.5), (0.5, 0.6)):
                    p.drawEllipse(QPointF(cx + s * dx, cy + s * dy), s * 0.08, s * 0.08)
    elif key == "can":
        p.drawRoundedRect(QRectF(cx - s * 0.35, cy - s * 0.5, s * 0.7, s * 1.0), 3, 3)
    elif key == "boot":
        path = QPainterPath()
        path.moveTo(cx - s * 0.3, cy - s * 0.6)
        path.lineTo(cx + s * 0.1, cy - s * 0.6)
        path.lineTo(cx + s * 0.1, cy + s * 0.15)
        path.lineTo(cx + s * 0.6, cy + s * 0.2)
        path.lineTo(cx + s * 0.6, cy + s * 0.55)
        path.lineTo(cx - s * 0.3, cy + s * 0.55)
        path.closeSubpath()
        p.drawPath(path)
    elif key == "coins":
        for i in range(3):
            p.drawEllipse(QPointF(cx - s * 0.4 + i * s * 0.4, cy), s * 0.28, s * 0.28)
    elif key == "cucumber":
        p.drawRoundedRect(QRectF(cx - s * 0.75, cy - s * 0.2, s * 1.5, s * 0.4), s * 0.2, s * 0.2)
    elif key == "tamatebako":
        p.drawRect(QRectF(cx - s * 0.5, cy - s * 0.35, s * 1.0, s * 0.7))
        p.setPen(QPen(QColor("#C8102E"), 2.2))
        p.drawLine(QPointF(cx, cy - s * 0.35), QPointF(cx, cy + s * 0.35))
    p.restore()


class FishingWindow(QWidget):
    """연못 위의 낚시 창: 찌가 쏙 들어가면 클릭."""

    W, H = 210, 150

    def __init__(self, cx: float, ground: float, bait_left: int, on_done: Callable[[str | None, str], None]):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.W, self.H)
        self.move(round(cx - self.W / 2), round(ground - self.H - 30))
        self.on_done = on_done
        self.bait_left = bait_left
        self.rng = random.Random()
        self.phase = "cast"
        self.t0 = time.monotonic()
        self.bite_at = self.t0 + 0.6 + self.rng.uniform(1.8, 5.5)
        self.bite_len = 0.85
        self.result: tuple[str | None, str] | None = None
        self.timer = QTimer(self, timeout=self._tick, interval=33)
        self.timer.start()

    def _tick(self) -> None:
        now = time.monotonic()
        if self.phase == "cast" and now - self.t0 > 0.6:
            self.phase = "wait"
        elif self.phase == "wait" and now >= self.bite_at:
            self.phase = "bite"
        elif self.phase == "bite" and now >= self.bite_at + self.bite_len:
            self._finish(None, "놓쳤다… 찌가 너무 빨리 올라왔어요")
        elif self.phase == "done" and now >= self.t_done + 1.6:
            self.close()
            return
        self.update()

    def _finish(self, key: str | None, msg: str) -> None:
        if self.phase == "done":
            return
        self.phase, self.t_done = "done", time.monotonic()
        self.result = (key, msg)
        self.on_done(key, msg)

    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.LeftButton:
            return
        if self.phase in ("cast", "wait"):
            self._finish(None, "앗, 너무 빨랐어요! 물고기가 도망갔어요")
        elif self.phase == "bite":
            self._finish(roll(self.rng).key, "")
        elif self.phase == "done":
            self.close()

    def paintEvent(self, _e) -> None:
        now = time.monotonic()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        panel = QRectF(4, 4, self.W - 8, self.H - 8)
        p.setPen(QPen(QColor(200, 16, 46, 110), 1.2))
        p.setBrush(QColor(255, 251, 245, 228))
        p.drawRoundedRect(panel, 12, 12)
        f = QFont("Malgun Gothic", 9)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#9E1027"))
        head = {"cast": "🎣 휙~", "wait": "찌를 보고 있다가…", "bite": "지금! 클릭!"}.get(self.phase, "")
        if self.phase == "done" and self.result:
            head = "🎣 낚았다!" if self.result[0] else "🎣 아쉽다…"
        p.drawText(QRectF(10, 8, self.W - 20, 20), Qt.AlignCenter, head)
        water = QRectF(18, 96, self.W - 36, 30)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(120, 190, 225, 170))
        p.drawEllipse(water)
        if self.phase != "done":
            bob = math.sin(now * 3.0) * 2
            dip = 0.0
            if self.phase == "bite":
                dip = 10 + math.sin(now * 30) * 3
            elif self.phase == "cast":
                dip = -40 * (1 - (now - self.t0) / 0.6)
            bx, by = self.W / 2, water.center().y() - 4 + bob + dip
            p.setPen(QPen(QColor(60, 50, 50, 180), 1))
            p.drawLine(QPointF(self.W / 2 + 40, 30), QPointF(bx, by - 8))
            p.setPen(QPen(QColor(70, 46, 40), 1.2))
            p.setBrush(QColor("#E23C52"))
            p.drawEllipse(QPointF(bx, by - 4), 5, 5)
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(QPointF(bx, by + 3), 5, 4)
            if self.phase == "bite":
                f2 = QFont("Malgun Gothic", 20)
                f2.setBold(True)
                p.setFont(f2)
                p.setPen(QColor("#C8102E"))
                p.drawText(QRectF(bx + 10, 40, 40, 40), Qt.AlignCenter, "!")
        elif self.result:
            key, msg = self.result
            if key:
                draw_icon(p, QRectF(self.W / 2 - 34, 34, 68, 50), key)
                p.setFont(f)
                p.setPen(QColor("#3A2A2E"))
                p.drawText(QRectF(10, 92, self.W - 20, 20), Qt.AlignCenter, FISH[key].name)
            else:
                f3 = QFont("Malgun Gothic", 8)
                p.setFont(f3)
                p.setPen(QColor("#5A464B"))
                p.drawText(QRectF(14, 40, self.W - 28, 50), Qt.AlignCenter | Qt.TextWordWrap, msg)
        f4 = QFont("Malgun Gothic", 7)
        p.setFont(f4)
        p.setPen(QColor("#8C7479"))
        p.drawText(QRectF(10, self.H - 22, self.W - 20, 14), Qt.AlignCenter, f"오늘 남은 미끼 {self.bait_left}개")
        p.end()
