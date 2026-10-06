# -*- coding: utf-8 -*-
"""사진 찍기: 신사와 친구들을 폴라로이드 사진처럼 한 장으로 저장한다.

화면을 그대로 캡처하지 않고 Hokora 의 창(신사·장식·캐릭터·손님)만 하늘 배경 위에 다시 그린다.
그래서 뒤에 열려 있던 창이나 바탕화면은 사진에 찍히지 않는다.
사진은 '사진\\Hokora' 폴더에 저장하고 클립보드에도 복사한다.
"""
from __future__ import annotations

import math
import os
import random
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import season

SKY_H = 250            # 바닥 위로 찍는 높이
GROUND_H = 26          # 사진 아래쪽 땅
MIN_W = 520
MAX_W = 1100           # 이보다 넓으면 신사를 가운데 두고 자름
BORDER, CAPTION = 14, 50
SCALE = 2.0            # 저장 배율 (선명하게)


def photo_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) or str(Path.home() / "Pictures")
    return Path(base) / "Hokora"


def _sky(p: QPainter, rect: QRectF, now: datetime, kind: str) -> None:
    h = now.hour
    g = QLinearGradient(0, rect.top(), 0, rect.bottom())
    if season.is_night(now):
        g.setColorAt(0, QColor("#1B2350"))
        g.setColorAt(1, QColor("#3E4A86"))
    elif 16 <= h < season.NIGHT_FROM:
        g.setColorAt(0, QColor("#F4A98C"))
        g.setColorAt(1, QColor("#FCE3C4"))
    else:
        g.setColorAt(0, QColor("#9ED3F2"))
        g.setColorAt(1, QColor("#EAF6FD"))
    p.fillRect(rect, g)
    rng = random.Random(now.toordinal())
    if season.is_night(now):                                  # 별과 달
        p.setPen(Qt.NoPen)
        for _ in range(int(rect.width() / 14)):
            x, y = rng.uniform(rect.left(), rect.right()), rng.uniform(rect.top(), rect.top() + rect.height() * 0.6)
            p.setBrush(QColor(255, 255, 230, rng.randint(120, 230)))
            r = rng.uniform(0.6, 1.5)
            p.drawEllipse(QPointF(x, y), r, r)
        mx, my = rect.right() - 60, rect.top() + 46
        p.setBrush(QColor(255, 244, 200))
        p.drawEllipse(QPointF(mx, my), 18, 18)
        p.setBrush(QColor("#232C5C"))
        p.drawEllipse(QPointF(mx + 8, my - 5), 15, 15)
    # 먼 산 두 겹
    for depth, (col, amp, base) in enumerate(((QColor(255, 255, 255, 70), 26, 0.62), (QColor(255, 255, 255, 110), 16, 0.78))):
        if season.is_night(now):
            col = QColor(20, 26, 60, 90 + depth * 40)
        path = QPainterPath()
        y0 = rect.top() + rect.height() * base
        path.moveTo(rect.left(), rect.bottom())
        steps = 40
        ph = rng.uniform(0, 6.28)
        for i in range(steps + 1):
            x = rect.left() + rect.width() * i / steps
            path.lineTo(x, y0 - amp * (0.6 + 0.4 * math.sin(i * 0.45 + ph)) - amp * 0.5 * math.sin(i * 0.17 + ph * 2))
        path.lineTo(rect.right(), rect.bottom())
        path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawPath(path)


def _ground(p: QPainter, rect: QRectF, kind: str, night: bool) -> None:
    top, bottom = {"petal": ("#A9D48A", "#86B866"), "firefly": ("#8CC46E", "#6BA24F"),
                   "leaf": ("#D6B27A", "#B88E55"), "snow": ("#F6F8FC", "#DDE4EF")}.get(kind, ("#A9D48A", "#86B866"))
    g = QLinearGradient(0, rect.top(), 0, rect.bottom())
    g.setColorAt(0, QColor(top))
    g.setColorAt(1, QColor(bottom))
    p.fillRect(rect, g)
    if night:
        p.fillRect(rect, QColor(20, 26, 70, 90))
    p.setPen(QPen(QColor(0, 0, 0, 30), 1))
    p.drawLine(QPointF(rect.left(), rect.top()), QPointF(rect.right(), rect.top()))


