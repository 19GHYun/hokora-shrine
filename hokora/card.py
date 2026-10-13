# -*- coding: utf-8 -*-
"""신사 명함: 내 신사(단계·칭호·친구·도리이·업적)를 한 장짜리 카드 그림으로. 사진 폴더에 저장 + 클립보드."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen

from . import achievements, moon, photo
from .render import CHARACTERS

W, H = 1200, 675
SCALE = 1.0


def _days_together(created: str) -> int:
    try:
        return max(1, (datetime.now() - datetime.fromisoformat(created)).days + 1)
    except ValueError:
        return 1


def make(game) -> tuple[QImage, Path]:
    from .guests import VISITS
    from .panel import portrait
    s = game.state
    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    bg = QLinearGradient(0, 0, W, H)                 # 바탕: 연한 크림 → 분홍
    bg.setColorAt(0, QColor("#FFF8EC"))
    bg.setColorAt(1, QColor("#FBE3E7"))
    p.fillRect(QRectF(0, 0, W, H), bg)
    p.setPen(Qt.NoPen)                               # 은은한 동그라미 무늬
    for i in range(14):
        p.setBrush(QColor(200, 16, 46, 10))
        p.drawEllipse(QPointF((i * 173) % W, (i * 97) % H), 60 + (i % 4) * 20, 60 + (i % 4) * 20)
    frame = QRectF(18, 18, W - 36, H - 36)
    p.setPen(QPen(QColor("#C8102E"), 4))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(frame, 26, 26)
    p.setPen(QPen(QColor(200, 16, 46, 90), 1.5))
    p.drawRoundedRect(frame.adjusted(10, 10, -10, -10), 20, 20)

    # 왼쪽: 신사 그림 (지금 보이는 모습 그대로)
    shrine = game.shrine.grab().toImage()
    box = QRectF(60, 90, 430, 330)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 170))
    p.drawRoundedRect(box, 22, 22)
    k = min((box.width() - 40) / max(1, shrine.width()), (box.height() - 40) / max(1, shrine.height()))
    sw, sh = shrine.width() * k, shrine.height() * k
    p.drawImage(QRectF(box.center().x() - sw / 2, box.bottom() - 20 - sh, sw, sh), shrine)
    moon.draw(p, box.right() - 42, box.top() + 42, 20, dark=QColor(90, 100, 150, 110))   # 오늘의 달

    # 오른쪽: 이름·칭호·숫자들
    x0 = 530
    f = QFont("Malgun Gothic", 14)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#8C7479"))
    p.drawText(QRectF(x0, 66, 600, 30), Qt.AlignLeft | Qt.AlignVCenter, "HOKORA · 나의 신사")
    f2 = QFont("Malgun Gothic", 38)
    f2.setBold(True)
    path = QPainterPath()
    from .shrine import _torii
    p.save()
    _torii(p, x0, 150, 44, 50)                       # 작은 도리이 (그림 문자 대신 직접 그림)
    p.restore()
    path.addText(QPointF(x0 + 58, 150), f2, s.stage_name)
    p.strokePath(path, QPen(QColor("#FFFFFF"), 8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.fillPath(path, QColor("#B3122C"))
    ttl = achievements.title(s)
    f3 = QFont("Malgun Gothic", 18)
    f3.setBold(True)
    p.setFont(f3)
    p.setPen(QColor("#B8860B"))
    p.drawText(QRectF(x0, 166, 620, 34), Qt.AlignLeft | Qt.AlignVCenter, f"「{ttl}」" if ttl else f"신사 {s.shrine_level}단계")
    guests_met = sum(1 for ks, _ in VISITS.values() for g in ks if s.guest_visits.get(g))
    guests_all = sum(len(ks) for ks, _ in VISITS.values())
    stats = [
        ("모은 새전", f"{s.saisen_total:,}"),
        ("함께한 날", f"{_days_together(s.created)}일"),
        ("친구", f"{len(s.unlocked)}명"),
        ("만난 손님", f"{guests_met}/{guests_all}"),
        ("도리이", f"{s.torii:,}개"),
        ("업적", f"{len(s.achievements)}/{len(achievements.ACHIEVEMENTS)}"),
    ]
    f4 = QFont("Malgun Gothic", 13)
    f5 = QFont("Malgun Gothic", 21)
    f5.setBold(True)
    for i, (label, value) in enumerate(stats):
        cx, cy = x0 + (i % 3) * 205, 222 + (i // 3) * 98
        cell = QRectF(cx, cy, 190, 84)
        p.setPen(QPen(QColor(200, 16, 46, 50), 1.2))
        p.setBrush(QColor(255, 255, 255, 200))
        p.drawRoundedRect(cell, 14, 14)
        p.setFont(f4)
        p.setPen(QColor("#8C7479"))
        p.drawText(cell.adjusted(14, 8, -10, -44), Qt.AlignLeft | Qt.AlignVCenter, label)
        p.setFont(f5)
        p.setPen(QColor("#3A2A2E"))
        p.drawText(cell.adjusted(14, 32, -10, -6), Qt.AlignLeft | Qt.AlignVCenter, value)

    # 아래: 친구들 (입은 옷 그대로)
    friends = [k for k in CHARACTERS if k in s.unlocked]
    size = 92
    gap = min(112.0, (W - 140) / max(1, len(friends)))
    y = 452
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 150))
    p.drawRoundedRect(QRectF(60, y - 8, W - 120, size + 40), 22, 22)
    start = W / 2 - gap * len(friends) / 2
    for i, key in enumerate(friends):
        pm = portrait(key, size, False, s.skins.get(key))
        p.drawPixmap(QRectF(start + i * gap + (gap - size) / 2, y, size, size).toRect(), pm)
    f6 = QFont("Malgun Gothic", 11)
    p.setFont(f6)
    p.setPen(QColor("#8C7479"))
    now = datetime.now()
    p.drawText(QRectF(60, H - 70, W - 120, 24), Qt.AlignLeft | Qt.AlignVCenter,
               f"{now.year}. {now.month}. {now.day}.  ·  {moon.name()[1]} {moon.name()[0]}")
    p.drawText(QRectF(60, H - 70, W - 120, 24), Qt.AlignRight | Qt.AlignVCenter,
               "Hokora — 작업표시줄 위의 나만의 신사 · 東方Project二次創作")
    p.end()
    folder = photo.photo_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path_ = folder / f"hokora_card_{now:%Y%m%d_%H%M%S}.png"
    img.save(str(path_))
    return img, path_
