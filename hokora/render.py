# -*- coding: utf-8 -*-
"""
작은 봉제인형 스타일 캐릭터를 QPainter 로 그린다.

모든 캐릭터는 같은 몸(아주 큰 찹쌀떡 머리 + 콩 모양 몸통)을 쓰고, 색과 장식만 다르다.
딱딱해 보이지 않게: 완전한 원 대신 볼이 살짝 부푼 곡선, 바깥 윤곽선은 굵게·안쪽 선은 가늘게,
큰 눈(윗눈꺼풀 선 + 홍채 그라데이션 + 반짝임 두 개), 볼 빗금, 레이스 치마 끝단.
설계 좌표계는 폭 100 × 높이 120, 발바닥 가운데가 (50, 118).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen,
                           QRadialGradient)

DESIGN_W, DESIGN_H = 100.0, 120.0
FOOT_X, FOOT_Y = 50.0, 118.0

SKIN = QColor("#FFEBDF")
SKIN_SHADE = QColor("#F8CDBE")
OUTLINE = QColor(84, 48, 52, 225)     # 따뜻한 갈색 윤곽선
LINE_OUTER = 2.2                       # 바깥 윤곽선
LINE_INNER = 1.3                       # 안쪽 선


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
    trim: str = "#FFFFFF"     # 옷 가장자리 레이스
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

    def shape(self, path: QPainterPath, fill: QColor | QBrush, outline: bool = True,
              width: float = LINE_OUTER) -> None:
        self.p.setPen(QPen(OUTLINE, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin) if outline else Qt.NoPen)
        self.p.setBrush(fill)
        self.p.drawPath(path)

    def ellipse(self, cx, cy, w, h, fill, outline=True, width=LINE_OUTER) -> None:
        path = QPainterPath()
        path.addEllipse(QRectF(cx - w / 2, cy - h / 2, w, h))
        self.shape(path, fill, outline, width)

    def stroke(self, path: QPainterPath, color: QColor, width: float) -> None:
        self.p.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        self.p.setBrush(Qt.NoBrush)
        self.p.drawPath(path)


def _c(x) -> QColor:
    return x if isinstance(x, QColor) else QColor(x)


def _soft(color: QColor, center: QPointF, radius: float, light: int = 115, dark: int = 108) -> QRadialGradient:
    """왼쪽 위에서 빛이 드는 부드러운 음영."""
    g = QRadialGradient(center, radius)
    g.setColorAt(0, color.lighter(light))
    g.setColorAt(1, color.darker(dark))
    return g


def _mochi(cx: float, top: float, w: float, h: float) -> QPainterPath:
    """찹쌀떡 머리: 위는 둥글고, 볼 쪽이 살짝 부풀고, 턱은 넓고 부드럽게."""
    l, r, b = cx - w / 2, cx + w / 2, top + h
    path = QPainterPath()
    path.moveTo(cx, top)
    path.cubicTo(cx + w * 0.34, top, r, top + h * 0.22, r, top + h * 0.54)
    path.cubicTo(r, top + h * 0.84, cx + w * 0.30, b, cx, b)
    path.cubicTo(cx - w * 0.30, b, l, top + h * 0.84, l, top + h * 0.54)
    path.cubicTo(l, top + h * 0.22, cx - w * 0.34, top, cx, top)
    path.closeSubpath()
    return path


# ─────────────────────────────── 몸 ───────────────────────────────
def _feet(pp: Painter, ch: Character, pose: Pose) -> None:
    shoe = _c(ch.shoes)
    if pose.kind == "sit":  # 다리를 앞으로 쭉
        pp.ellipse(33, 114, 18, 11, _soft(shoe, QPointF(30, 111), 12))
        pp.ellipse(67, 114, 18, 11, _soft(shoe, QPointF(64, 111), 12))
        return
    lift_l = lift_r = 0.0
    if pose.kind == "walk":
        phase = pose.t * 9.0
        lift_l = max(0.0, math.sin(phase)) * 5
        lift_r = max(0.0, -math.sin(phase)) * 5
    elif pose.kind in ("held", "fall"):
        swing = math.sin(pose.t * 10.0) * 3
        lift_l, lift_r = 2 + swing, 2 - swing
    pp.ellipse(40, 113.5 - lift_l, 16, 10, _soft(shoe, QPointF(37, 110 - lift_l), 11))
    pp.ellipse(60, 113.5 - lift_r, 16, 10, _soft(shoe, QPointF(57, 110 - lift_r), 11))


def _body(pp: Painter, ch: Character, pose: Pose) -> None:
    """콩 모양 몸통 + 레이스 끝단."""
    bottom = 111.0 if pose.kind != "sit" else 112.0
    path = QPainterPath()
    path.moveTo(32, 76)
    path.cubicTo(27, 88, 21, 101, 24, bottom - 1)
    path.cubicTo(34, bottom + 5, 66, bottom + 5, 76, bottom - 1)
    path.cubicTo(79, 101, 73, 88, 68, 76)
    path.closeSubpath()
    dress = _c(ch.dress)
    pp.shape(path, _soft(dress, QPointF(40, 84), 42, 118, 112))
    # 레이스 끝단: 작은 반원들
    trim = _c(ch.trim)
    for i in range(6):
        x = 27.5 + i * 9.0
        y = bottom + 1.2 - abs(i - 2.5) * 0.9
        pp.ellipse(x, y, 10.5, 7.0, trim, width=LINE_INNER)
    # 옷 주름 한 줄 (딱딱함 덜기)
    fold = QPainterPath()
    fold.moveTo(50, 86)
    fold.quadTo(48, 96, 51, 104)
    pp.stroke(fold, QColor(0, 0, 0, 40), 1.2)


def _limb(pp: Painter, cx: float, cy: float, angle: float, sleeve: QColor) -> None:
    """어깨(cx, cy)에 달린 짧고 통통한 팔 + 동그란 손."""
    p = pp.p
    p.save()
    p.translate(cx, cy)
    p.rotate(angle)
    arm = QPainterPath()
    arm.addRoundedRect(QRectF(-7, -2, 14, 19), 7, 7)
    pp.shape(arm, _soft(sleeve, QPointF(-3, 2), 16))
    pp.ellipse(0, 17.5, 9, 8, SKIN)
    p.restore()


def _arms(pp: Painter, ch: Character, pose: Pose) -> None:
    sleeve = _c(ch.sleeves or ch.dress)
    if pose.kind == "held":        # 잡혀서 팔을 위로 버둥버둥
        wave = math.sin(pose.t * 10) * 14
        _limb(pp, 30, 80, 150 + wave, sleeve)
        _limb(pp, 70, 80, -150 + wave, sleeve)
    elif pose.kind == "fall":
        _limb(pp, 30, 80, 120, sleeve)
        _limb(pp, 70, 80, -120, sleeve)
    elif pose.kind == "happy":     # 만세
        wave = math.sin(pose.t * 14) * 10
        _limb(pp, 30, 80, 135 + wave, sleeve)
        _limb(pp, 70, 80, -135 - wave, sleeve)
    else:
        swing = math.sin(pose.t * 9.0) * 16 if pose.kind == "walk" else 0.0
        rest = 22 if pose.kind != "sit" else 30
        _limb(pp, 31, 80, rest + swing, sleeve)
        _limb(pp, 69, 80, -rest + swing, sleeve)


# ─────────────────────────────── 머리 ───────────────────────────────
def _hair_back(pp: Painter, ch: Character, pose: Pose) -> None:
    hair = _c(ch.hair_dark)
    # 머리 윗부분과 옆만 감싸고 턱 아래로는 내려오지 않게 (후드처럼 보이지 않도록)
    cap = _mochi(50, 7, 88, 74)
    clip = QPainterPath()
    clip.addRect(QRectF(0, -10, 100, 72))
    path = cap.intersected(clip)
    if ch.side_locks:  # 끝이 가늘어지며 바깥으로 살짝 휘는 옆머리
        sway = math.sin(pose.t * 3) * 1.5
        for sx in (-1, 1):
            base = 50 + sx * 36
            lock = QPainterPath()
            lock.moveTo(base, 40)
            lock.cubicTo(base + sx * 6, 60, base + sx * 5 + sway, 78, base + sx * 1 + sway, 90)
            lock.cubicTo(base - sx * 6 + sway, 82, base - sx * 12, 66, base - sx * 12, 48)
            lock.closeSubpath()
            path = path.united(lock)
    pp.shape(path.simplified(), _soft(hair, QPointF(40, 20), 70, 108, 104))


def _head(pp: Painter, ch: Character, pose: Pose) -> None:
    face = _mochi(50, 14, 78, 68)
    pp.shape(face, _soft(SKIN, QPointF(40, 40), 50, 102, 104))


def _bangs(pp: Painter, ch: Character, pose: Pose) -> None:
    """큼직하고 부드러운 앞머리 다발 몇 개 + 바보털."""
    hair = _c(ch.hair)
    path = QPainterPath()
    path.moveTo(10, 56)
    path.cubicTo(8, 24, 28, 7, 50, 7)
    path.cubicTo(72, 7, 92, 24, 90, 56)
    # 오른쪽 옆 → 왼쪽 옆으로 다발 끝 (x, 끝 y, 사이 골 y)
    clumps = [(80, 47, 34), (65, 45, 30), (50, 49, 31), (35, 45, 30), (20, 47, 34)]
    prev = (90.0, 56.0)
    for x, tip_y, valley in clumps:
        px, py = prev
        path.cubicTo(px - 3, valley + 4, x + 5, valley, x, tip_y)
        prev = (x, tip_y)
    path.cubicTo(prev[0] - 4, 40, 12, 44, 10, 56)
    path.closeSubpath()
    pp.shape(path, _soft(hair, QPointF(36, 14), 64, 130, 100))
    # 윤기 (반달 하이라이트)
    shine = QPainterPath()
    shine.moveTo(27, 22)
    shine.cubicTo(33, 15, 44, 13, 52, 14)
    pp.stroke(shine, QColor(255, 255, 255, 110), 2.4)
    # 바보털
    sway = math.sin(pose.t * 3.2) * 2
    ahoge = QPainterPath()
    ahoge.moveTo(50, 9)
    ahoge.cubicTo(49, 0, 58 + sway, -6, 62 + sway, -1)
    pp.stroke(ahoge, OUTLINE, 3.6)
    pp.stroke(ahoge, hair, 2.0)


def _eye(pp: Painter, ch: Character, cx: float, cy: float, surprised: bool) -> None:
    iris = _c(ch.eyes)
    w, h = 14.0, 17.5
    # 흰자 없이 홍채 그라데이션 (위는 진하게, 아래는 밝게)
    g = QLinearGradient(0, cy - h / 2, 0, cy + h / 2)
    g.setColorAt(0, iris.darker(170))
    g.setColorAt(0.55, iris)
    g.setColorAt(1, iris.lighter(150))
    pp.ellipse(cx, cy, w, h, g, width=LINE_INNER)
    pupil = 4.5 if surprised else 6.5
    pp.ellipse(cx, cy + 1.5, pupil, pupil * 1.2, iris.darker(220), outline=False)
    # 반짝임 두 개
    pp.ellipse(cx - 2.6, cy - 3.4, 5.0, 5.0, QColor("#FFFFFF"), outline=False)
    pp.ellipse(cx + 3.0, cy + 3.8, 2.3, 2.3, QColor(255, 255, 255, 220), outline=False)
    # 굵은 윗눈꺼풀: 눈 윗가장자리를 따라감 (눈 안쪽으로 파고들면 졸려 보임)
    lid = QPainterPath()
    lid.moveTo(cx - 7.6, cy - 1.0)
    lid.cubicTo(cx - 7.2, cy - 10.6, cx + 7.2, cy - 10.6, cx + 7.6, cy - 1.0)
    pp.stroke(lid, OUTLINE, 2.6)
    # 바깥쪽 속눈썹 하나 (얼굴 바깥 방향으로 살짝 올라감)
    out = -1 if cx < 50 else 1
    lash = QPainterPath()
    lash.moveTo(cx + out * 6.4, cy - 4.5)
    lash.quadTo(cx + out * 9.0, cy - 6.0, cx + out * 10.2, cy - 8.4)
    pp.stroke(lash, OUTLINE, 1.8)


def _face(pp: Painter, ch: Character, pose: Pose) -> None:
    ex_l, ex_r, ey = 35.0, 65.0, 58.0
    blink = pose.blink if pose.blink is not None else (pose.t % 4.0) > 3.85
    blink = blink and pose.kind not in ("happy", "sleep", "held", "fall")
    if pose.kind in ("happy", "sleep") or blink:
        for ex in (ex_l, ex_r):
            eye = QPainterPath()
            if pose.kind == "happy":          # ^ ^
                eye.moveTo(ex - 6, ey + 3)
                eye.quadTo(ex, ey - 6, ex + 6, ey + 3)
            else:                             # 감은 눈 ‿
                eye.moveTo(ex - 6, ey)
                eye.quadTo(ex, ey + 5, ex + 6, ey)
            pp.stroke(eye, OUTLINE, 2.6)
    else:
        surprised = pose.kind in ("held", "fall")
        for ex in (ex_l, ex_r):
            _eye(pp, ch, ex, ey, surprised)
    # 볼터치: 부드러운 분홍 + 작은 빗금
    for bx in (23.5, 76.5):
        g = QRadialGradient(QPointF(bx, 69), 9)
        g.setColorAt(0, QColor(255, 125, 150, 150))
        g.setColorAt(1, QColor(255, 125, 150, 0))
        pp.ellipse(bx, 69, 18, 10, g, outline=False)
        for i in range(3):
            x = bx - 3.5 + i * 3.5
            line = QPainterPath()
            line.moveTo(x + 1.2, 67)
            line.lineTo(x - 1.2, 71)
            pp.stroke(line, QColor(230, 95, 120, 150), 1.0)
    # 입
    mouth = QPainterPath()
    if pose.kind in ("held", "fall"):         # 놀란 o
        pp.ellipse(50, 73, 5, 5.5, QColor("#B8404F"), width=LINE_INNER)
        return
    if pose.kind == "happy":                  # 활짝
        mouth.moveTo(45, 70.5)
        mouth.cubicTo(46, 78, 54, 78, 55, 70.5)
        mouth.quadTo(50, 72, 45, 70.5)
        mouth.closeSubpath()
        pp.shape(mouth, QColor("#B8404F"), width=LINE_INNER)
        tongue = QPainterPath()
        tongue.addEllipse(QRectF(47.5, 73.6, 5, 2.8))
        pp.shape(tongue, QColor("#FF8FA0"), outline=False)
        return
    # 평소: 고양이 입 ω
    mouth.moveTo(45.5, 71)
    mouth.quadTo(47.8, 73.8, 50, 71.2)
    mouth.quadTo(52.2, 73.8, 54.5, 71)
    pp.stroke(mouth, OUTLINE, 1.5)


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
            pp.shape(wing, frill)
            t = QPainterPath()
            t.moveTo(cx, cy)
            t.cubicTo(cx + sx * span * 0.35, cy - span * 0.42 - flap,
                      cx + sx * span * 0.92, cy - span * 0.55 - flap,
                      cx + sx * span * 0.86, cy - span * 0.08)
            t.cubicTo(cx + sx * span * 0.90, cy + span * 0.32 + flap,
                      cx + sx * span * 0.38, cy + span * 0.28,
                      cx, cy)
            pp.shape(t, _soft(color, QPointF(cx + sx * span * 0.4, cy - span * 0.3), span, 118, 106),
                     outline=False)
        else:
            pp.shape(wing, _soft(color, QPointF(cx + sx * span * 0.4, cy - span * 0.3), span, 118, 106))
        # 주름
        fold = QPainterPath()
        fold.moveTo(cx + sx * 4, cy)
        fold.quadTo(cx + sx * span * 0.4, cy - span * 0.05, cx + sx * span * 0.62, cy - span * 0.22)
        pp.stroke(fold, color.darker(140), 1.2)
    pp.ellipse(cx + knot_dx, cy, span * 0.30, span * 0.28, _soft(color, QPointF(cx - 2, cy - 2), 6))


def _reimu_bow(pp: Painter, ch: Character, pose: Pose) -> None:
    _bow(pp, pose, 50, 9, 38, QColor("#E0314B"), frill=QColor("#FFFFFF"))


def _reimu_front(pp: Painter, ch: Character, pose: Pose) -> None:
    # 옆머리 장식 (빨간 줄무늬 흰 통)
    for x in (16.5, 83.5):
        tube = QPainterPath()
        tube.addRoundedRect(QRectF(x - 6, 68, 12, 13), 4, 4)
        pp.shape(tube, QColor("#FFFFFF"), width=LINE_INNER)
        for y in (72, 77):
            stripe = QPainterPath()
            stripe.moveTo(x - 5, y)
            stripe.lineTo(x + 5, y)
            pp.stroke(stripe, QColor("#E0314B"), 2.0)
    # 노란 스카프
    pp.ellipse(50, 83, 13, 7.5, _soft(QColor("#F7C933"), QPointF(47, 81), 8), width=LINE_INNER)


def _marisa_hat(pp: Painter, ch: Character, pose: Pose) -> None:
    black, band = QColor("#2E2934"), QColor("#FFFFFF")
    brim = QPainterPath()
    brim.addEllipse(QRectF(0, 14, 100, 22))
    pp.shape(brim, _soft(black, QPointF(35, 18), 50, 150, 100))
    cone = QPainterPath()
    tip = 8 + math.sin(pose.t * 2.5) * 2
    cone.moveTo(24, 26)
    cone.cubicTo(32, 6, 52, -12, 80 + tip, -9)
    cone.cubicTo(66, 1, 72, 12, 76, 26)
    cone.quadTo(50, 30, 24, 26)
    cone.closeSubpath()
    pp.shape(cone, _soft(black, QPointF(40, 8), 40, 160, 100))
    band_path = QPainterPath()
    band_path.moveTo(27, 22)
    band_path.quadTo(50, 26, 74, 22)
    pp.stroke(band_path, band, 4.2)
    _bow(pp, pose, 70, 21, 8, band)


def _marisa_front(pp: Painter, ch: Character, pose: Pose) -> None:
    # 한쪽 땋은 머리 + 앞치마
    braid = QPainterPath()
    braid.addRoundedRect(QRectF(9, 58, 11, 28), 5.5, 5.5)
    pp.shape(braid, _soft(_c(ch.hair), QPointF(12, 62), 16), width=LINE_INNER)
    _bow(pp, pose, 14.5, 88, 6, QColor("#FFFFFF"))
    apron = QPainterPath()
    apron.addRoundedRect(QRectF(40, 86, 20, 22), 7, 7)
    pp.shape(apron, QColor("#FFFFFF"), width=LINE_INNER)


def _sakuya_front(pp: Painter, ch: Character, pose: Pose) -> None:
    # 메이드 머리띠 (프릴) + 땋은 머리 두 가닥 + 초록 리본 + 앞치마
    band = QPainterPath()
    band.moveTo(24, 20)
    for i, x in enumerate(range(24, 78, 6)):
        band.quadTo(x + 1.5, 10 if i % 2 == 0 else 14, x + 3, 12 if i % 2 == 0 else 16)
    band.lineTo(76, 20)
    band.quadTo(50, 10, 24, 20)
    pp.shape(band, QColor("#FFFFFF"), width=LINE_INNER)
    for x in (15, 85):
        pp.ellipse(x, 76, 9, 13, _soft(_c(ch.hair), QPointF(x - 2, 72), 8), width=LINE_INNER)
        _bow(pp, pose, x, 84, 6, QColor("#3E9A5E"))
    apron = QPainterPath()
    apron.addRoundedRect(QRectF(39, 85, 22, 23), 7, 7)
    pp.shape(apron, QColor("#FFFFFF"), width=LINE_INNER)


def _cirno_bow(pp: Painter, ch: Character, pose: Pose) -> None:
    _bow(pp, pose, 50, 7, 28, QColor("#3478E0"))


def _cirno_wings(pp: Painter, ch: Character, pose: Pose) -> None:
    ice = QColor(200, 240, 255, 215)
    shimmer = math.sin(pose.t * 3) * 2
    for sx in (-1, 1):
        for dy, ln in ((78, 22), (90, 26), (102, 20)):
            wing = QPainterPath()
            base = 50 + sx * 16
            wing.moveTo(base, dy)
            wing.lineTo(base + sx * ln, dy - 8 + shimmer)
            wing.lineTo(base + sx * (ln - 6), dy + 4)
            wing.closeSubpath()
            pp.shape(wing, ice, width=LINE_INNER)


CHARACTERS: dict[str, Character] = {
    "reimu": Character(
        key="reimu", name="하쿠레이 레이무",
        hair="#553430", hair_dark="#3E2522", eyes="#B0343A",
        dress="#E0314B", dress_dark="#B21E36", sleeves="#FFFFFF", shoes="#6A4436",
        accessory_back=_reimu_bow, accessory_front=_reimu_front),
    "marisa": Character(
        key="marisa", name="키리사메 마리사",
        hair="#F7D862", hair_dark="#DDB73F", eyes="#D39A2A",
        dress="#35303C", dress_dark="#1F1B24", sleeves="#FFFFFF", shoes="#46382E",
        accessory_front=_marisa_front, tags={"hat": _marisa_hat}),
    "sakuya": Character(
        key="sakuya", name="이자요이 사쿠야",
        hair="#E3E7F0", hair_dark="#BCC3D2", eyes="#4F70C8",
        dress="#4764B4", dress_dark="#2F4788", sleeves="#4764B4", shoes="#2E2E3C",
        accessory_front=_sakuya_front),
    "sanae": Character(
        key="sanae", name="코치야 사나에",
        hair="#5FB84E", hair_dark="#469A3A", eyes="#4E9A48",
        dress="#4A5FB0", dress_dark="#34468A", sleeves="#FFFFFF", shoes="#3C4C8A"),
    "remilia": Character(
        key="remilia", name="레밀리아 스칼렛",
        hair="#9AA4DC", hair_dark="#7A84C0", eyes="#C0303A",
        dress="#F4C8D0", dress_dark="#E0A4B0", sleeves="#F4C8D0", shoes="#E8A0AC"),
    "flandre": Character(
        key="flandre", name="플랑드르 스칼렛",
        hair="#F4D35E", hair_dark="#D9B23C", eyes="#C0303A",
        dress="#D8263A", dress_dark="#A8182B", sleeves="#FFFFFF", shoes="#B01E30"),
    "cirno": Character(
        key="cirno", name="치르노",
        hair="#78CCF4", hair_dark="#56AEE0", eyes="#3478E0",
        dress="#4188EA", dress_dark="#2C63B8", sleeves="#FFFFFF", shoes="#3C4C70",
        side_locks=False, accessory_back=_cirno_bow, extra_body=_cirno_wings),
}


# 손님 (guests.py). 그림 파일로 그리므로 코드 그림용 색은 만일을 위한 대강
GUESTS: dict[str, Character] = {
    "sunny": Character(key="sunny", name="서니 밀크", hair="#F29A3A", hair_dark="#D97A22", eyes="#C0503A",
                       dress="#D8263A", dress_dark="#A8182B", sleeves="#FFFFFF"),
    "luna": Character(key="luna", name="루나 차일드", hair="#F4D86A", hair_dark="#D9B84A", eyes="#6E5A4A",
                      dress="#FFFFFF", dress_dark="#DDDDDD", sleeves="#FFFFFF", shoes="#2E2626"),
    "star": Character(key="star", name="스타 사파이어", hair="#2E2630", hair_dark="#1C161E", eyes="#5A4A5A",
                      dress="#3A5CC0", dress_dark="#2A4494", sleeves="#FFFFFF"),
    "aya": Character(key="aya", name="샤메이마루 아야", hair="#2A2226", hair_dark="#161014", eyes="#B0343A",
                     dress="#2E2A30", dress_dark="#1A171C", sleeves="#FFFFFF", shoes="#B0343A"),
    "suika": Character(key="suika", name="이부키 스이카", hair="#E08A3C", hair_dark="#C06E26", eyes="#8A5A2A",
                       dress="#7A4EB0", dress_dark="#5A368A", sleeves="#FFFFFF", shoes="#6A4436"),
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
        pp.ellipse(50, 118, 56, 8, QColor(0, 0, 0, 40), outline=False)  # 그림자
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
