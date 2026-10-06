# -*- coding: utf-8 -*-
"""의상실 뽑기: 캐릭터 옷 색·재질 스킨과 발자국 이펙트.

부적과 달리 효과는 없고 보기만 바뀐다 (그래서 비싸다: 한 번 1,000 × 신사 단계).
- 색 스킨: 캐릭터마다 옷 색 범위를 정해 두고, 그 범위의 픽셀만 다른 색으로 돌린다 (그림을 새로 그리지 않음).
  옷 색 범위에 든 눈·리본도 같이 바뀐다.
- 재질 스킨: 흑백·유령·은빛·금빛 — 캐릭터 전체를 다른 재질처럼.
- 이펙트: 걸을 때 남는 발자국(하트·벚꽃·별·무지개), 음표, 반짝이 오라. 누구에게나 씌울 수 있다.
- 중복은 '옷감'이 되고, 옷감으로 원하는 것을 교환할 수 있다. 주마다 한 캐릭터가 픽업(확률 3배).
- 그림이 필요한 전용 의상은 hokora/sprites/<캐릭터>@<스킨>/ 폴더를 넣으면 그 그림을 쓴다 (없는 동작은 기본 옷).
"""
from __future__ import annotations

import colorsys
import math
import random
from dataclasses import dataclass
from datetime import date
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen

from .season import draw_petal
from .sprites import SPRITE_DIR, ImageSprites, image_sprites
from .state import GameState

RARITY = {
    "N": ("일반", "#9AA0A6", 55.0),
    "R": ("희귀", "#3D7DD8", 30.0),
    "SR": ("귀함", "#9B4DCA", 12.0),
    "SSR": ("전설", "#E0A100", 3.0),
}
PRICE_PER_STAGE = 1000
PITY = 80
PICKUP_WEIGHT = 3
CLOTH_GAIN = {"N": 1, "R": 3, "SR": 10, "SSR": 40}       # 중복 → 옷감
CLOTH_COST = {"N": 10, "R": 30, "SR": 100, "SSR": 300}   # 옷감 → 원하는 것 교환
SHORT = {"reimu": "레이무", "marisa": "마리사", "sakuya": "사쿠야", "cirno": "치르노", "sanae": "사나에",
         "remilia": "레밀리아", "flandre": "플랑드르"}

