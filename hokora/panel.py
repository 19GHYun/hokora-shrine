# -*- coding: utf-8 -*-
"""신사를 누르면 뜨는 창: 신사 키우기 + 도감. 바깥을 누르면 닫힌다."""
from __future__ import annotations

import time
from typing import Callable

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QTabBar, QVBoxLayout, QWidget)

from . import affection as aff
from . import daily, omamori, season, torii, wardrobe
from .decor import decor_image
from .guests import GUEST_ABOUT, VISITS, guest_stage
from .omikuji import can_draw
from .prayer import NEWS_BOOST, WISHES, blocked, fmt_left, income_multiplier, left, news_active
from .progress import UNLOCKS
from .render import CHARACTERS, GUESTS, Pose, draw_character
from .shrine import DRAW_STAGE, STAGE_SIZE
from .sprites import image_sprites
from .state import DECOR, SAISEN_BOX, SHRINE_STAGES, GameState

PORTRAIT = 76
GUEST_KEYS = [k for keys, _ in VISITS.values() for k in keys]

STYLE = """
QWidget#panel { background: transparent; }
QLabel { color: #2B1D21; font-family: 'Malgun Gothic'; font-size: 12px; }
QLabel#title { font-size: 17px; font-weight: 700; color: #B3122C; }
QLabel#sub { color: #8C7479; }
QLabel#section { font-size: 13px; font-weight: 700; color: #2B1D21; padding-top: 4px; }
QLabel#name { font-size: 13px; font-weight: 700; color: #B3122C; }
QLabel#locked { font-size: 13px; font-weight: 700; color: #8C7479; }
QLabel#goal { font-size: 11px; color: #5A464B; }
QLabel#done { font-size: 11px; color: #3E8E5A; font-weight: 700; }
QWidget#card { background: rgba(255,255,255,215); border: 1px solid rgba(200,16,46,45); border-radius: 10px; }
QProgressBar { border: none; background: rgba(200,16,46,30); border-radius: 4px; height: 8px;
               max-height: 8px; text-align: center; font-size: 1px; color: transparent; }
QProgressBar::chunk { background: #D9412E; border-radius: 4px; }
QPushButton#upgrade { background: #C8102E; color: #FFFFFF; border: none; border-radius: 8px;
                      padding: 7px 14px; font-family: 'Malgun Gothic'; font-size: 12px; font-weight: 700; }
QPushButton#upgrade:hover { background: #A90D26; }
QPushButton#upgrade:disabled { background: rgba(200,16,46,90); }
QPushButton#small { background: #C8102E; color: #FFFFFF; border: none; border-radius: 6px;
                    padding: 4px 8px; font-family: 'Malgun Gothic'; font-size: 11px; font-weight: 700; }
QPushButton#small:hover { background: #A90D26; }
QPushButton#small:disabled { background: rgba(200,16,46,70); }
QPushButton#ghost { background: #FFFFFF; color: #9E1027; border: 1px solid rgba(200,16,46,110); border-radius: 6px;
                    padding: 4px 8px; font-family: 'Malgun Gothic'; font-size: 11px; font-weight: 700; }
QPushButton#ghost:hover { background: #FBE3E7; }
QCheckBox { color: #2B1D21; font-family: 'Malgun Gothic'; font-size: 12px; font-weight: 700; }
QCheckBox::indicator { width: 15px; height: 15px; }
QTabBar::tab { background: transparent; color: #8C7479; padding: 6px 10px; margin-right: 3px;
               font-family: 'Malgun Gothic'; font-size: 12px; font-weight: 700;
               border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #B3122C; border-bottom: 2px solid #C8102E; }
QTabBar::tab:hover { color: #9E1027; }
"""


_portraits: dict[tuple, QPixmap] = {}


def portrait(key: str, size: int, silhouette: bool, skin: str | None = None) -> QPixmap:
    """도감용 얼굴(서 있는 모습). 못 만난 캐릭터는 검은 실루엣. skin 이면 그 옷을 입은 모습."""
    ck = (key, size, silhouette, skin)
    if ck not in _portraits:
        _portraits[ck] = _portrait(key, size, silhouette, skin)
    return _portraits[ck]


def _portrait(key: str, size: int, silhouette: bool, skin: str | None) -> QPixmap:
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    sprites = wardrobe.sprites_for(key, skin) if key in CHARACTERS else image_sprites(key)
    if sprites is not None:
        img, anchor = sprites.images[sprites.sequence("idle")[0]]
        s = size * 0.95 / img.height()
        p.drawImage(QRectF((size - img.width() * s) / 2, size - img.height() * s, img.width() * s,
                           img.height() * s), img)
    else:
        draw_character(p, CHARACTERS.get(key) or GUESTS[key], Pose(kind="idle", t=0.3), QRectF(0, 0, size, size))
    if silhouette:
        p.setCompositionMode(QPainter.CompositionMode_SourceIn)
        p.fillRect(QRectF(0, 0, size, size), QColor(70, 50, 58, 230))
    p.end()
    return pm


def _decor_icon(key: str, size: int) -> QPixmap:
    img = decor_image(key)
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    sc = size / max(img.width(), img.height(), 1)
    w, h = img.width() * sc, img.height() * sc
    p.drawImage(QRectF((size - w) / 2, size - h, w, h), img)
    p.end()
    return pm


class _Stamps(QWidget):
    """출석 도장판 7칸."""

    def __init__(self, state: GameState):
        super().__init__()
        self.state = state
        self.setFixedHeight(46)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        daily.draw_stamps(p, QRectF(self.rect()).adjusted(0, 2, 0, -2), daily.cycle_day(self.state))
        p.end()


class _LookButton(QWidget):
    """신사 모양 고르기: 그 단계 신사의 작은 그림. 아직 못 키운 단계는 잠김."""

    W, H = 72, 58

    def __init__(self, stage: int, on_pick: Callable[[int], None]):
        super().__init__()
        self.stage, self.on_pick = stage, on_pick
        self.selected = self.locked = None
        self.setFixedSize(self.W, self.H + 18)

    def set_state(self, selected: bool, locked: bool) -> None:
        if (selected, locked) != (self.selected, self.locked):
            self.selected, self.locked = selected, locked
            self.setCursor(Qt.ArrowCursor if locked else Qt.PointingHandCursor)
            self.setToolTip("아직 키우지 않은 단계예요" if locked else SHRINE_STAGES[self.stage][0])
            self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, self.W - 2, self.H - 2)
        p.setPen(QPen(QColor("#C8102E"), 2) if self.selected else QPen(QColor(200, 16, 46, 50), 1))
        p.setBrush(QColor(255, 255, 255, 230))
        p.drawRoundedRect(r, 8, 8)
        bw, bh = STAGE_SIZE[self.stage]
        k = min((r.width() - 10) / bw, (r.height() - 8) / bh)
        p.save()
        p.translate(r.center().x() - bw * k / 2, r.bottom() - 4 - bh * k)
        p.scale(k, k)
        DRAW_STAGE[self.stage](p)
        p.restore()
        if self.locked:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(246, 240, 242, 190))
            p.drawRoundedRect(r, 8, 8)
            p.setPen(QColor(140, 116, 121))
            p.drawText(r, Qt.AlignCenter, "🔒")
        f = QFont("Malgun Gothic", 8)
        f.setBold(bool(self.selected))
        p.setFont(f)
        p.setPen(QColor("#B3122C") if self.selected else QColor("#8C7479"))
        p.drawText(QRectF(0, self.H, self.W, 18), Qt.AlignCenter, f"{self.stage}단계")
        p.end()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton and not self.locked:
            self.on_pick(self.stage)


