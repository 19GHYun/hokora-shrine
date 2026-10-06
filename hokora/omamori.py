# -*- coding: utf-8 -*-
"""부적 뽑기 (수여소).

새전을 내고 부적을 뽑는다. 부적은 일반·희귀·귀함·전설 네 등급이고, 3개까지 지니면(장착) 효과가 난다.
같은 부적이 또 나오면 레벨이 오르고(최대 Lv.5), 그 뒤로는 새전을 조금 돌려준다.
천장: 전설 없이 60번 뽑으면 다음은 꼭 전설. 10번 뽑기는 귀함 이상 하나 보장.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen

from .state import GameState

# 등급 → (이름, 테두리 색, 뽑힐 확률 %)
RARITY = {
    "N": ("일반", "#9AA0A6", 60.0),
    "R": ("희귀", "#3D7DD8", 30.0),
    "SR": ("귀함", "#9B4DCA", 8.5),
    "SSR": ("전설", "#E0A100", 1.5),
}
EFFECTS = {  # 효과 → 설명 (v 는 레벨을 반영한 값)
    "income": "새전 수입 +{v:.0%}",
    "pat": "쓰다듬기 새전 +{v:.0f}",
    "offline": "꺼진 동안 새전함 +{v:.0%}",
    "omikuji": "오미쿠지 새전 +{v:.0%}",
    "thief": "새전 도둑 -{v:.0%}",
    "daily": "부탁 보상 +{v:.0%}",
    "guest": "손님 방문 +{v:.0%}",
    "affection": "말 걸기·선물 호감도 +{v:.0f}",
    "torii": "도리이 봉납값 -{v:.0%}",
    "suika": "스이카의 새전 +{v:.0%}",
}
MAX_LV = 5
SLOTS = 3
PITY = 60
PRICE_BY_STAGE = {1: 50, 2: 100, 3: 200, 4: 350, 5: 500}   # 한 번 뽑는 값 (신사 단계별)
CAPS = {"thief": 0.9, "torii": 0.5}                          # 효과 상한


@dataclass(frozen=True)
class Charm:
    key: str
    name: str
    kanji: str
    rarity: str
    effect: str
    base: float
    color: str


CHARMS = {c.key: c for c in [
    Charm("kinun", "금운 부적", "金運", "N", "income", 0.03, "#E8B923"),
    Charm("fuku", "복 부적", "福", "N", "pat", 1, "#D9412E"),
    Charm("gakugyo", "학업 부적", "學業", "N", "omikuji", 0.10, "#3D7DD8"),
    Charm("kenko", "건강 부적", "健康", "N", "offline", 0.08, "#4FA36B"),
    Charm("yakuyoke", "액막이 부적", "厄除", "N", "thief", 0.25, "#7A5BB5"),
    Charm("shobai", "상업번성 부적", "商賣", "R", "income", 0.06, "#C8102E"),
    Charm("enmusubi", "인연 부적", "良緣", "R", "affection", 1, "#F07AA0"),
    Charm("ryoko", "여행 부적", "旅行", "R", "guest", 0.25, "#2FA7B5"),
    Charm("kaiun", "개운 부적", "開運", "R", "daily", 0.25, "#F29A3A"),
    Charm("ryujin", "용신 부적", "龍神", "SR", "income", 0.10, "#2C6E9E"),
    Charm("hono", "봉납 부적", "奉納", "SR", "torii", 0.10, "#B5462E"),
    Charm("oni", "오니 부적", "鬼", "SR", "suika", 0.5, "#7A4EB0"),
    Charm("hakurei", "하쿠레이 부적", "博麗", "SSR", "income", 0.15, "#C8102E"),
    Charm("moriya", "모리야 부적", "守矢", "SSR", "offline", 0.40, "#3E8E5A"),
    Charm("yakumo", "야쿠모 부적", "八雲", "SSR", "guest", 0.80, "#6B4FA0"),
]}


def price(s: GameState) -> int:
    return PRICE_BY_STAGE.get(s.shrine_level, 500)


def value(charm: Charm, lv: int) -> float:
    """레벨 1 = 기본값, 레벨마다 +50% (Lv.5 면 3배)."""
    v = charm.base * (1 + 0.5 * (max(1, lv) - 1))
    return round(v) if charm.effect in ("pat", "affection") else v


def effect_text(charm: Charm, lv: int) -> str:
    return EFFECTS[charm.effect].format(v=value(charm, lv))


def bonus(s: GameState, effect: str) -> float:
    """지닌 부적들의 효과 합."""
    total = sum(value(CHARMS[k], s.omamori.get(k, 1)) for k in s.equipped
                if k in CHARMS and CHARMS[k].effect == effect)
    return min(total, CAPS.get(effect, total))


def _roll(rng: random.Random, pool: list[str]) -> str:
    return rng.choices(pool, weights=[RARITY[r][2] for r in pool])[0]


def pull(s: GameState, n: int, rng: random.Random | None = None) -> list[tuple[str, str]] | None:
    """n번(1 또는 10) 뽑기. 새전이 모자라면 None. 결과: [(부적 키, "new" | "up" | "max")]"""
    rng = rng or random.Random()
    cost = price(s) * (9 if n == 10 else n)                 # 10번은 한 번 값 덜 받음
    if s.saisen < cost:
        return None
    s.saisen -= cost
    results: list[tuple[str, str]] = []
    for i in range(n):
        s.gacha_pity += 1
        if s.gacha_pity >= PITY:
            rank = "SSR"
        elif n == 10 and i == n - 1 and all(CHARMS[k].rarity in ("N", "R") for k, _ in results):
            rank = _roll(rng, ["SR", "SSR"])                # 10번 뽑기: 귀함 이상 하나 보장
        else:
            rank = _roll(rng, list(RARITY))
        if rank == "SSR":
            s.gacha_pity = 0
        key = rng.choice([k for k, c in CHARMS.items() if c.rarity == rank])
        lv = s.omamori.get(key, 0)
        if lv == 0:
            s.omamori[key] = 1
            tag = "new"
        elif lv < MAX_LV:
            s.omamori[key] = lv + 1
            tag = "up"
        else:
            s.saisen += price(s) // 5                          # 다 키운 부적은 새전을 조금 돌려줌
            tag = "max"
        results.append((key, tag))
        if len(s.equipped) < SLOTS and key not in s.equipped and tag == "new":
            s.equipped.append(key)                             # 빈 칸이 있으면 바로 지님
    s.gacha_pulls += n
    return results


def toggle_equip(s: GameState, key: str) -> bool:
    """지니기 / 내려놓기. 칸이 꽉 차서 못 지니면 False."""
    if key in s.equipped:
        s.equipped.remove(key)
        return True
    if key not in s.omamori or len(s.equipped) >= SLOTS:
        return False
    s.equipped.append(key)
    return True


# ── 그리기 ──
def draw_omamori(p: QPainter, rect: QRectF, charm: Charm | None, locked: bool = False) -> None:
    """부적 주머니 하나 (rect 안에 맞춰서). charm 이 None 이거나 locked 면 회색 실루엣."""
    w = min(rect.width(), rect.height() * 0.68)
    h = w / 0.68
    x, y = rect.center().x() - w / 2, rect.center().y() - h / 2 + h * 0.06
    body = QPainterPath()                                       # 위가 비스듬히 접힌 주머니
    body.moveTo(x + w * 0.18, y + h * 0.12)
    body.lineTo(x + w * 0.82, y + h * 0.12)
    body.lineTo(x + w, y + h * 0.3)
    body.lineTo(x + w, y + h - 4)
    body.quadTo(x + w, y + h, x + w - 4, y + h)
    body.lineTo(x + 4, y + h)
    body.quadTo(x, y + h, x, y + h - 4)
    body.lineTo(x, y + h * 0.3)
    body.closeSubpath()
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    if locked or charm is None:
        p.setPen(QPen(QColor(150, 130, 136), 1.2, Qt.DashLine))
        p.setBrush(QColor(220, 210, 214))
        p.drawPath(body)
        f = QFont("Malgun Gothic", max(7, int(w * 0.3)))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(150, 130, 136))
        p.drawText(QRectF(x, y + h * 0.2, w, h * 0.8), Qt.AlignCenter, "?")
        p.restore()
        return
    rim = QColor(RARITY[charm.rarity][1])
    g = QLinearGradient(x, y, x + w, y + h)
    base = QColor(charm.color)
    g.setColorAt(0, base.lighter(125))
    g.setColorAt(1, base.darker(110))
    p.setPen(QPen(rim, 2.2 if charm.rarity in ("SR", "SSR") else 1.6))
    p.setBrush(g)
    p.drawPath(body)
    p.setPen(QPen(QColor(255, 225, 140, 200), 1))              # 안쪽 금실 테두리
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(x + w * 0.16, y + h * 0.3, w * 0.68, h * 0.62), 2, 2)
    # 매듭 끈
    p.setPen(QPen(rim.darker(110), 1.6))
    cx = x + w / 2
    p.drawLine(QPointF(cx, y + h * 0.12), QPointF(cx, y - h * 0.02))
    p.setBrush(rim)
    p.drawEllipse(QPointF(cx, y + h * 0.03), w * 0.09, w * 0.07)
    # 한자 (세로)
    f = QFont("Malgun Gothic", max(6, int(w * (0.22 if len(charm.kanji) > 1 else 0.34))))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(255, 236, 170))
    chars = list(charm.kanji)
    box = QRectF(x + w * 0.16, y + h * 0.32, w * 0.68, h * 0.58)
    step = box.height() / len(chars)
    for i, ch in enumerate(chars):
        p.drawText(QRectF(box.left(), box.top() + i * step, box.width(), step), Qt.AlignCenter, ch)
    if charm.rarity == "SSR":                                   # 전설은 반짝반짝
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 230, 120, 230))
        for sx, sy, r in ((x + w * 1.02, y + h * 0.18, w * 0.12), (x - w * 0.06, y + h * 0.7, w * 0.08)):
            star = QPainterPath()
            for k in range(8):
                a = k * math.pi / 4
                rr = r if k % 2 == 0 else r * 0.35
                pt = QPointF(sx + math.cos(a) * rr, sy + math.sin(a) * rr)
                if k == 0:
                    star.moveTo(pt)
                else:
                    star.lineTo(pt)
            star.closeSubpath()
            p.drawPath(star)
    p.restore()