def take(game) -> tuple[QImage, Path] | None:
    """지금 신사 둘레를 사진으로 (저장한 경로와 함께). 찍을 게 없으면 None."""
    g = game.ground_under(game.shrine.pos_x)
    top = g.y - SKY_H
    subjects = [w for w in game.windows() if w.isVisible() and not isinstance(w, season.SeasonFx)]
    shots = []
    for w in subjects:
        r = w.geometry()
        if r.right() < g.x1 or r.left() > g.x2 or r.bottom() < top or r.top() > g.y + 20:
            continue
        shots.append(w)
    if not shots:
        return None
    x0 = min(w.x() for w in shots) - 40
    x1 = max(w.x() + w.width() for w in shots) + 40
    if x1 - x0 < MIN_W:
        c = (x0 + x1) / 2
        x0, x1 = c - MIN_W / 2, c + MIN_W / 2
    elif x1 - x0 > MAX_W:
        c = min(max(game.shrine.pos_x, x0 + MAX_W / 2), x1 - MAX_W / 2)
        x0, x1 = c - MAX_W / 2, c + MAX_W / 2
    x0, x1 = max(x0, g.x1), min(x1, g.x2)
    w_, h_ = x1 - x0, SKY_H + GROUND_H
    now = datetime.now()
    kind = season.fx_kind(now) or ("petal" if season.season(now) == "spring" else "")
    night = season.is_night(now)

    W, H = w_ + BORDER * 2, h_ + BORDER + CAPTION
    img = QImage(int(W * SCALE), int(H * SCALE), QImage.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(SCALE)
    img.fill(QColor("#FFFDF8"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    scene = QRectF(BORDER, BORDER, w_, h_)
    p.save()
    p.setClipRect(scene)
    _sky(p, QRectF(BORDER, BORDER, w_, SKY_H + 2), now, kind)
    _ground(p, QRectF(BORDER, BORDER + SKY_H, w_, GROUND_H), kind, night)
    rng = random.Random()
    if kind:
        season.scatter(p, kind, QRectF(BORDER, BORDER + 10, w_, SKY_H - 20), int(w_ / 60), rng)
    for w in shots:                                          # 뒤 → 앞 (windows() 순서)
        pm = w.grab()
        p.drawPixmap(QPointF(BORDER + w.x() - x0, BORDER + w.y() - top), pm)
    if kind in ("petal", "leaf", "snow"):                   # 앞쪽에도 몇 장
        season.scatter(p, kind, QRectF(BORDER, BORDER + SKY_H - 30, w_, GROUND_H + 24), int(w_ / 120), rng)
    p.restore()
    p.setPen(QPen(QColor(0, 0, 0, 40), 1))
    p.setBrush(Qt.NoBrush)
    p.drawRect(scene)
    # 아래 글씨: 신사 이름·친구 수 / 날짜
    s = game.state
    f = QFont("Malgun Gothic", 12)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#B3122C"))
    inside = [w for w in shots if x0 <= w.x() + w.width() / 2 <= x1]
    friends = len([w for w in inside if w in game.pets])
    guests = len([w for w in inside if w in game.guests])
    cap = (f"⛩ {s.stage_name}   ·   친구 {friends}명" + (f" · 손님 {guests}명" if guests else "")
           + (f"   ·   도리이 {s.torii:,}개" if s.torii else ""))
    p.drawText(QRectF(BORDER + 4, BORDER + h_ + 6, W, 24), Qt.AlignLeft | Qt.AlignVCenter, cap)
    f2 = QFont("Malgun Gothic", 10)
    p.setFont(f2)
    p.setPen(QColor("#6E5F55"))
    p.drawText(QRectF(0, BORDER + h_ + 6, W - BORDER - 4, 24), Qt.AlignRight | Qt.AlignVCenter,
               f"{now.year}. {now.month}. {now.day}.  {season.SEASON_NAME[season.season(now)]}")
    f3 = QFont("Malgun Gothic", 7)
    p.setFont(f3)
    p.setPen(QColor("#A8989C"))
    p.drawText(QRectF(0, BORDER + h_ + 28, W - BORDER - 4, 16), Qt.AlignRight | Qt.AlignVCenter,
               "Hokora · 東方Project二次創作")
    p.end()

    folder = photo_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"hokora_{now:%Y%m%d_%H%M%S}.png"
    img.save(str(path))
    return img, path


def to_clipboard(img: QImage) -> None:
    """바로 붙여 넣어 자랑할 수 있게."""
    QGuiApplication.clipboard().setImage(img)


class PhotoCard(QWidget):
    """찍은 사진 미리보기. 누르면 사진을 열고, 12초 뒤 저절로 닫힌다."""

    W = 340

    def __init__(self, img: QImage, path: Path):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setCursor(Qt.PointingHandCursor)
        self.path = path
        self.thumb = img
        iw = self.W - 28
        self.th = iw * img.height() / max(1, img.width())
        self.setFixedSize(self.W, int(self.th + 84))

    def show_above(self, cx: float, bottom: float) -> None:
        self.move(round(cx - self.width() / 2), round(bottom - self.height() - 8))
        self.show()
        QTimer.singleShot(12_000, self.close)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            try:
                os.startfile(str(self.path))             # 윈도우 사진 앱으로 열기
            except (OSError, AttributeError):
                pass
        self.close()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        p.setPen(QPen(QColor(200, 16, 46, 120), 1.2))
        p.setBrush(QColor(255, 250, 244, 250))
        p.drawPath(path)
        f = QFont("Malgun Gothic", 11)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#B3122C"))
        p.drawText(QRectF(14, 10, self.W - 28, 22), Qt.AlignLeft | Qt.AlignVCenter, "📸 찰칵! 사진을 저장했어요")
        p.drawImage(QRectF(14, 38, self.W - 28, self.th), self.thumb)
        f2 = QFont("Malgun Gothic", 8)
        p.setFont(f2)
        p.setPen(QColor("#8C7479"))
        p.drawText(QRectF(14, 42 + self.th, self.W - 28, 16), Qt.AlignCenter,
                   "'사진 › Hokora' 폴더에 저장  ·  클립보드에도 복사됨")
        p.drawText(QRectF(14, 58 + self.th, self.W - 28, 16), Qt.AlignCenter, "눌러서 사진 열기")
        p.end()