class _CharmTile(QWidget):
    """부적 하나: 그림·이름·레벨·효과. 가진 부적을 누르면 지니기/내려놓기."""

    W, H = 84, 128

    def __init__(self, state: GameState, key: str, on_click: Callable[[str], None]):
        super().__init__()
        self.state, self.key, self.on_click = state, key, on_click
        self.setFixedSize(self.W, self.H)

    def paintEvent(self, _e) -> None:
        s, c = self.state, omamori.CHARMS[self.key]
        lv = s.omamori.get(self.key, 0)
        owned, worn = lv > 0, self.key in s.equipped
        self.setCursor(Qt.PointingHandCursor if owned else Qt.ArrowCursor)
        self.setToolTip(("눌러서 내려놓기" if worn else "눌러서 지니기") if owned else "아직 없는 부적")
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, self.W - 2, self.H - 2)
        rim = QColor(omamori.RARITY[c.rarity][1])
        if worn:
            p.setPen(QPen(QColor("#C8102E"), 2.2))
        elif owned:
            rim.setAlpha(110)
            p.setPen(QPen(rim, 1.2))
        else:
            p.setPen(QPen(QColor(200, 16, 46, 40), 1, Qt.DashLine))
        p.setBrush(QColor(255, 255, 255, 225 if owned else 150))
        p.drawRoundedRect(r, 9, 9)
        omamori.draw_omamori(p, QRectF(18, 8, self.W - 36, 56), c if owned else None, locked=not owned)
        f = QFont("Malgun Gothic", 8)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(omamori.RARITY[c.rarity][1]) if owned else QColor(140, 116, 121))
        p.drawText(QRectF(2, 68, self.W - 4, 16), Qt.AlignCenter, c.name.replace(" 부적", "") if owned else "???")
        small = QFont("Malgun Gothic", 7)
        p.setFont(small)
        p.setPen(QColor("#8C7479"))
        p.drawText(QRectF(2, 84, self.W - 4, 14), Qt.AlignCenter,
                   f"Lv.{lv} · {omamori.RARITY[c.rarity][0]}" if owned else omamori.RARITY[c.rarity][0])
        if owned:
            p.setPen(QColor("#3A2A2E"))
            p.drawText(QRectF(4, 98, self.W - 8, 28), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
                       omamori.effect_text(c, lv))
        if worn:
            badge = QRectF(5, 5, 30, 15)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#C8102E"))
            p.drawRoundedRect(badge, 7, 7)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(badge, Qt.AlignCenter, "지님")
        p.end()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton and self.state.omamori.get(self.key):
            self.on_click(self.key)


class _PullStrip(QWidget):
    """방금 뽑은 부적들 (1개 또는 10개)."""

    def __init__(self):
        super().__init__()
        self.results: list[tuple] = []
        self.setFixedHeight(0)

    def set_results(self, s: GameState, results: list[tuple[str, str]]) -> None:
        self.results = [(omamori.CHARMS[k], tag, s.omamori.get(k, 1)) for k, tag in results]
        self.setFixedHeight(96 if results else 0)
        self.update()

    def paintEvent(self, _e) -> None:
        if not self.results:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(200, 16, 46, 60), 1))
        p.setBrush(QColor(255, 248, 236, 235))
        p.drawRoundedRect(r, 10, 10)
        f = QFont("Malgun Gothic", 8)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#B3122C"))
        best = max(["N", "R", "SR", "SSR"].index(c.rarity) for c, _, _ in self.results)
        p.drawText(QRectF(10, 4, r.width() - 20, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   {3: "✨ 전설 부적이다!!", 2: "✨ 귀한 부적이 나왔다!"}.get(best, "방금 뽑은 부적"))
        n = len(self.results)
        cell = min(56.0, (r.width() - 12) / n)
        x0 = r.center().x() - cell * n / 2
        tagf = QFont("Malgun Gothic", 7)
        tagf.setBold(True)
        for i, (c, tag, lv) in enumerate(self.results):
            x = x0 + i * cell
            omamori.draw_omamori(p, QRectF(x + cell / 2 - 17, 22, 34, 48), c)
            label, col = {"new": ("NEW!", "#C8102E"), "up": (f"Lv.{lv}", "#3E8E5A"), "max": ("반환", "#8C7479")}[tag]
            p.setFont(tagf)
            p.setPen(QColor(col))
            p.drawText(QRectF(x, 74, cell, 14), Qt.AlignCenter, label)
        p.end()


class _WTile(QWidget):
    """의상실 칸: 옷(그 옷을 입은 모습) 또는 이펙트(아이콘). 누르면 입기/쓰기, 없는 건 옷감 교환."""

    W, H = 84, 108

    def __init__(self, on_click: Callable[[tuple], None]):
        super().__init__()
        self.on_click = on_click
        self.setFixedSize(self.W, self.H)
        self.payload: tuple | None = None
        self.pix: QPixmap | None = None
        self.icon = ""
        self.title = self.sub = ""
        self.rarity = "N"
        self.mode = "own"                  # worn / own / trade / locked

    def set(self, payload: tuple, title: str, sub: str, rarity: str, mode: str,
            pix: QPixmap | None = None, icon: str = "") -> None:
        self.payload, self.title, self.sub, self.rarity, self.mode = payload, title, sub, rarity, mode
        self.pix, self.icon = pix, icon
        self.setCursor(Qt.ArrowCursor if mode == "locked" else Qt.PointingHandCursor)
        self.setToolTip({"worn": "입고 있어요", "own": "눌러서 입기", "trade": "눌러서 옷감으로 교환",
                         "locked": "옷감이 모자라요 — 뽑기로 얻거나 옷감을 모아요"}[mode])
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(1, 1, self.W - 2, self.H - 2)
        rim = QColor(wardrobe.RARITY[self.rarity][1])
        if self.mode == "worn":
            p.setPen(QPen(QColor("#C8102E"), 2.2))
        elif self.mode == "own":
            rim.setAlpha(110)
            p.setPen(QPen(rim, 1.2))
        else:
            p.setPen(QPen(QColor(200, 16, 46, 40), 1, Qt.DashLine))
        p.setBrush(QColor(255, 255, 255, 225 if self.mode in ("worn", "own") else 150))
        p.drawRoundedRect(r, 9, 9)
        art = QRectF(10, 6, self.W - 20, 60)
        if self.pix is not None:
            p.drawPixmap(art.toRect(), self.pix)
        elif self.icon:
            wardrobe.draw_icon(p, art, self.icon)
        if self.mode in ("trade", "locked"):                  # 아직 없는 것: 흐리게
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(250, 246, 247, 170))
            p.drawRoundedRect(art, 6, 6)
        f = QFont("Malgun Gothic", 8)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(wardrobe.RARITY[self.rarity][1]) if self.mode in ("worn", "own") else QColor(140, 116, 121))
        p.drawText(QRectF(2, 68, self.W - 4, 16), Qt.AlignCenter, self.title)
        small = QFont("Malgun Gothic", 7)
        p.setFont(small)
        p.setPen(QColor("#C8102E") if self.mode == "trade" else QColor("#8C7479"))
        p.drawText(QRectF(2, 85, self.W - 4, 16), Qt.AlignCenter, self.sub)
        if self.mode == "worn":
            badge = QRectF(5, 5, 30, 15)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#C8102E"))
            p.drawRoundedRect(badge, 7, 7)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(badge, Qt.AlignCenter, "입음")
        p.end()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton and self.payload and self.mode in ("own", "trade"):
            self.on_click(self.payload)