# 캐릭터 → 옷 색 범위: (색상 범위(도) 또는 "dark", 최소 채도, 최소 밝기, 최대 채도, 최대 밝기)
OUTFIT = {
    "reimu": ((335, 20), 0.40, 0.30, 1.0, 1.0),       # 빨간 무녀복·리본 (눈도)
    "marisa": ("dark", 0.0, 0.05, 0.35, 0.42),        # 검은 모자·옷
    "sakuya": ((200, 250), 0.25, 0.20, 1.0, 1.0),     # 파란 메이드복
    "cirno": ((195, 235), 0.55, 0.20, 1.0, 0.93),     # 파란 원피스 (밝은 하늘색 머리는 빼고)
    "sanae": ((200, 250), 0.30, 0.20, 1.0, 1.0),      # 파란 치마
    "remilia": ((330, 358), 0.10, 0.55, 1.0, 1.0),    # 분홍 드레스·빨간 리본 (살색 10~20도는 빼고)
    "flandre": ((335, 20), 0.40, 0.30, 1.0, 1.0),     # 빨간 옷
}
# 색 스킨: id → (이름, 바꿀 색상(도, None 이면 무채색), 채도 배수, 밝기 배수, 등급)
COLORS = {
    "blue": ("파랑", 215, 1.0, 1.0, "N"), "green": ("초록", 135, 0.9, 0.95, "N"),
    "purple": ("보라", 275, 0.9, 1.0, "N"), "pink": ("분홍", 330, 0.8, 1.05, "N"),
    "orange": ("주황", 28, 1.0, 1.0, "N"), "red": ("빨강", 355, 1.0, 0.95, "N"),
    "mint": ("민트", 165, 0.7, 1.05, "N"), "sky": ("하늘", 200, 0.8, 1.05, "N"),
    "black": ("검정", None, 0.12, 0.42, "R"),
}
# 어두운 옷(마리사)용: id → (이름, 색상, 채도, 밝기 더하기, 등급)
DARK_COLORS = {
    "navy": ("남색", 225, 0.55, 0.20, "N"), "purple": ("보라", 280, 0.5, 0.22, "N"),
    "red": ("빨강", 355, 0.6, 0.22, "N"), "white": ("하양", None, 0.0, 0.70, "R"),
}
CHAR_COLORS = {
    "reimu": ["blue", "green", "purple", "black"],
    "marisa": ["navy", "purple", "red", "white"],
    "sakuya": ["red", "green", "purple", "black"],
    "cirno": ["pink", "green", "orange", "purple"],
    "sanae": ["red", "orange", "purple", "black"],
    "remilia": ["sky", "mint", "purple", "black"],
    "flandre": ["blue", "green", "purple", "black"],
}
FILTERS = {"mono": ("흑백", "R"), "ghost": ("유령", "SR"), "silver": ("은빛", "SR"), "gold": ("금빛", "SSR")}
EFFECTS = {
    "hearts": ("하트 발자국", "R"), "petals": ("벚꽃 발자국", "R"), "notes": ("음표", "R"),
    "stars": ("별 발자국", "SR"), "sparkle": ("반짝이 오라", "SR"), "rainbow": ("무지개 발자국", "SSR"),
}
FOOTPRINTS = {"hearts", "petals", "stars", "rainbow"}
# 전용 의상 그림 폴더(<캐릭터>@<스킨>)의 이름 — 폴더만 넣으면 전설 등급으로 뽑기에 들어감
ART_NAMES = {"yukata": "유카타", "santa": "산타", "swimsuit": "수영복", "pajama": "잠옷", "school": "교복",
             "maid": "메이드", "kimono": "기모노", "witch": "마녀"}


@dataclass(frozen=True)
class Item:
    id: str              # "reimu:blue" / "reimu:gold" / "fx:hearts"
    char: str | None     # 이펙트는 None (누구에게나)
    kind: str            # color / filter / fx
    skin: str
    name: str
    rarity: str


def _catalog() -> dict[str, Item]:
    items: list[Item] = []
    for ch, colors in CHAR_COLORS.items():
        table = DARK_COLORS if OUTFIT[ch][0] == "dark" else COLORS
        for c in colors:
            name, *_, rank = table[c]
            items.append(Item(f"{ch}:{c}", ch, "color", c, f"{SHORT[ch]} {name}", rank))
        for f, (name, rank) in FILTERS.items():
            items.append(Item(f"{ch}:{f}", ch, "filter", f, f"{SHORT[ch]} {name}", rank))
    for folder in sorted(SPRITE_DIR.glob("*@*")):                    # 전용 의상 (그림)
        char, _, skin = folder.name.partition("@")
        if char in CHAR_COLORS and (folder / "manifest.json").exists():
            items.append(Item(f"{char}:{skin}", char, "art", skin, f"{SHORT[char]} {ART_NAMES.get(skin, skin)}", "SSR"))
    for e, (name, rank) in EFFECTS.items():
        items.append(Item(f"fx:{e}", None, "fx", e, name, rank))
    return {it.id: it for it in items}


def skins_of(char: str) -> list[str]:
    """그 캐릭터가 입을 수 있는 옷 (색 → 재질 → 전용 의상 순)."""
    return [it.skin for it in ITEMS.values() if it.char == char]


ITEMS = _catalog()


def price(s: GameState) -> int:
    return PRICE_PER_STAGE * s.shrine_level


