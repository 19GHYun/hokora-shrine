# -*- coding: utf-8 -*-
"""
작은 봉제인형 스타일 캐릭터를 QPainter 로 그린다.

모든 캐릭터는 같은 몸(큰 머리 + 짧은 몸통)을 쓰고, 색과 장식만 다르다.
설계 좌표계는 폭 100 × 높이 120, 발바닥 가운데가 (50, 118).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QRadialGradient

DESIGN_W, DESIGN_H = 100.0, 120.0
FOOT_X, FOOT_Y = 50.0, 118.0

SKIN = QColor("#FFE6D8")
SKIN_SHADE = QColor("#F6C9B5")
OUTLINE = QColor(60, 36, 40, 200)
BLUSH = QColor(255, 120, 140, 110)


@dataclass
class Pose:
    """그릴 때의 자세. t 는 초 단위 시간(애니메이션 위상)."""
    kind: str = "idle"        # idle / walk / sit / held / fall / happy / sleep
    t: float = 0.0
    facing: int = 1           # 1 = 오른쪽, -1 = 왼쪽
    squash: float = 0.0       # +면 납작, -면 길쭉 (착지·쓰다듬기)
    tilt: float = 0.0         # 도 단위 기울기
    blink: bool | None = None  # None 이면 t 로 알아서 깜빡임


@dataclass
class Character:
    key: str
    name: str                 # 표시 이름
    hair: str
    hair_dark: str
    eyes: str
    dress: str
    dress_dark: str
    trim: str = "#FFFFFF"     # 옷 가장자리
    shoes: str = "#4A3036"
    sleeves: str | None = None  # 소매 색 (None 이면 dress)
    side_locks: bool = True
    accessory_back: Callable[["Painter", "Character", Pose], None] | None = None   # 머리 뒤 장식
    accessory_front: Callable[["Painter", "Character", Pose], None] | None = None  # 머리 앞 장식
    extra_body: Callable[["Painter", "Character", Pose], None] | None = None       # 몸 뒤 장식(날개 등)
    tags: dict = field(default_factory=dict)


class Painter:
    """QPainter 에 봉제인형용 도우미를 붙인 얇은 래퍼."""

    def __init__(self, p: QPainter):
        self.p = p

    def shape(self, path: QPainterPath, fill: QColor | QBrush, outline: bool = True, width: float = 1.6) -> None:
        self.p.setPen(QPen(OUTLINE, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin) if outline else Qt.NoPen)
        self.p.setBrush(fill)
        self.p.drawPath(path)

    def ellipse(self, cx, cy, w, h, fill, outline=True, width=1.6) -> None:
        path = QPainterPath()
        path.addEllipse(QRectF(cx - w / 2, cy - h / 2, w, h))
        self.shape(path, fill, outline, width)


def _c(x) -> QColor:
    return x if isinstance(x, QColor) else QColor(x)


# ─────────────────────────────── 몸 부분 ───────────────────────────────
def _feet(pp: Painter, ch: Character, pose: Pose) -> None:
    lift_l = lift_r = 0.0
    if pose.kind == "walk":
        phase = pose.t * 9.0
        lift_l = max(0.0, math.sin(phase)) * 5
        lift_r = max(0.0, -math.sin(phase)) * 5
    elif pose.kind in ("held", "fall"):
        swing = math.sin(pose.t * 7.0) * 3
        lift_l, lift_r = 2 + swing, 2 - swing
    if pose.kind == "sit":
        pp.ellipse(36, 114, 16, 9, _c(ch.shoes))
        pp.ellipse(64, 114, 16, 9, _c(ch.shoes))
        return
    pp.ellipse(41, 113 - lift_l, 14, 9, _c(ch.shoes))
    pp.ellipse(59, 113 - lift_r, 14, 9, _c(ch.shoes))


def _body(pp: Painter, ch: Character, pose: Pose) -> None:
    # 치마(A라인)
    top, bottom = 72.0, 112.0
    if pose.kind == "sit":
        top, bottom = 76.0, 114.0
    path = QPainterPath()
    path.moveTo(37, top)
    path.cubicTo(33, 90, 24, 104, 22, bottom - 2)
    path.quadTo(50, bottom + 5, 78, bottom - 2)
    path.cubicTo(76, 104, 67, 90, 63, top)
    path.closeSubpath()
    grad = QRadialGradient(QPointF(42, 84), 40)
    grad.setColorAt(0, _c(ch.dress).lighter(112))
    grad.setColorAt(1, _c(ch.dress_dark))
    pp.shape(path, QBrush(grad))
    # 치마 끝단 장식
    hem = QPainterPath()
    hem.moveTo(23, bottom - 4)
    hem.quadTo(50, bottom + 3, 77, bottom - 4)
    pp.p.setPen(QPen(_c(ch.trim), 3.2, Qt.SolidLine, Qt.RoundCap))
    pp.p.setBrush(Qt.NoBrush)
    pp.p.drawPath(hem)


def _arms(pp: Painter, ch: Character, pose: Pose) -> None:
    sleeve = _c(ch.sleeves or ch.dress)
    if pose.kind == "held":      # 잡혀서 팔을 위로 버둥
        wave = math.sin(pose.t * 10) * 6
        pp.ellipse(24, 70 + wave, 15, 20, sleeve)
        pp.ellipse(76, 70 - wave, 15, 20, sleeve)
        pp.ellipse(22, 61 + wave, 8, 8, SKIN)
        pp.ellipse(78, 61 - wave, 8, 8, SKIN)
        return
    swing = math.sin(pose.t * 9.0) * 4 if pose.kind == "walk" else 0.0
    if pose.kind == "happy":
        swing = math.sin(pose.t * 14) * 3
    pp.ellipse(27, 86 + swing, 15, 21, sleeve)
    pp.ellipse(73, 86 - swing, 15, 21, sleeve)
    pp.ellipse(27, 97 + swing, 8, 8, SKIN)
    pp.ellipse(73, 97 - swing, 8, 8, SKIN)


def _hair_back(pp: Painter, ch: Character, pose: Pose) -> None:
    hair = _c(ch.hair_dark)
    # 머리 윗부분과 옆만 감싸고 턱 아래로는 내려오지 않게 (후드처럼 보이지 않도록)
    cap = QPainterPath()
    cap.addEllipse(QRectF(14, 10, 72, 66))
    clip = QPainterPath()
    clip.addRect(QRectF(0, 0, 100, 58))
    path = cap.intersected(clip)
    if ch.side_locks:
        sway = math.sin(pose.t * 3) * 1.5
        for x in (14, 72):
            lock = QPainterPath()
            lock.addRoundedRect(QRectF(x + sway, 34, 14, 46), 7, 7)
            path = path.united(lock)
    pp.shape(path.simplified(), hair)


def _head(pp: Painter, ch: Character, pose: Pose) -> None:
    grad = QRadialGradient(QPointF(40, 36), 44)
    grad.setColorAt(0, SKIN.lighter(103))
    grad.setColorAt(1, SKIN_SHADE)
    face = QPainterPath()
    face.addEllipse(QRectF(19, 18, 62, 58))
    pp.shape(face, QBrush(grad))


def _bangs(pp: Painter, ch: Character, pose: Pose) -> None:
    hair = _c(ch.hair)
    path = QPainterPath()
    path.moveTo(16, 48)
    path.cubicTo(14, 10, 86, 10, 84, 48)
    # 앞머리 끝: 둥글게 뭉친 머리카락 다발 (끝만 살짝 뾰족)
    tips = [(76, 42), (66, 44), (56, 41), (45, 44), (34, 42), (24, 46)]
    prev_x = 84.0
    for x, y in tips:
        mid = (prev_x + x) / 2
        path.quadTo(mid, 28, x, y)
        prev_x = x
    path.quadTo(18, 34, 16, 48)
    path.closeSubpath()
    grad = QRadialGradient(QPointF(38, 16), 60)
    grad.setColorAt(0, hair.lighter(135))
    grad.setColorAt(1, hair)
    pp.shape(path, QBrush(grad))
    # 머리 윤기
    pp.p.setPen(QPen(QColor(255, 255, 255, 90), 2.2, Qt.SolidLine, Qt.RoundCap))
    pp.p.setBrush(Qt.NoBrush)
    shine = QPainterPath()
    shine.moveTo(30, 22)
    shine.quadTo(38, 16, 48, 17)
    pp.p.drawPath(shine)


def _face(pp: Painter, ch: Character, pose: Pose) -> None:
    p = pp.p
    ex_l, ex_r, ey = 39.0, 61.0, 55.0
    blink = pose.blink if pose.blink is not None else (pose.t % 4.0) > 3.85
    blink = blink and pose.kind not in ("happy", "sleep", "held", "fall")
    if pose.kind in ("happy", "sleep") or blink:
        # ^ ^ (행복) 또는 감은 눈
        p.setPen(QPen(OUTLINE, 2.2, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        for ex in (ex_l, ex_r):
            eye = QPainterPath()
            if pose.kind == "happy":
                eye.moveTo(ex - 5, ey + 2)
                eye.quadTo(ex, ey - 5, ex + 5, ey + 2)
            else:
                eye.moveTo(ex - 5, ey)
                eye.quadTo(ex, ey + 4, ex + 5, ey)
            p.drawPath(eye)
    else:
        big = pose.kind in ("held", "fall")
        w, h = (10, 13) if big else (9, 12)
        for ex in (ex_l, ex_r):
            pp.ellipse(ex, ey, w, h, _c(ch.eyes), outline=True, width=1.2)
            pp.ellipse(ex, ey + 2.5, w * 0.55, h * 0.45, _c(ch.eyes).darker(160), outline=False)
            pp.ellipse(ex - 2, ey - 3, 3.4, 3.4, QColor("#FFFFFF"), outline=False)
    # 볼터치
    pp.ellipse(32, 64, 9, 5, BLUSH, outline=False)
    pp.ellipse(68, 64, 9, 5, BLUSH, outline=False)
    # 입
    p.setPen(QPen(OUTLINE, 1.6, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    mouth = QPainterPath()
    if pose.kind in ("held", "fall"):
        p.setBrush(QColor("#C0485A"))
        mouth.addEllipse(QRectF(47.5, 62, 5, 5.5))
    elif pose.kind == "happy":
        p.setBrush(QColor("#C0485A"))
        mouth.moveTo(45, 62)
        mouth.quadTo(50, 69, 55, 62)
        mouth.closeSubpath()
    else:
        mouth.moveTo(47, 64)
        mouth.quadTo(50, 66.5, 53, 64)
    p.drawPath(mouth)


# ─────────────────────────────── 캐릭터별 장식 ───────────────────────────────
def _bow(pp: Painter, pose: Pose, cx: float, cy: float, span: float, color: QColor,
         frill: QColor | None = None, knot_dx: float = 0.0) -> None:
    """리본: 가운데 매듭에서 양옆으로 퍼지는 두 날개(바깥쪽이 넓고 끝이 살짝 뾰족)."""
    flap = math.sin(pose.t * 4) * 1.5
    for sx in (-1, 1):
        wing = QPainterPath()
        wing.moveTo(cx, cy)
        wing.cubicTo(cx + sx * span * 0.35, cy - span * 0.55 - flap,
                     cx + sx * span * 1.05, cy - span * 0.70 - flap,
                     cx + sx * span, cy - span * 0.10)
        wing.cubicTo(cx + sx * span * 1.05, cy + span * 0.45 + flap,
                     cx + sx * span * 0.40, cy + span * 0.40,
                     cx, cy)
        if frill is not None:  # 흰 레이스 테두리 → 안쪽 색
            pp.shape(wing, frill, width=1.4)
            t = QPainterPath()
            t.moveTo(cx, cy)
            t.cubicTo(cx + sx * span * 0.35, cy - span * 0.42 - flap,
                      cx + sx * span * 0.92, cy - span * 0.55 - flap,
                      cx + sx * span * 0.86, cy - span * 0.08)
            t.cubicTo(cx + sx * span * 0.90, cy + span * 0.32 + flap,
                      cx + sx * span * 0.38, cy + span * 0.28,
                      cx, cy)
            pp.shape(t, color, outline=False)
        else:
            pp.shape(wing, color, width=1.4)
        # 주름
        pp.p.setPen(QPen(color.darker(135), 1.2, Qt.SolidLine, Qt.RoundCap))
        pp.p.drawLine(QPointF(cx + sx * 4, cy), QPointF(cx + sx * span * 0.62, cy - span * 0.18))
    pp.ellipse(cx + knot_dx, cy, span * 0.28, span * 0.26, color)


def _reimu_bow(pp: Painter, ch: Character, pose: Pose) -> None:
    _bow(pp, pose, 50, 14, 34, QColor("#D8263A"), frill=QColor("#FFFFFF"))


def _reimu_tubes(pp: Painter, ch: Character, pose: Pose) -> None:
    for x in (20, 80):
        pp.p.save()
        path = QPainterPath()
        path.addRoundedRect(QRectF(x - 6, 68, 12, 13), 3, 3)
        pp.shape(path, QColor("#FFFFFF"), width=1.2)
        pp.p.setPen(QPen(QColor("#D8263A"), 2))
        pp.p.drawLine(QPointF(x - 5, 72), QPointF(x + 5, 72))
        pp.p.drawLine(QPointF(x - 5, 77), QPointF(x + 5, 77))
        pp.p.restore()


def _reimu_front(pp: Painter, ch: Character, pose: Pose) -> None:
    _reimu_tubes(pp, ch, pose)
    pp.ellipse(50, 76, 12, 7, QColor("#F2C230"), width=1.2)  # 노란 스카프


def _marisa_hat(pp: Painter, ch: Character, pose: Pose) -> None:
    black, band = QColor("#2B2630"), QColor("#FFFFFF")
    brim = QPainterPath()
    brim.addEllipse(QRectF(4, 18, 92, 20))
    pp.shape(brim, black)
    cone = QPainterPath()
    tip = 8 + math.sin(pose.t * 2.5) * 2
    cone.moveTo(26, 28)
    cone.cubicTo(34, 10, 52, -8, 78 + tip, -6)
    cone.cubicTo(64, 4, 70, 14, 74, 28)
    cone.closeSubpath()
    pp.shape(cone, black)
    pp.p.setPen(QPen(band, 4))
    pp.p.drawLine(QPointF(29, 24), QPointF(72, 24))
    pp.ellipse(72, 22, 10, 8, band, width=1.2)  # 리본


def _marisa_front(pp: Painter, ch: Character, pose: Pose) -> None:
    # 한쪽 땋은 머리 + 앞치마
    braid = QPainterPath()
    braid.addRoundedRect(QRectF(14, 58, 10, 26), 5, 5)
    pp.shape(braid, _c(ch.hair))
    pp.ellipse(19, 86, 8, 6, QColor("#FFFFFF"), width=1.1)
    apron = QPainterPath()
    apron.addRoundedRect(QRectF(40, 84, 20, 26), 6, 6)
    pp.shape(apron, QColor("#FFFFFF"), width=1.2)


def _sakuya_front(pp: Painter, ch: Character, pose: Pose) -> None:
    # 메이드 머리띠 + 땋은 머리 두 가닥 + 초록 리본
    band = QPainterPath()
    band.moveTo(24, 22)
    for i, x in enumerate(range(24, 78, 6)):
        band.lineTo(x + 3, 14 if i % 2 == 0 else 19)
    band.lineTo(76, 22)
    band.quadTo(50, 12, 24, 22)
    pp.shape(band, QColor("#FFFFFF"), width=1.2)
    for x in (18, 82):
        pp.ellipse(x, 74, 8, 12, _c(ch.hair), width=1.2)
        pp.ellipse(x, 82, 7, 5, QColor("#3E8E5A"), width=1.0)
    apron = QPainterPath()
    apron.addRoundedRect(QRectF(39, 82, 22, 28), 6, 6)
    pp.shape(apron, QColor("#FFFFFF"), width=1.2)


def _cirno_bow(pp: Painter, ch: Character, pose: Pose) -> None:
    _bow(pp, pose, 50, 12, 26, QColor("#2F6FD6"))


def _cirno_wings(pp: Painter, ch: Character, pose: Pose) -> None:
    ice = QColor(190, 235, 255, 210)
    shimmer = math.sin(pose.t * 3) * 2
    for sx in (-1, 1):
        for dy, ln in ((74, 22), (86, 26), (98, 20)):
            wing = QPainterPath()
            base = 50 + sx * 16
            wing.moveTo(base, dy)
            wing.lineTo(base + sx * ln, dy - 8 + shimmer)
            wing.lineTo(base + sx * (ln - 6), dy + 4)
            wing.closeSubpath()
            pp.shape(wing, ice, width=1.1)


CHARACTERS: dict[str, Character] = {
    "reimu": Character(
        key="reimu", name="하쿠레이 레이무",
        hair="#4A2E2A", hair_dark="#3A2220", eyes="#9C2B2B",
        dress="#D8263A", dress_dark="#A8182B", sleeves="#FFFFFF", shoes="#5A3A30",
        accessory_back=_reimu_bow, accessory_front=_reimu_front),
    "marisa": Character(
        key="marisa", name="키리사메 마리사",
        hair="#F4D35E", hair_dark="#D9B23C", eyes="#C9962B",
        dress="#2B2630", dress_dark="#17141B", sleeves="#FFFFFF", shoes="#3A2E26",
        side_locks=True, accessory_front=_marisa_front, tags={"hat": _marisa_hat}),
    "sakuya": Character(
        key="sakuya", name="이자요이 사쿠야",
        hair="#D9DEE8", hair_dark="#B7BECC", eyes="#4666B8",
        dress="#3E5BA8", dress_dark="#2A407E", sleeves="#3E5BA8", shoes="#2A2A36",
        accessory_front=_sakuya_front),
    "cirno": Character(
        key="cirno", name="치르노",
        hair="#6EC6F2", hair_dark="#4FA8DC", eyes="#2F6FD6",
        dress="#3C7FE0", dress_dark="#2A5DB0", sleeves="#FFFFFF", shoes="#3A4A6A",
        side_locks=False, accessory_back=_cirno_bow, extra_body=_cirno_wings),
}


def draw_character(p: QPainter, ch: Character, pose: Pose, rect: QRectF) -> None:
    """rect 안에(발이 rect 아래 가운데) 캐릭터를 그린다."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    scale = min(rect.width() / DESIGN_W, rect.height() / DESIGN_H)
    # 발 기준으로 좌우 반전·찌그러짐·기울기
    p.translate(rect.center().x(), rect.bottom() - (DESIGN_H - FOOT_Y) * scale)
    bob = 0.0
    if pose.kind == "walk":
        bob = -abs(math.sin(pose.t * 9.0)) * 2.5
    elif pose.kind == "idle":
        bob = math.sin(pose.t * 2.2) * 0.8
    elif pose.kind == "happy":
        bob = -abs(math.sin(pose.t * 12)) * 4
    p.translate(0, bob * scale)
    p.rotate(pose.tilt)
    sq = max(-0.3, min(0.3, pose.squash))
    p.scale(scale * pose.facing * (1 + sq * 0.6), scale * (1 - sq))
    p.translate(-FOOT_X, -FOOT_Y)

    pp = Painter(p)
    if pose.kind not in ("held", "fall"):
        pp.ellipse(50, 118, 52, 7, QColor(0, 0, 0, 45), outline=False)  # 그림자
    if ch.extra_body:
        ch.extra_body(pp, ch, pose)
    _hair_back(pp, ch, pose)
    if ch.accessory_back:  # 뒷머리 위, 얼굴·앞머리 아래 → 머리 뒤에 달린 리본처럼
        ch.accessory_back(pp, ch, pose)
    _feet(pp, ch, pose)
    _body(pp, ch, pose)
    _arms(pp, ch, pose)
    _head(pp, ch, pose)
    _face(pp, ch, pose)
    _bangs(pp, ch, pose)
    if ch.accessory_front:
        ch.accessory_front(pp, ch, pose)
    hat = ch.tags.get("hat")
    if hat:
        hat(pp, ch, pose)
    p.restore()
