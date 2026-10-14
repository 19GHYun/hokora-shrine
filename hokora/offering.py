# -*- coding: utf-8 -*-
"""공물 올리기 (고양이 수집 Neko Atsume 오마주): 신사 앞에 공물을 올려 두면 그걸 좋아하는 손님이 잘 오고,
먹고 나면 답례품을 두고 간다. 공물은 한 번에 하나, 그 손님이 올 때까지 그대로 있다.

그림은 hokora/sprites/items/offer_<키>.png · gift_<손님>.png 가 있으면 그걸, 없으면 그림 문자로.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .state import GameState

if TYPE_CHECKING:
    from .app import Game

BOOST = 1.6                 # 공물이 있으면 손님이 오는 확률 ×
PICK = 0.7                  # 손님이 올 때 공물을 좋아하는 손님일 확률
EAT_AFTER = 7.0             # 손님이 와서 이만큼 뒤에 공물을 먹음
CUKE_OFFER = 10             # 오이 공물은 가진 오이 10개로도


@dataclass(frozen=True)
class Offering:
    key: str
    icon: str
    name: str
    price: int
    guest: str          # guests.VISITS 의 방문 종류
    hint: str


OFFERINGS = {o.key: o for o in [
    Offering("konpeito", "🍬", "별사탕", 1500, "fairies", "달콤한 걸 좋아하는 장난꾸러기들이"),
    Offering("scoop", "📸", "수상한 사진", 2500, "aya", "특종 냄새를 맡은 기자가"),
    Offering("sake", "🍶", "술병", 3000, "suika", "술이라면 사족을 못 쓰는 오니가"),
    Offering("carrot", "🥕", "당근", 1500, "tewi", "행운의 토끼가"),
    Offering("rose", "🌹", "장미 한 송이", 2500, "koishi", "무의식중에 누군가가"),
    Offering("cucumber", "🥒", "오이", 1500, "nitori", "오이라면 갓파가"),
    Offering("onigiri", "🍙", "주먹밥", 2000, "yuyuko", "늘 배고픈 아가씨가"),
    Offering("score", "🎼", "악보", 2500, "mystia", "노래하는 밤참새가 (밤에만)"),
    Offering("dango", "🍡", "달맞이 경단", 2500, "reisen", "달이 그리운 토끼가"),
    Offering("grimoire", "📕", "마도서", 3500, "patchouli", "책벌레 마법사가"),
    Offering("inari", "🍣", "유부초밥", 3500, "yukari", "식신이 좋아하는 걸 알고 그 주인이"),
]}
GIFTS = {  # 손님 → (그림 문자, 답례품)
    "fairies": ("🌰", "반짝이는 도토리"), "aya": ("📰", "붕붕마루 신문 사인본"), "suika": ("🏺", "이부키 표주박"),
    "tewi": ("🍀", "네잎클로버"), "koishi": ("💖", "코이시의 하트"), "nitori": ("🔧", "갓파 렌치"),
    "yuyuko": ("🌸", "벚꽃 부채"), "mystia": ("🍢", "장어 꼬치"), "reisen": ("💊", "영원정 상비약"),
    "patchouli": ("🔮", "현자의 돌 조각"), "yukari": ("🎀", "틈새 리본"),
}
SHORT = {"fairies": "세 요정", "aya": "아야", "suika": "스이카", "tewi": "테위", "koishi": "코이시", "nitori": "니토리",
         "yuyuko": "유유코", "mystia": "미스티아", "reisen": "레이센", "patchouli": "파츄리", "yukari": "유카리"}
_images: dict[str, QImage | None] = {}


def item_image(name: str) -> QImage | None:
    if name not in _images:
        from .sprites import SPRITE_DIR
        path = SPRITE_DIR / "items" / f"{name}.png"
        img = QImage(str(path)) if path.exists() else QImage()
        if img.isNull() and name == "offer_cucumber":       # 낚시 그림의 오이
            path = SPRITE_DIR / "fish" / "cucumber.png"
            img = QImage(str(path)) if path.exists() else QImage()
        _images[name] = None if img.isNull() else img
    return _images[name]


def draw_item(p: QPainter, rect: QRectF, name: str, emoji: str, dim: bool = False) -> None:
    """공물·답례품 그림 (그림 파일이 없으면 그림 문자). dim 이면 아직 못 받은 것 (흐리게)."""
    p.save()
    if dim:
        p.setOpacity(0.22)
    img = item_image(name)
    if img is not None:
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        k = min(rect.width() / img.width(), rect.height() / img.height())
        w, h = img.width() * k, img.height() * k
        p.drawImage(QRectF(rect.center().x() - w / 2, rect.center().y() - h / 2, w, h), img)
    else:
        f = QFont("Segoe UI Emoji")
        f.setPixelSize(int(rect.height() * 0.78))
        p.setFont(f)
        p.setPen(QColor("#2B1D21"))
        p.drawText(rect, Qt.AlignCenter, emoji)
    p.restore()


def item_pixmap(name: str, emoji: str, size: int, dim: bool = False) -> QPixmap:
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    draw_item(p, QRectF(0, 0, size, size), name, emoji, dim)
    p.end()
    return pm


def wanted(s: GameState) -> str:
    """지금 올린 공물을 좋아하는 손님 (없으면 "")."""
    o = OFFERINGS.get(s.offering)
    return o.guest if o else ""


def place(s: GameState, key: str, use_cucumbers: bool = False) -> bool:
    o = OFFERINGS.get(key)
    if o is None or s.offering:
        return False
    if use_cucumbers:
        if key != "cucumber" or s.cuke_have < CUKE_OFFER:
            return False
        cost = round(s.cuke_paid * CUKE_OFFER / s.cuke_have)
        s.cuke_have -= CUKE_OFFER
        s.cuke_paid -= cost
    else:
        if s.saisen < o.price:
            return False
        s.saisen -= o.price
    s.offering, s.offering_since = key, time.time()
    s.offerings_made += 1
    return True


def receive(s: GameState, guest: str) -> tuple[str, int, int, bool]:
    """손님이 공물을 먹음 → (답례품 이름, 새전, 옷감, 처음 받았나)."""
    s.offering = ""
    first = not s.gifts.get(guest)
    s.gifts[guest] = s.gifts.get(guest, 0) + 1
    saisen = max(300, s.income_per_min * 25)
    cloth = 3 + (10 if first else 0)
    s.add_saisen(saisen)
    s.cloth += cloth
    return GIFTS[guest][1], saisen, cloth, first


class OfferTray(QWidget):
    """신사 앞 공물상 (삼보) 위의 공물. 누르면 공물 창."""

    W, H = 48, 46

    def __init__(self, game: "Game"):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.PointingHandCursor)
        self.game = game
        self.key = ""

    def set_offering(self, key: str) -> None:
        self.key = key
        o = OFFERINGS.get(key)
        if o:
            from .affection import josa
            from .guests import VISITS
            met = self.game.state.guest_visits
            who = SHORT[o.guest] if any(met.get(k) for k in VISITS[o.guest][0]) else "누군가"
            self.setToolTip(f"공물: {o.name} — {josa(who, '을', '를')} 기다리는 중")
        self.update()

    def follow(self, cx: float, ground: float, shrine_w: float) -> None:
        x, y = round(cx + shrine_w * 0.28 - self.W / 2), round(ground - self.H)
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.game.open_offering()

    def paintEvent(self, _e) -> None:
        o = OFFERINGS.get(self.key)
        if o is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        stand = item_image("offer_sanbo")
        if stand is not None:                                     # 그림 받침이 있으면 그걸로
            draw_item(p, QRectF(2, 20, self.W - 4, self.H - 20), "offer_sanbo", "")
            draw_item(p, QRectF(10, 0, self.W - 20, 24), f"offer_{o.key}", o.icon)
            p.end()
            return
        wood, dark = QColor("#E2BE86"), QColor("#A77A44")
        p.setPen(QPen(dark, 1.2))
        p.setBrush(wood)
        base = QPainterPath()                                    # 받침 (삼보)
        base.moveTo(12, self.H - 1)
        base.lineTo(self.W - 12, self.H - 1)
        base.lineTo(self.W - 9, 28)
        base.lineTo(9, 28)
        base.closeSubpath()
        p.drawPath(base)
        p.setBrush(dark.darker(110))
        p.drawEllipse(QRectF(self.W / 2 - 4, 33, 8, 7))           # 받침 구멍
        p.setBrush(wood.lighter(108))
        p.drawRect(QRectF(4, 24, self.W - 8, 5))                  # 쟁반
        draw_item(p, QRectF(10, 2, self.W - 20, 24), f"offer_{o.key}", o.icon)
        p.end()


class GiftCard(QWidget):
    """답례품 카드. 누르면 닫히고 20초 뒤 저절로 닫힌다."""

    W, H = 320, 150

    def __init__(self, guest: str, offering_key: str, gift: str, saisen: int, cloth: int, first: bool):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.W, self.H)
        self.guest, self.gift, self.saisen, self.cloth, self.first = guest, gift, saisen, cloth, first
        self.offer = OFFERINGS[offering_key]

    def show_above(self, cx: float, bottom: float) -> None:
        self.move(round(cx - self.W / 2), round(bottom - self.H - 8))
        self.show()
        QTimer.singleShot(20_000, self.close)

    def mousePressEvent(self, _e) -> None:
        self.close()

    def paintEvent(self, _e) -> None:
        from .affection import josa
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        p.setPen(QPen(QColor(200, 16, 46, 120), 1.2))
        p.setBrush(QColor(255, 250, 244, 250))
        p.drawPath(path)
        p.save()
        p.setClipPath(path)
        p.fillRect(QRectF(r.left(), r.top(), r.width(), 4), QColor("#C8102E"))
        p.restore()
        f = QFont("Malgun Gothic", 12)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#B3122C"))
        p.drawText(QRectF(18, 12, self.W - 36, 24), Qt.AlignLeft | Qt.AlignVCenter,
                   "🎁 답례품" + ("  (처음 받았어요!)" if self.first else ""))
        draw_item(p, QRectF(18, 46, 62, 62), f"gift_{self.guest}", GIFTS[self.guest][0])
        f2 = QFont("Malgun Gothic", 10)
        p.setFont(f2)
        p.setPen(QColor("#3A2A2E"))
        who = SHORT[self.guest]
        text = (f"{josa(who, '이', '가')} {josa(self.offer.name, '을', '를')} 먹고\n"
                f"「{self.gift}」{'을' if _final(self.gift) else '를'} 두고 갔어요!")
        p.drawText(QRectF(92, 44, self.W - 106, 50), Qt.AlignLeft | Qt.AlignVCenter, text)
        f3 = QFont("Malgun Gothic", 11)
        f3.setBold(True)
        p.setFont(f3)
        p.setPen(QColor("#B8860B"))
        p.drawText(QRectF(92, 98, self.W - 106, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   f"새전 +{self.saisen:,}  ·  옷감 +{self.cloth}")
        p.end()


def _final(word: str) -> bool:
    code = ord(word[-1]) - 0xAC00
    return 0 <= code < 11172 and code % 28 != 0


class OfferingWindow(QWidget):
    """공물 창: 공물 고르기 + 답례품 모음."""

    def __init__(self, game: "Game"):
        super().__init__(None, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        from .panel import STYLE
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("panel")
        self.setStyleSheet(STYLE)
        self.game = game
        self.setFixedWidth(560)
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(18, 14, 18, 16)
        self.v.setSpacing(7)
        self.build()

    def build(self) -> None:
        from .affection import josa
        from .guests import VISITS, available
        v = self.v
        while v.count():
            item = v.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                _clear(item.layout())
        s = self.game.state
        v.addWidget(QLabel("🍙  공물 올리기", objectName="title"))
        tip = QLabel("신사 앞에 공물을 올려 두면 그걸 좋아하는 손님이 잘 와요. 손님이 먹고 나면 답례품을 두고 가요. "
                     "공물은 한 번에 하나, 그 손님이 올 때까지 그대로 있어요.", objectName="goal")
        tip.setWordWrap(True)
        v.addWidget(tip)
        cur = OFFERINGS.get(s.offering)
        if cur:
            row = QHBoxLayout()
            ic = QLabel()
            ic.setPixmap(item_pixmap(f"offer_{cur.key}", cur.icon, 30))
            row.addWidget(ic)
            met = any(s.guest_visits.get(k) for k in VISITS[cur.guest][0])
            row.addWidget(QLabel(f"지금 올린 공물: {cur.name}  —  "
                                 f"{josa(SHORT[cur.guest] if met else '누군가', '을', '를')} 기다리는 중…",
                                 objectName="name"), 1)
            b = QPushButton("치우기", objectName="ghost")
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip("공물을 치워요 (새전은 돌려받지 못해요)")
            b.clicked.connect(self._clear_offering)
            row.addWidget(b)
            v.addLayout(row)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        avail = set(available(s))
        for i, o in enumerate(OFFERINGS.values()):
            cell = QWidget(objectName="card")
            h = QHBoxLayout(cell)
            h.setContentsMargins(8, 5, 8, 5)
            h.setSpacing(6)
            ic = QLabel()
            ic.setPixmap(item_pixmap(f"offer_{o.key}", o.icon, 30))
            h.addWidget(ic)
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(QLabel(o.name, objectName="name"))
            met = any(s.guest_visits.get(k) for k in VISITS[o.guest][0])
            who = SHORT[o.guest] if met else "처음 보는 손님"
            stage = VISITS[o.guest][1]
            note = (f"{o.hint}" if met else "누가 좋아할까?")
            if s.shrine_level < stage:
                note = f"신사 {stage}단계부터 오는 손님용"
            hint = QLabel(f"{note}\n→ {who}", objectName="goal")
            col.addWidget(hint)
            h.addLayout(col, 1)
            btns = QVBoxLayout()
            btns.setSpacing(2)
            b = QPushButton(f"{o.price:,}", objectName="small")
            b.setCursor(Qt.PointingHandCursor)
            b.setEnabled(not s.offering and s.saisen >= o.price)
            b.setToolTip("새전으로 올리기" + ("" if o.guest in avail else "  (지금은 이 손님이 오지 않아요)"))
            b.clicked.connect(lambda _=False, k=o.key: self._place(k, False))
            btns.addWidget(b)
            if o.key == "cucumber" and s.cuke_have >= CUKE_OFFER:
                b2 = QPushButton(f"오이 {CUKE_OFFER}개", objectName="ghost")
                b2.setCursor(Qt.PointingHandCursor)
                b2.setEnabled(not s.offering)
                b2.clicked.connect(lambda _=False: self._place("cucumber", True))
                btns.addWidget(b2)
            h.addLayout(btns)
            grid.addWidget(cell, i // 2, i % 2)
        v.addLayout(grid)
        v.addWidget(QLabel(f"🎁 답례품  {sum(1 for g in GIFTS if s.gifts.get(g))} / {len(GIFTS)}", objectName="section"))
        row = QHBoxLayout()
        row.setSpacing(4)
        for guest, (emoji, name) in GIFTS.items():
            n = s.gifts.get(guest, 0)
            lab = QLabel()
            lab.setPixmap(item_pixmap(f"gift_{guest}", emoji, 34, dim=not n))
            lab.setToolTip(f"{name} ×{n}  ({SHORT[guest]})" if n else "??? — 공물을 올려 손님을 불러 봐요")
            row.addWidget(lab)
        row.addStretch(1)
        v.addLayout(row)
        self.adjustSize()

    def _place(self, key: str, cukes: bool) -> None:
        if self.game.place_offering(key, cukes):
            self.build()

    def _clear_offering(self) -> None:
        self.game.clear_offering()
        self.build()

    def show_near(self, pos: QPoint) -> None:
        self.adjustSize()
        sc = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        area = sc.availableGeometry()
        x = min(max(pos.x() - self.width() // 2, area.left() + 8), area.right() - self.width() - 8)
        y = min(max(pos.y() - self.height() - 10, area.top() + 8), area.bottom() - self.height() - 8)
        self.move(x, y)
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
        p.fillRect(QRectF(r.left(), r.top(), r.width(), 4), QColor("#C8102E"))
        p.restore()
        p.end()


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear(item.layout())