def pickup(s: GameState, today: date | None = None) -> str | None:
    """이번 주 픽업 캐릭터 (만난 친구 중에서 주마다 돌아가며)."""
    chars = [k for k in CHAR_COLORS if k in s.unlocked]
    if not chars:
        return None
    week = (today or date.today()).isocalendar()[1]
    return chars[week % len(chars)]


def pool(s: GameState) -> list[Item]:
    """만난 친구의 옷 + 이펙트."""
    return [it for it in ITEMS.values() if it.char is None or it.char in s.unlocked]


def pull(s: GameState, n: int, rng: random.Random | None = None) -> list[tuple[str, str]] | None:
    """n번(1 또는 10) 뽑기. 새전이 모자라면 None. 결과: [(아이템 id, "new" | "dup")]"""
    rng = rng or random.Random()
    cost = price(s) * (9 if n == 10 else n)
    if s.saisen < cost:
        return None
    s.saisen -= cost
    items = pool(s)
    pick = pickup(s)
    results: list[tuple[str, str]] = []
    for i in range(n):
        s.wardrobe_pity += 1
        if s.wardrobe_pity >= PITY:
            rank = "SSR"
        elif n == 10 and i == n - 1 and all(ITEMS[k].rarity in ("N", "R") for k, _ in results):
            rank = rng.choices(["SR", "SSR"], weights=[RARITY["SR"][2], RARITY["SSR"][2]])[0]
        else:
            rank = rng.choices(list(RARITY), weights=[r[2] for r in RARITY.values()])[0]
        if rank == "SSR":
            s.wardrobe_pity = 0
        cands = [it for it in items if it.rarity == rank]
        it = rng.choices(cands, weights=[PICKUP_WEIGHT if it.char == pick else 1 for it in cands])[0]
        if it.id in s.wardrobe:
            s.cloth += CLOTH_GAIN[it.rarity]
            results.append((it.id, "dup"))
        else:
            s.wardrobe.append(it.id)
            results.append((it.id, "new"))
    s.wardrobe_pulls += n
    return results


def exchange(s: GameState, item_id: str) -> bool:
    it = ITEMS.get(item_id)
    if it is None or item_id in s.wardrobe or s.cloth < CLOTH_COST[it.rarity]:
        return False
    if it.char is not None and it.char not in s.unlocked:
        return False
    s.cloth -= CLOTH_COST[it.rarity]
    s.wardrobe.append(item_id)
    return True


def wear(s: GameState, char: str, skin: str | None) -> bool:
    """옷 갈아입기 (None = 기본 옷)."""
    if skin is None:
        s.skins.pop(char, None)
        return True
    if f"{char}:{skin}" not in s.wardrobe:
        return False
    s.skins[char] = skin
    return True


def set_effect(s: GameState, char: str, fx: str | None) -> bool:
    if fx is None:
        s.effects.pop(char, None)
        return True
    if f"fx:{fx}" not in s.wardrobe:
        return False
    s.effects[char] = fx
    return True


# ── 그림 바꾸기 ──
def _hue_dist(h: float, center: float) -> float:
    """색상 차이 (-0.5 ~ 0.5)."""
    return (h - center + 0.5) % 1.0 - 0.5


def _in_outfit(h: float, s: float, v: float, spec) -> bool:
    rng, smin, vmin, smax, vmax = spec
    if not (smin <= s <= smax and vmin <= v <= vmax):
        return False
    if rng == "dark":
        return True
    lo, hi = rng
    hd = h * 360
    return (hd >= lo or hd <= hi) if lo > hi else (lo <= hd <= hi)


def _center(rng) -> float:
    lo, hi = rng
    if lo > hi:
        hi += 360
    return ((lo + hi) / 2 % 360) / 360


