# -*- coding: utf-8 -*-
"""진짜 달 모양: 오늘 달이 어떤 모양인지 계산한다 (인터넷 없이, 삭망월 평균으로 ±반나절 정도).

- 보름달 밤: 새전 수입 ×1.3, 레밀리아가 신남
- 그믐(삭) 밤: 손님이 잘 옴 ×1.5
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

SYNODIC = 29.530588853                          # 삭망월 (일)
NEW_MOON_REF = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)   # 기준 삭
FULL_INCOME = 1.3
NEW_GUESTS = 1.5
NAMES = [  # (월령 끝, 이름, 그림 문자)
    (1.85, "삭", "🌑"), (5.54, "초승달", "🌒"), (9.23, "상현달", "🌓"), (12.92, "차오르는 달", "🌔"),
    (16.61, "보름달", "🌕"), (20.30, "기우는 달", "🌖"), (23.99, "하현달", "🌗"), (27.68, "그믐달", "🌘"),
    (SYNODIC + 1, "삭", "🌑"),
]


def age(now: datetime | None = None) -> float:
    """월령 (삭으로부터 며칠, 0 ~ 29.5)."""
    now = now or datetime.now().astimezone()
    if now.tzinfo is None:
        now = now.astimezone()
    days = (now - NEW_MOON_REF).total_seconds() / 86400
    return days % SYNODIC


def phase(now: datetime | None = None) -> float:
    """0 = 삭, 0.5 = 보름, 1 = 다시 삭."""
    return age(now) / SYNODIC


def illumination(now: datetime | None = None) -> float:
    return (1 - math.cos(2 * math.pi * phase(now))) / 2


def name(now: datetime | None = None) -> tuple[str, str]:
    a = age(now)
    return next((n, e) for end, n, e in NAMES if a < end)


def is_full(now: datetime | None = None) -> bool:
    return 13.3 <= age(now) <= 16.3


def is_new(now: datetime | None = None) -> bool:
    a = age(now)
    return a < 1.5 or a > SYNODIC - 1.5


def draw(p: QPainter, cx: float, cy: float, r: float, ph: float | None = None, dark: QColor | None = None) -> None:
    """그 위상의 달 (밝은 부분 + 어두운 부분)."""
    ph = phase() if ph is None else ph
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(dark or QColor(40, 48, 90, 200))
    p.drawEllipse(QPointF(cx, cy), r, r)
    a = r * math.cos(2 * math.pi * ph)            # 경계선(명암 경계) 타원의 가로 반지름
    side = 1 if ph < 0.5 else -1                  # 차오를 땐 오른쪽, 기울 땐 왼쪽이 밝음
    lit = QPainterPath()
    steps = 40
    lit.moveTo(cx, cy - r)
    for i in range(steps + 1):                    # 바깥 반원
        t = math.pi * i / steps
        lit.lineTo(cx + side * r * math.sin(t), cy - r * math.cos(t))
    for i in range(steps + 1):                    # 경계선 (아래 → 위)
        t = math.pi * i / steps
        lit.lineTo(cx + side * a * math.sin(math.pi - t), cy + r * math.cos(t))
    lit.closeSubpath()
    p.setBrush(QColor(255, 244, 200))
    p.drawPath(lit)
    p.setPen(QPen(QColor(255, 244, 200, 90), 1))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
    p.restore()