class _CharPick(QWidget):
    """의상실에서 옷을 입힐 친구 고르기 (작은 얼굴)."""

    S = 46

    def __init__(self, key: str, on_pick: Callable[[str], None]):
        super().__init__()
        self.key, self.on_pick = key, on_pick
        self.selected = False
        self.skin: str | None = None
        self.setFixedSize(self.S, self.S + 2)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(CHARACTERS[key].name)

    def set_state(self, selected: bool, skin: str | None) -> None:
        if (selected, skin) != (self.selected, self.skin):
            self.selected, self.skin = selected, skin
            self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, self.S - 2, self.S - 2)
        p.setPen(QPen(QColor("#C8102E"), 2) if self.selected else QPen(QColor(200, 16, 46, 50), 1))
        p.setBrush(QColor(255, 255, 255, 230))
        p.drawEllipse(r)
        p.drawPixmap(QRectF(5, 3, self.S - 10, self.S - 10).toRect(), portrait(self.key, 60, False, self.skin))
        p.end()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.on_pick(self.key)


class _WardrobeStrip(QWidget):
    """방금 뽑은 옷·이펙트."""

    def __init__(self):
        super().__init__()
        self.results: list[tuple] = []
        self.setFixedHeight(0)

    def set_results(self, results: list[tuple[str, str]]) -> None:
        self.results = [(wardrobe.ITEMS[k], tag) for k, tag in results]
        self.setFixedHeight(100 if results else 0)
        self.update()

    def paintEvent(self, _e) -> None:
        if not self.results:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(200, 16, 46, 60), 1))
        p.setBrush(QColor(255, 248, 236, 235))
        p.drawRoundedRect(r, 10, 10)
        f = QFont("Malgun Gothic", 8)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#B3122C"))
        best = max(["N", "R", "SR", "SSR"].index(it.rarity) for it, _ in self.results)
        p.drawText(QRectF(10, 4, r.width() - 20, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   {3: "✨ 전설이다!!", 2: "✨ 귀한 게 나왔다!"}.get(best, "방금 뽑은 것"))
        n = len(self.results)
        cell = min(56.0, (r.width() - 12) / n)
        x0 = r.center().x() - cell * n / 2
        tagf = QFont("Malgun Gothic", 7)
        tagf.setBold(True)
        for i, (it, tag) in enumerate(self.results):
            x = x0 + i * cell
            box = QRectF(x + cell / 2 - 21, 22, 42, 50)
            p.setPen(QPen(QColor(wardrobe.RARITY[it.rarity][1]), 1.4))
            p.setBrush(QColor(255, 255, 255, 220))
            p.drawRoundedRect(box, 6, 6)
            if it.char is not None:
                p.drawPixmap(box.adjusted(3, 2, -3, -2).toRect(), portrait(it.char, 60, False, it.skin))
            else:
                wardrobe.draw_icon(p, box, it.skin)
            p.setFont(tagf)
            p.setPen(QColor("#C8102E") if tag == "new" else QColor("#8C7479"))
            p.drawText(QRectF(x, 76, cell, 14), Qt.AlignCenter,
                       "NEW!" if tag == "new" else f"옷감+{wardrobe.CLOTH_GAIN[it.rarity]}")
        p.end()


def _hearts(s: GameState, key: str) -> str:
    """도감 카드의 하트 (분홍색)."""
    return f"<span style='color:#E0457B'>{aff.hearts(s, key)}</span>"


class ShrinePanel(QWidget):
    def __init__(self, state: GameState, on_upgrade: Callable[[], None], on_omikuji: Callable[[], None],
                 on_decor: Callable[[str, str], None], on_pray: Callable[[str], None],
                 on_box: Callable[[], None], tab: int = 0, on_action: Callable[[str, object], object] | None = None):
        super().__init__(None, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("panel")
        self.setStyleSheet(STYLE)
        self.state = state
        self.on_upgrade = on_upgrade
        self.on_omikuji = on_omikuji
        self.on_decor = on_decor
        self.on_pray = on_pray
        self.on_box = on_box
        self.on_action = on_action
        self.setFixedWidth(490)

        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 16)
        v.setSpacing(8)

        # ── 신사 ──
        self.title = QLabel(objectName="title")
        self.sub = QLabel(objectName="sub")
        v.addWidget(self.title)
        v.addWidget(self.sub)
        self.tabs = QTabBar()
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        v.addWidget(self.tabs)
        page1, page2, page3, page4, page5, page6, page7, page8 = (QWidget() for _ in range(8))
        p1, p3, p4, p5, p6, p7, p8 = (QVBoxLayout(pg) for pg in (page1, page3, page4, page5, page6, page7, page8))
        for lay in (p1, p3, p4, p5, p6, p7, p8):
            lay.setContentsMargins(0, 4, 0, 0)
            lay.setSpacing(10)
        self.pages = [page1, page6, page4, page7, page8, page2, page5, page3]
        for name, page in zip(("신사", "부탁", "참배", "부적", "의상", "도감", "손님", "꾸미기"), self.pages):
            self.tabs.addTab(name)
            page.hide()
            v.addWidget(page)
        up = QHBoxLayout()
        self.up_bar = QProgressBar()
        self.up_bar.setTextVisible(False)
        self.up_label = QLabel(objectName="goal")
        col = QVBoxLayout()
        col.setSpacing(3)
        col.addWidget(self.up_label)
        col.addWidget(self.up_bar)
        self.up_btn = QPushButton(objectName="upgrade")
        self.up_btn.setCursor(Qt.PointingHandCursor)
        self.up_btn.clicked.connect(self._upgrade)
        up.addLayout(col, 1)
        up.addWidget(self.up_btn)
        p1.addLayout(up)

        # ── 새전함 (꺼져 있는 동안의 수입) ──
        box = QHBoxLayout()
        self.box_label = QLabel(objectName="goal")
        self.box_label.setWordWrap(True)
        self.box_btn = QPushButton(objectName="upgrade")
        self.box_btn.setCursor(Qt.PointingHandCursor)
        self.box_btn.clicked.connect(self._box)
        box.addWidget(self.box_label, 1)
        box.addWidget(self.box_btn)
        p1.addLayout(box)

        # ── 센본토리이 ──
        trow = QHBoxLayout()
        self.torii_label = QLabel(objectName="goal")
        self.torii_label.setWordWrap(True)
        self.torii_btn = QPushButton(objectName="upgrade")
        self.torii_btn.setCursor(Qt.PointingHandCursor)
        self.torii_btn.clicked.connect(lambda: self._act("torii", 1))
        self.torii10_btn = QPushButton(objectName="ghost")
        self.torii10_btn.setCursor(Qt.PointingHandCursor)
        self.torii10_btn.clicked.connect(lambda: self._act("torii", 10))
        trow.addWidget(self.torii_label, 1)
        trow.addWidget(self.torii_btn)
        trow.addWidget(self.torii10_btn)
        p1.addLayout(trow)

        # ── 오미쿠지 ──
        omi = QHBoxLayout()
        self.omi_label = QLabel(objectName="goal")
        self.omi_btn = QPushButton(objectName="upgrade")
        self.omi_btn.setCursor(Qt.PointingHandCursor)
        self.omi_btn.clicked.connect(self._omikuji)
        omi.addWidget(self.omi_label, 1)
        omi.addWidget(self.omi_btn)
        p1.addLayout(omi)
        self.stats = QLabel(objectName="sub")
        self.stats.setWordWrap(True)
        p1.addWidget(self.stats)

        # ── 도감 ──
        grid = QGridLayout(page2)
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setSpacing(8)
        self.cards: dict[str, tuple] = {}
        for i, key in enumerate(UNLOCKS):
            card = QWidget(objectName="card")
            card.setAttribute(Qt.WA_StyledBackground, True)
            h = QHBoxLayout(card)
            h.setContentsMargins(8, 8, 10, 8)
            pic = QLabel()
            pic.setFixedSize(PORTRAIT, PORTRAIT)
            info = QVBoxLayout()
            info.setSpacing(3)
            name = QLabel()
            info.addWidget(name)
            goals = []
            for _ in UNLOCKS[key].goals or (None,):
                g_label = QLabel(objectName="goal")
                g_label.setWordWrap(True)
                g_bar = QProgressBar()
                g_bar.setTextVisible(False)
                g_bar.setRange(0, 1000)
                info.addWidget(g_label)
                info.addWidget(g_bar)
                goals.append((g_label, g_bar))
            out = QCheckBox("밖에 나와 있기")
            out.setToolTip("끄면 신사 안에서 쉬어요 (작업표시줄에 안 나와요)")
            out.setCursor(Qt.PointingHandCursor)
            out.setStyleSheet("font-size: 11px;")
            out.toggled.connect(lambda on, k=key: self._act("out", (k, on)))
            info.addWidget(out)
            info.addStretch(1)
            h.addWidget(pic)
            h.addLayout(info, 1)
            grid.addWidget(card, i // 2, i % 2)
            self.cards[key] = (pic, name, goals, out)

        # ── 부적 (수여소) ──
        intro = QLabel("수여소에서 부적을 뽑아요. 3개까지 지니면 효과가 나고, 같은 부적이 또 나오면 "
                       "레벨이 올라요 (최대 Lv.5).", objectName="goal")
        intro.setWordWrap(True)
        p7.addWidget(intro)
        prow = QHBoxLayout()
        self.pull1 = QPushButton(objectName="upgrade")
        self.pull10 = QPushButton(objectName="upgrade")
        for b, n in ((self.pull1, 1), (self.pull10, 10)):
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, n=n: self._pull(n))
            prow.addWidget(b, 1)
        p7.addLayout(prow)
        self.pity_label = QLabel(objectName="goal")
        self.pity_label.setWordWrap(True)
        p7.addWidget(self.pity_label)
        self.pull_strip = _PullStrip()
        p7.addWidget(self.pull_strip)
        p7.addWidget(QLabel("지닌 부적", objectName="section"))
        self.worn_label = QLabel(objectName="done")
        self.worn_label.setWordWrap(True)
        p7.addWidget(self.worn_label)
        cgrid = QGridLayout()
        cgrid.setSpacing(6)
        self.charm_tiles = []
        for i, key in enumerate(omamori.CHARMS):
            tile = _CharmTile(state, key, self._equip)
            cgrid.addWidget(tile, i // 5, i % 5)
            self.charm_tiles.append(tile)
        p7.addLayout(cgrid)
        self.charm_stats = QLabel(objectName="sub")
        p7.addWidget(self.charm_stats)

        # ── 의상실 ──
        intro = QLabel("옷 색·재질과 발자국 이펙트를 뽑아요. 효과는 없고 보기만 바뀌어요. "
                       "중복은 옷감이 되고, 옷감으로 원하는 걸 교환할 수 있어요.", objectName="goal")
        intro.setWordWrap(True)
        p8.addWidget(intro)
        self.pickup_label = QLabel(objectName="done")
        p8.addWidget(self.pickup_label)
        wrow = QHBoxLayout()
        self.wpull1 = QPushButton(objectName="upgrade")
        self.wpull10 = QPushButton(objectName="upgrade")
        for b, n in ((self.wpull1, 1), (self.wpull10, 10)):
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, n=n: self._wpull(n))
            wrow.addWidget(b, 1)
        p8.addLayout(wrow)
        self.wpity_label = QLabel(objectName="goal")
        self.wpity_label.setWordWrap(True)
        p8.addWidget(self.wpity_label)
        self.wstrip = _WardrobeStrip()
        p8.addWidget(self.wstrip)
        p8.addWidget(QLabel("입히기", objectName="section"))
        crow = QHBoxLayout()
        crow.setSpacing(4)
        self.char_picks = {k: _CharPick(k, self._pick_char) for k in wardrobe.CHAR_COLORS}
        for w in self.char_picks.values():
            crow.addWidget(w)
        crow.addStretch(1)
        p8.addLayout(crow)
        self.w_char = next((k for k in wardrobe.CHAR_COLORS if k in state.unlocked), "reimu")
        self.w_view = "skin"                                  # 옷 / 이펙트 중 하나만 보여서 창이 너무 길어지지 않게
        vrow = QHBoxLayout()
        self.view_btns = {}
        for key, label in (("skin", "👘 옷"), ("fx", "✨ 이펙트")):
            b = QPushButton(label, objectName="ghost")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, key=key: self._wview(key))
            vrow.addWidget(b)
            self.view_btns[key] = b
        vrow.addStretch(1)
        p8.addLayout(vrow)
        self.skin_box, self.fx_box = QWidget(), QWidget()
        sgrid, fgrid = QGridLayout(self.skin_box), QGridLayout(self.fx_box)
        self.skin_tiles, self.fx_tiles = [], []
        most = max(len(wardrobe.skins_of(k)) for k in wardrobe.CHAR_COLORS)
        for grid_, tiles, n in ((sgrid, self.skin_tiles, 1 + most), (fgrid, self.fx_tiles, 1 + len(wardrobe.EFFECTS))):
            grid_.setContentsMargins(0, 0, 0, 0)
            grid_.setSpacing(6)
            for i in range(n):
                t = _WTile(self._wclick)
                grid_.addWidget(t, i // 5, i % 5)
                tiles.append(t)
            grid_.setColumnStretch(5, 1)
        p8.addWidget(self.skin_box)
        p8.addWidget(self.fx_box)
        self.fx_box.hide()
        self.wstats = QLabel(objectName="sub")
        p8.addWidget(self.wstats)

        # ── 부탁: 출석 도장 + 오늘의 부탁 ──
        p6.addWidget(QLabel("💮 출석 도장", objectName="section"))
        self.stamps = _Stamps(state)
        p6.addWidget(self.stamps)
        self.attend_label = QLabel(objectName="goal")
        self.attend_label.setWordWrap(True)
        p6.addWidget(self.attend_label)
        p6.addWidget(QLabel("레이무의 오늘의 부탁", objectName="section"))
        self.task_rows: list[tuple] = []
        for _ in range(3):
            card = QWidget(objectName="card")
            card.setAttribute(Qt.WA_StyledBackground, True)
            h = QHBoxLayout(card)
            h.setContentsMargins(12, 8, 12, 8)
            icon = QLabel()
            icon.setStyleSheet("font-size: 20px;")
            icon.setFixedWidth(32)
            col = QVBoxLayout()
            col.setSpacing(3)
            title = QLabel(objectName="name")
            bar = QProgressBar()
            bar.setTextVisible(False)
            status = QLabel(objectName="goal")
            for w in (title, bar, status):
                col.addWidget(w)
            h.addWidget(icon)
            h.addLayout(col, 1)
            p6.addWidget(card)
            self.task_rows.append((card, icon, title, bar, status))
        self.daily_foot = QLabel(objectName="sub")
        self.daily_foot.setWordWrap(True)
        p6.addWidget(self.daily_foot)

        # ── 손님 ──
        tip = QLabel("가끔 신사에 손님이 찾아와요. 신사가 커질수록 찾아오는 손님이 늘어요.", objectName="goal")
        tip.setWordWrap(True)
        p5.addWidget(tip)
        ggrid = QGridLayout()
        ggrid.setSpacing(8)
        self.guest_cards: dict[str, tuple] = {}
        for i, key in enumerate(GUEST_KEYS):
            card = QWidget(objectName="card")
            card.setAttribute(Qt.WA_StyledBackground, True)
            h = QHBoxLayout(card)
            h.setContentsMargins(8, 8, 10, 8)
            pic = QLabel()
            pic.setFixedSize(PORTRAIT, PORTRAIT)
            info = QVBoxLayout()
            info.setSpacing(3)
            name, line1, line2 = QLabel(), QLabel(objectName="goal"), QLabel(objectName="goal")
            line2.setWordWrap(True)
            for w in (name, line1, line2):
                info.addWidget(w)
            info.addStretch(1)
            h.addWidget(pic)
            h.addLayout(info, 1)
            ggrid.addWidget(card, i // 2, i % 2)
            self.guest_cards[key] = (pic, name, line1, line2)
        p5.addLayout(ggrid)
        p5.addWidget(QLabel("📰 붕붕마루 신문 스크랩", objectName="section"))
        self.news_boost = QLabel(objectName="done")
        p5.addWidget(self.news_boost)
        self.news_label = QLabel(objectName="goal")
        self.news_label.setWordWrap(True)
        p5.addWidget(self.news_label)
        self.guest_stats = QLabel(objectName="sub")
        p5.addWidget(self.guest_stats)

        # ── 참배 ──
        tip = QLabel("새전을 넣고 소원을 빌어요. 효과는 껐다 켜도 이어져요.", objectName="goal")
        tip.setWordWrap(True)
        p4.addWidget(tip)
        self.wish_rows: dict[str, tuple] = {}
        for key, w in WISHES.items():
            card = QWidget(objectName="card")
            card.setAttribute(Qt.WA_StyledBackground, True)
            h = QHBoxLayout(card)
            h.setContentsMargins(12, 8, 10, 8)
            icon = QLabel(w.icon)
            icon.setStyleSheet("font-size: 22px;")
            icon.setFixedWidth(34)
            col = QVBoxLayout()
            col.setSpacing(1)
            col.addWidget(QLabel(w.name, objectName="name"))
            desc = QLabel(w.desc, objectName="goal")
            desc.setWordWrap(True)
            col.addWidget(desc)
            status = QLabel(objectName="done")
            col.addWidget(status)
            btn = QPushButton(objectName="small")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumWidth(96)
            btn.clicked.connect(lambda _=False, k=key: self._pray(k))
            h.addWidget(icon)
            h.addLayout(col, 1)
            h.addWidget(btn)
            p4.addWidget(card)
            self.wish_rows[key] = (btn, status)

        # ── 꾸미기: 신사 모양·크기 ──
        p3.addWidget(QLabel("신사 모양", objectName="section"))
        lrow = QHBoxLayout()
        lrow.setSpacing(6)
        self.look_btns = [_LookButton(st, lambda st: self._act("look", st)) for st in SHRINE_STAGES]
        for b in self.look_btns:
            lrow.addWidget(b)
        lrow.addStretch(1)
        p3.addLayout(lrow)
        look_tip = QLabel("모양만 바뀌고, 수입은 가장 높이 올린 단계 그대로예요.", objectName="goal")
        p3.addWidget(look_tip)
        srow = QHBoxLayout()
        srow.addWidget(QLabel("크기", objectName="section"))
        self.size_btns: dict[float, QPushButton] = {}
        for k, label in ((1.0, "보통"), (0.85, "작게"), (0.7, "아주 작게")):
            b = QPushButton(label, objectName="ghost")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=k: self._act("scale", k))
            srow.addWidget(b)
            self.size_btns[k] = b
        srow.addStretch(1)
        p3.addLayout(srow)

        # ── 꾸미기 ──
        tip = QLabel("장식을 사서 신사 옆에 놓으면 분당 새전이 늘어요. 놓은 장식은 좌우로 끌어서 옮길 수 있어요.",
                     objectName="goal")
        tip.setWordWrap(True)
        p3.addWidget(tip)
        self.view_box = QCheckBox("신사 옆에 장식 보이기  (꺼도 효과는 그대로)")
        self.view_box.setCursor(Qt.PointingHandCursor)
        self.view_box.setChecked(state.show_decor)
        self.view_box.toggled.connect(lambda on: self.on_decor("", "show" if on else "hide"))
        p3.addWidget(self.view_box)
        dgrid = QGridLayout()
        dgrid.setSpacing(6)
        self.decor_rows: dict[str, tuple] = {}
        for i, key in enumerate(DECOR):
            name, price, bonus, _ = DECOR[key]
            card = QWidget(objectName="card")
            card.setAttribute(Qt.WA_StyledBackground, True)
            cv = QVBoxLayout(card)
            cv.setContentsMargins(6, 6, 6, 6)
            cv.setSpacing(2)
            pic = QLabel()
            pic.setAlignment(Qt.AlignCenter)
            pic.setPixmap(_decor_icon(key, 52))
            title = QLabel(name, objectName="name")
            title.setAlignment(Qt.AlignCenter)
            info = QLabel(f"분당 +{bonus}", objectName="goal")
            info.setAlignment(Qt.AlignCenter)
            btn = QPushButton()
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._decor_clicked(k))
            for w in (pic, title, info, btn):
                cv.addWidget(w)
            dgrid.addWidget(card, i // 3, i % 3)
            self.decor_rows[key] = (btn, price)
        p3.addLayout(dgrid)
        self._anchor = None
        self._top: float | None = None
        self._roles: dict[int, str] = {}
        self.tabs.setCurrentIndex(tab)
        self.tabs.currentChanged.connect(self._fit_tab)
        self.refresh()
        self._fit_tab(self.tabs.currentIndex())
        self._timer = QTimer(self, timeout=self.refresh, interval=1000)   # 열려 있는 동안 새전 등 갱신
        self._timer.start()

    def _role(self, w: QWidget, name: str) -> None:
        """스타일시트 이름을 바꾸고 다시 입힘 — 바뀔 때만."""
        if self._roles.get(id(w)) != name:
            self._roles[id(w)] = name
            w.setObjectName(name)
            w.style().unpolish(w)
            w.style().polish(w)

    # ── 내용 ──
    def refresh(self) -> None:
        s = self.state
        self.title.setText(f"⛩  {s.stage_name}  ({s.shrine_level}단계)")
        boost = income_multiplier(s)
        tags = (["번영 기원 ×2"] if left(s, "prosper") else []) + ([f"신문 ×{NEWS_BOOST:g}"] if news_active(s) else [])
        if season.is_new_year():
            tags.append(f"설날 ×{season.NEW_YEAR_BOOST}")
        self.sub.setText(f"새전 {s.saisen:,}   ·   분당 새전 {s.income_per_min * boost:g}"
                         + (f"  ({', '.join(tags)})" if tags else ""))
        drawable = can_draw(s)
        for key, (btn, status) in self.wish_rows.items():
            remain = left(s, key)
            why = blocked(s, key, drawable)
            status.setText(fmt_left(remain) if remain else "")
            status.setVisible(bool(remain))
            btn.setText("효과 중" if remain else f"새전 {WISHES[key].cost(s):,}")
            btn.setEnabled(not why)
            btn.setToolTip(why)
        cost = s.next_stage_cost
        if cost is None:
            self.up_label.setText("최고 단계예요. 훌륭한 신사가 됐어요!")
            self.up_bar.setRange(0, 1)
            self.up_bar.setValue(1)
            self.up_btn.setText("완성")
            self.up_btn.setEnabled(False)
        else:
            nxt_name, nxt_income, _ = SHRINE_STAGES[s.shrine_level + 1]
            self.up_label.setText(f"다음: {nxt_name} (분당 {nxt_income})   {min(s.saisen, cost):,} / {cost:,} 새전")
            self.up_bar.setRange(0, cost)
            self.up_bar.setValue(min(s.saisen, cost))
            self.up_btn.setText(f"{nxt_name}로 올리기")   # 신사·대신사 모두 받침 없음 → "로"
            self.up_btn.setEnabled(s.saisen >= cost)

        cap_h, rate, _ = SAISEN_BOX[s.box_level]
        nxt = s.next_box_cost
        self.box_label.setText(f"새전함 Lv.{s.box_level} — 꺼져 있는 동안에도 최대 {cap_h}시간, 수입의 {int(rate * 100)}%를 모아요")
        if nxt is None:
            self.box_btn.setText("최고 단계")
            self.box_btn.setEnabled(False)
        else:
            self.box_btn.setText(f"새전함 올리기  {nxt:,}")
            self.box_btn.setEnabled(s.saisen >= nxt)

        if can_draw(s):
            self.omi_label.setText("오늘의 오미쿠지를 뽑아 보세요. 좋은 운세일수록 새전을 많이 받아요.")
            self.omi_btn.setText("오미쿠지 뽑기")
            self.omi_btn.setEnabled(True)
        else:
            self.omi_label.setText("오늘은 이미 뽑았어요. 내일 또 만나요!")
            self.omi_btn.setText("내일 다시")
            self.omi_btn.setEnabled(False)
        self.omi_label.setWordWrap(True)

        for key, (pic, name, goals, out) in self.cards.items():
            met = key in s.unlocked
            if pic.property("met") != met:          # 그림은 만났을 때만 다시 그림
                pic.setPixmap(portrait(key, PORTRAIT, silhouette=not met))
                pic.setProperty("met", met)
            name.setText(CHARACTERS[key].name if met else "???")
            self._role(name, "name" if met else "locked")
            unlock = UNLOCKS[key]
            if not unlock.goals:
                label, bar = goals[0]
                label.setText(f"신사의 주인<br>{_hearts(s, key)}")
                self._role(label, "done")
                bar.hide()
            for (label, bar), goal in zip(goals, unlock.goals):
                if met:
                    label.setText(f"함께 지내는 중<br>{_hearts(s, key)}")
                    self._role(label, "done")
                    bar.hide()
                else:
                    label.setText(goal.label(s))
                    self._role(label, "goal")
                    bar.setValue(int(goal.ratio(s) * 1000))
            if met:                                   # 조건이 여러 개여도 "함께 지내는 중" 한 줄만
                for label, bar in goals[1:]:
                    label.hide()
                    bar.hide()
            out.setVisible(met)
            out.blockSignals(True)
            out.setChecked(key not in s.resting)
            out.blockSignals(False)
        # 센본토리이
        nm, ttl = torii.next_milestone(s), torii.title(s)
        self.torii_label.setText(f"⛩ 센본토리이 {s.torii:,}개 — 분당 새전 +{torii.income(s)}"
                                 + (f"  「{ttl}」" if ttl else "")
                                 + (f"\n2개마다 분당 +1 · 다음 칭호 「{nm[1]}」까지 {nm[0] - s.torii:,}개" if nm
                                    else "\n모든 칭호를 얻었어요!"))
        c1, c10 = torii.cost(s), torii.cost_many(s, 10)
        self.torii_btn.setText(f"봉납  {c1:,}")
        self.torii_btn.setEnabled(s.saisen >= c1)
        self.torii10_btn.setText(f"10개  {c10:,}")
        self.torii10_btn.setEnabled(s.saisen >= c10)

        # 부적
        price = omamori.price(s)
        self.pull1.setText(f"1번 뽑기   새전 {price:,}")
        self.pull1.setEnabled(s.saisen >= price)
        self.pull10.setText(f"10번 뽑기   새전 {price * 9:,}")
        self.pull10.setEnabled(s.saisen >= price * 9)
        self.pity_label.setText(f"10번 뽑기는 한 번 값을 덜 받고 귀함 이상 하나 보장  ·  전설까지 최대 {omamori.PITY - s.gacha_pity}번")
        worn = [omamori.CHARMS[k] for k in s.equipped if k in omamori.CHARMS]
        self.worn_label.setText(("  ·  ".join(f"{c.name.replace(' 부적', '')}: {omamori.effect_text(c, s.omamori.get(c.key, 1))}"
                                              for c in worn) + f"   ({len(worn)}/{omamori.SLOTS})") if worn
                                else f"아직 지닌 부적이 없어요. 아래 부적을 눌러서 지녀요 (0/{omamori.SLOTS})")
        for tile in self.charm_tiles:
            tile.update()
        self.charm_stats.setText(f"모은 부적 {len(s.omamori)}/{len(omamori.CHARMS)}   ·   뽑은 횟수 {s.gacha_pulls:,}")

        # 의상실
        self._refresh_wardrobe()

        # 신사 모양·크기
        for b in self.look_btns:
            b.set_state(b.stage == s.look_stage, b.stage > s.shrine_level)
        for k, b in self.size_btns.items():
            self._role(b, "small" if abs(s.size_scale - k) < 0.01 else "ghost")

        day = daily.cycle_day(s)
        self.stamps.update()
        if not s.attend_streak:
            self.attend_label.setText("하루에 한 번 켜면 도장을 찍어요. 7일째엔 큰 선물!")
        else:
            gift = "오늘 큰 선물을 받았어요!" if day == 7 else f"{7 - day}일 더 오면 큰 선물 (새전 + 오미쿠지 한 번 더)"
            self.attend_label.setText(f"연속 {s.attend_streak}일째 출석 (모두 {s.attend_days}일)   ·   {gift}")
        for i, (card, icon, title, bar, status) in enumerate(self.task_rows):
            if i >= len(s.daily_tasks):
                card.hide()
                continue
            task = s.daily_tasks[i]
            card.show()
            icon.setText(daily.icon(task))
            title.setText(daily.text(task))
            n = min(daily.count(s, task), task["goal"])
            bar.setRange(0, task["goal"])
            bar.setValue(task["goal"] if task["done"] else n)
            if task["done"]:
                status.setText(f"✓ 들어줬어요   새전 +{task['reward']:,}")
                self._role(status, "done")
            else:
                status.setText(f"{n:,} / {task['goal']:,}   ·   새전 +{task['reward']:,}")
                self._role(status, "goal")
        all_done = s.daily_tasks and all(t["done"] for t in s.daily_tasks)
        self.daily_foot.setText(("🎉 오늘의 부탁을 모두 들어줬어요! 내일 또 새 부탁이 와요."
                                 if all_done else f"셋 다 들어주면 보너스 새전 +{daily.all_bonus(s):,}")
                                + f"\n지금까지 들어준 부탁 {s.daily_done}개")

        for key, (pic, name, line1, line2) in self.guest_cards.items():
            visits = s.guest_visits.get(key, 0)
            met = visits > 0
            if pic.property("met") != met:
                pic.setPixmap(portrait(key, PORTRAIT, silhouette=not met))
                pic.setProperty("met", met)
            name.setText(GUESTS[key].name if met else "???")
            self._role(name, "name" if met else "locked")
            hint, about = GUEST_ABOUT[key]
            stage = guest_stage(key)
            if met:
                line1.setText(f"{visits}번 다녀감")
                self._role(line1, "done")
            elif s.shrine_level >= stage:
                line1.setText("언젠가 찾아올 거예요")
                self._role(line1, "goal")
            else:
                line1.setText(f"신사 {stage}단계부터 찾아와요")
                self._role(line1, "goal")
            line2.setText(about if met else hint)
        self.news_boost.setText(f"기사 효과 중: 새전 수입 ×{NEWS_BOOST:g}  ({fmt_left(s.news_until - time.time())})"
                                if news_active(s) else "")
        self.news_boost.setVisible(news_active(s))
        self.news_label.setText("\n".join(f"· {h}" for h in reversed(s.news[-3:]))
                                or "아직 기사가 없어요. 신사가 2단계가 되면 기자가 취재하러 와요.")
        self.guest_stats.setText(f"붙잡은 요정 {s.fairies_caught}번   ·   스이카가 두고 간 새전 {s.suika_saisen:,}")
        hours = s.runtime_sec / 3600
        self.stats.setText(f"모은 새전 {s.saisen_total:,}   ·   쓰다듬기 {s.pats:,}번   ·   함께한 시간 {hours:.1f}시간"
                           f"   ·   붙잡은 새전 도둑 {s.thief_caught}번"
                           + (f"\n장식 보너스 분당 +{s.decor_bonus}" if s.decor_bonus else ""))

        for key, (btn, price) in self.decor_rows.items():
            if key not in s.decor_owned:
                btn.setText(f"구입  {price:,}")
                self._role(btn, "small")
                btn.setEnabled(s.saisen >= price)
            elif key in s.decor_pos:
                btn.setText("치우기")
                self._role(btn, "ghost")
                btn.setEnabled(True)
            else:
                btn.setText("놓기")
                self._role(btn, "small")
                btn.setEnabled(True)

    def _omikuji(self) -> None:
        self.close()             # 오미쿠지 종이를 띄우려고 창은 닫음
        self.on_omikuji()

    def _act(self, name: str, value=None):
        result = self.on_action(name, value) if self.on_action is not None else None
        self.refresh()
        return result

    def _pull(self, n: int) -> None:
        res = self._act("pull", n)
        if res:
            self.pull_strip.set_results(self.state, res)
            self.pull_strip.parentWidget().layout().activate()   # 결과 줄 높이를 먼저 반영
            self._fit_tab(self.tabs.currentIndex())          # 결과 줄만큼 창 높이가 바뀜

    def _refresh_wardrobe(self) -> None:
        s = self.state
        pick = wardrobe.pickup(s)
        self.pickup_label.setText(f"이번 주 픽업: {CHARACTERS[pick].name}의 옷 (확률 {wardrobe.PICKUP_WEIGHT}배)"
                                  if pick else "")
        price = wardrobe.price(s)
        self.wpull1.setText(f"1번 뽑기   새전 {price:,}")
        self.wpull1.setEnabled(s.saisen >= price)
        self.wpull10.setText(f"10번 뽑기   새전 {price * 9:,}")
        self.wpull10.setEnabled(s.saisen >= price * 9)
        self.wpity_label.setText(f"10번 뽑기는 귀함 이상 하나 보장  ·  전설까지 최대 {wardrobe.PITY - s.wardrobe_pity}번"
                                 f"  ·  옷감 {s.cloth:,}")
        if self.w_char not in s.unlocked:
            self.w_char = next((k for k in wardrobe.CHAR_COLORS if k in s.unlocked), "reimu")
        for k, w in self.char_picks.items():
            w.setVisible(k in s.unlocked)
            w.set_state(k == self.w_char, s.skins.get(k))
        for key, b in self.view_btns.items():
            self._role(b, "small" if key == self.w_view else "ghost")
        ch = self.w_char
        worn = s.skins.get(ch)
        skins = [None] + wardrobe.skins_of(ch)
        for i, tile in enumerate(self.skin_tiles):
            tile.setVisible(i < len(skins))
        for tile, skin in zip(self.skin_tiles, skins):
            if skin is None:
                tile.set(("wear", None), "기본 옷", "처음 옷", "N", "worn" if worn is None else "own",
                         pix=portrait(ch, 120, False))
                continue
            it = wardrobe.ITEMS[f"{ch}:{skin}"]
            owned = it.id in s.wardrobe
            cost = wardrobe.CLOTH_COST[it.rarity]
            mode = "worn" if worn == skin else "own" if owned else "trade" if s.cloth >= cost else "locked"
            tile.set(("wear", skin) if owned else ("exchange", it.id), it.name.split(" ", 1)[1],
                     wardrobe.RARITY[it.rarity][0] if owned else f"옷감 {cost}", it.rarity, mode,
                     pix=portrait(ch, 120, False, skin))
        cur = s.effects.get(ch)
        fx_list = [None] + list(wardrobe.EFFECTS)
        for tile, fx in zip(self.fx_tiles, fx_list):
            if fx is None:
                tile.set(("wfx", None), "없음", "이펙트 끄기", "N", "worn" if cur is None else "own")
                continue
            it = wardrobe.ITEMS[f"fx:{fx}"]
            owned = it.id in s.wardrobe
            cost = wardrobe.CLOTH_COST[it.rarity]
            mode = "worn" if cur == fx else "own" if owned else "trade" if s.cloth >= cost else "locked"
            tile.set(("wfx", fx) if owned else ("exchange", it.id), it.name,
                     wardrobe.RARITY[it.rarity][0] if owned else f"옷감 {cost}", it.rarity, mode, icon=fx)
        total = len(wardrobe.pool(s))
        have = len([i for i in s.wardrobe if i in wardrobe.ITEMS])
        self.wstats.setText(f"모은 옷·이펙트 {have}/{total}   ·   뽑은 횟수 {s.wardrobe_pulls:,}")

    def _wview(self, key: str) -> None:
        self.w_view = key
        self.skin_box.setVisible(key == "skin")
        self.fx_box.setVisible(key == "fx")
        self._refresh_wardrobe()
        self.fx_box.parentWidget().layout().activate()
        self._fit_tab(self.tabs.currentIndex())

    def _pick_char(self, key: str) -> None:
        self.w_char = key
        self._refresh_wardrobe()

    def _wclick(self, payload: tuple) -> None:
        what, value = payload
        if what == "exchange":
            self._act("exchange", value)
        else:
            self._act(what, (self.w_char, value))

    def _wpull(self, n: int) -> None:
        res = self._act("wpull", n)
        if res:
            self.wstrip.set_results(res)
            self.wstrip.parentWidget().layout().activate()
            self._fit_tab(self.tabs.currentIndex())

    def _equip(self, key: str) -> None:
        if not self._act("equip", key):
            self.worn_label.setText(f"칸이 꽉 찼어요 ({omamori.SLOTS}/{omamori.SLOTS}). 지닌 부적을 눌러서 먼저 내려놓아요.")

    def _pray(self, key: str) -> None:
        if key == "snack":
            self.close()                 # 모두 모이는 걸 보이게 창은 닫음
        self.on_pray(key)
        if key != "snack":
            self.refresh()

    def _decor_clicked(self, key: str) -> None:
        s = self.state
        action = "buy" if key not in s.decor_owned else ("remove" if key in s.decor_pos else "place")
        self.on_decor(key, action)
        self.refresh()

    def _box(self) -> None:
        self.on_box()
        self.refresh()

    def _upgrade(self) -> None:
        self.on_upgrade()
        self.refresh()

    def _fit_tab(self, index: int) -> None:
        """지금 탭의 페이지만 보이게 하고 창 높이를 내용에 맞춤.

        처음 열 때는 창 아래쪽을 신사 바로 위에 두고, 탭을 바꿀 때는 창 위쪽(탭 막대)을 제자리에 둔다.
        그래야 누른 탭이 마우스 밑에서 도망가지 않는다. 크기와 위치는 한 번에 바꾼다(두 번에 나누면 깜빡임).
        """
        for i, page in enumerate(self.pages):
            page.setVisible(i == index)
        lay = self.layout()
        lay.activate()
        w = self.width()
        h = lay.totalHeightForWidth(w) if lay.hasHeightForWidth() else lay.totalSizeHint().height()
        h = max(h, lay.totalMinimumSize().height())
        if self._anchor is None:
            self.resize(w, h)
            return
        cx, bottom, screen_left, screen_right = self._anchor
        x = min(max(cx - w / 2, screen_left + 8), screen_right - w - 8)
        area = self._area()
        if self._top is None:                           # 처음: 신사 바로 위
            y = bottom - h - 6
        else:                                           # 탭 바꿈: 위쪽 고정, 화면 아래로 넘치면 그만큼만 올림
            y = min(self._top, area.bottom() - h - 4)
        y = max(y, area.top() + 4)
        self._top = y
        self.setGeometry(round(x), round(y), w, h)

    def _area(self):
        cx, bottom = self._anchor[0], self._anchor[1]
        sc = QGuiApplication.screenAt(QPoint(round(cx), round(bottom) - 10)) or QGuiApplication.primaryScreen()
        return sc.availableGeometry()

    def show_above(self, cx: float, bottom: float, screen_left: float, screen_right: float) -> None:
        self._anchor = (cx, bottom, screen_left, screen_right)
        self._top = None
        self._fit_tab(self.tabs.currentIndex())
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
        p.fillRect(QRectF(r.left(), r.top(), r.width(), 4), QColor("#C8102E"))   # 위쪽 빨간 띠
        p.restore()
        p.end()