def _map_pixels(img: QImage, fn: Callable[[int, int, int, int], tuple[int, int, int, int]]) -> QImage:
    """픽셀마다 fn(r, g, b, a) → (r, g, b, a). 같은 색은 한 번만 계산."""
    out = img.convertToFormat(QImage.Format_ARGB32)
    mv = memoryview(out.bits()).cast("B")
    cache: dict[tuple, tuple] = {}
    for i in range(0, out.width() * out.height() * 4, 4):
        a = mv[i + 3]
        if a < 4:
            continue
        key = (mv[i + 2], mv[i + 1], mv[i], a)
        new = cache.get(key)
        if new is None:
            new = cache[key] = fn(*key)
        mv[i + 2], mv[i + 1], mv[i], mv[i + 3] = new
    return out


def _recolor_fn(spec, color, dark: bool):
    if dark:
        th, ts, tv_add = color[1], color[2], color[3]
    else:
        th, sm, vm = color[1], color[2], color[3]
        center = _center(spec[0])

    def fn(r, g, b, a):
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if not _in_outfit(h, s, v, spec):
            return r, g, b, a
        if dark:
            if th is None:                                   # 하양
                nh, ns, nv = h, 0.0, min(1.0, 0.55 + v)
            else:
                nh, ns, nv = th / 360, ts, min(1.0, v + tv_add)
        elif th is None:                                     # 검정: 무채색으로 어둡게
            nh, ns, nv = h, s * sm, v * vm
        else:                                                # 원래 색과의 차이(음영)를 살려 색상만 옮김
            nh = (th / 360 + _hue_dist(h, center)) % 1.0
            ns, nv = min(1.0, s * sm), min(1.0, v * vm)
        rr, gg, bb = colorsys.hsv_to_rgb(nh, ns, nv)
        return int(rr * 255), int(gg * 255), int(bb * 255), a
    return fn


def _ramp(stops):
    def at(t: float):
        t = min(1.0, max(0.0, t))
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t <= t1:
                k = (t - t0) / max(1e-6, t1 - t0)
                return tuple(int(c0[j] + (c1[j] - c0[j]) * k) for j in range(3))
        return stops[-1][1]
    return at


GOLD = _ramp([(0.0, (60, 36, 6)), (0.25, (138, 90, 16)), (0.6, (232, 185, 35)), (1.0, (255, 246, 200))])
SILVER = _ramp([(0.0, (40, 44, 54)), (0.25, (92, 100, 116)), (0.6, (176, 186, 202)), (1.0, (248, 250, 253))])


def _filter_fn(kind: str):
    def fn(r, g, b, a):
        lum = (0.3 * r + 0.59 * g + 0.11 * b) / 255
        if kind == "mono":
            y = int(lum * 255)
            return y, y, y, a
        if kind == "gold":
            return (*GOLD(lum * 1.1), a)
        if kind == "silver":
            return (*SILVER(lum * 1.05), a)
        # ghost: 푸르스름하게 비치는
        return (int(r * 0.45 + 200 * 0.55), int(g * 0.45 + 228 * 0.55), int(b * 0.45 + 255 * 0.55), int(a * 0.62))
    return fn


def transform_for(char: str, skin: str) -> Callable[[QImage], QImage] | None:
    if skin in FILTERS:
        fn = _filter_fn(skin)
    elif char in OUTFIT:
        dark = OUTFIT[char][0] == "dark"
        table = DARK_COLORS if dark else COLORS
        if skin not in table:
            return None
        fn = _recolor_fn(OUTFIT[char], table[skin], dark)
    else:
        return None
    return lambda img: _map_pixels(img, fn)


_skinned: dict[tuple[str, str], ImageSprites | None] = {}


def sprites_for(char: str, skin: str | None) -> ImageSprites | None:
    """스킨을 입힌 그림 묶음. 전용 의상 그림 폴더(<캐릭터>@<스킨>)가 있으면 그것, 아니면 기본 그림을 바꿔서."""
    base = image_sprites(char)
    if not skin or base is None:
        return base
    key = (char, skin)
    if key not in _skinned:
        folder = SPRITE_DIR / f"{char}@{skin}"          # 전용 의상: 시트를 전부 뽑아 넣은 폴더
        art = image_sprites(f"{char}@{skin}", folder) if (folder / "manifest.json").exists() else None
        if art is not None:
            _skinned[key] = art
        else:
            fn = transform_for(char, skin)
            _skinned[key] = base.variant(fn) if fn else base
    return _skinned[key]


# ── 이펙트 그리기 (PetWindow 가 부름) ──
def _heart(p: QPainter, cx: float, cy: float, size: float, color: QColor) -> None:
    s = size / 2
    path = QPainterPath()
    path.moveTo(cx, cy + s * 0.9)
    path.cubicTo(cx - s * 1.6, cy - s * 0.2, cx - s * 0.6, cy - s * 1.3, cx, cy - s * 0.45)
    path.cubicTo(cx + s * 0.6, cy - s * 1.3, cx + s * 1.6, cy - s * 0.2, cx, cy + s * 0.9)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawPath(path)


def _star(p: QPainter, cx: float, cy: float, r: float, color: QColor, points: int = 5, inner: float = 0.45) -> None:
    path = QPainterPath()
    for k in range(points * 2):
        a = -math.pi / 2 + k * math.pi / points
        rr = r if k % 2 == 0 else r * inner
        pt = QPointF(cx + math.cos(a) * rr, cy + math.sin(a) * rr)
        if k == 0:
            path.moveTo(pt)
        else:
            path.lineTo(pt)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawPath(path)


def draw_mark(p: QPainter, kind: str, x: float, y: float, age: float, life: float, seed: float) -> None:
    """이펙트 한 조각. (x, y) 는 창 안 좌표, age/life 로 흐려짐."""
    a = max(0.0, 1 - age / life)
    if kind == "hearts":
        _heart(p, x, y - 3, 8, QColor(240, 90, 130, int(210 * a)))
    elif kind == "petals":
        draw_petal(p, x, y - 3, 4.5, seed * 360, a)
    elif kind == "stars":
        _star(p, x, y - 4, 5, QColor(250, 210, 60, int(230 * a)))
    elif kind == "rainbow":
        c = QColor.fromHsvF(seed % 1.0, 0.65, 1.0, 0.85 * a)
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawEllipse(QPointF(x, y - 2), 4.2, 2.6)
        p.drawEllipse(QPointF(x - 2.6, y - 6), 1.4, 1.4)
        p.drawEllipse(QPointF(x + 2.6, y - 6), 1.4, 1.4)
    elif kind == "notes":
        f = QFont("Malgun Gothic", 10)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor.fromHsvF((0.55 + seed * 0.4) % 1.0, 0.6, 0.85, a))
        p.drawText(QPointF(x + math.sin(age * 4 + seed * 6) * 4, y - age * 22), "♪" if seed < 0.5 else "♫")
    elif kind == "sparkle":
        tw = math.sin(min(1.0, age / life) * math.pi)
        _star(p, x, y, 4.5 * tw + 0.5, QColor(255, 210, 80, int(245 * tw)), points=4, inner=0.3)


def draw_icon(p: QPainter, rect: QRectF, kind: str) -> None:
    """의상실 칸에 그리는 이펙트 아이콘 (발자국 몇 개)."""
    cx, cy = rect.center().x(), rect.center().y()
    if kind == "sparkle":
        for dx, dy, life in ((-10, -8, 1.0), (8, -2, 0.7), (-2, 10, 0.85), (12, 12, 0.6)):
            draw_mark(p, kind, cx + dx, cy + dy, life / 2, life, 0.3)
    elif kind == "notes":
        for i, (dx, dy) in enumerate(((-10, 10), (6, 2))):
            draw_mark(p, kind, cx + dx, cy + dy + 12, 0.0, 1.0, 0.3 + i * 0.4)
    else:
        for i in range(4):
            draw_mark(p, kind, cx - 18 + i * 12, cy + 6 - (i % 2) * 6, 0.0, 1.0, i * 0.22)
    p.setPen(QPen(Qt.NoPen))
