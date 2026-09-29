# -*- coding: utf-8 -*-
"""신사를 누르면 뜨는 창: 신사 키우기 + 도감. 바깥을 누르면 닫힌다."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)

from .decor import decor_image
from .omikuji import can_draw
from .prayer import WISHES, blocked, fmt_left, income_multiplier, left
from .progress import UNLOCKS
from .render import CHARACTERS, Pose, draw_character
from .sprites import image_sprites
from .state import DECOR, SHRINE_STAGES, GameState

PORTRAIT = 76

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
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; color: #8C7479; padding: 6px 16px; margin-right: 4px;
               font-family: 'Malgun Gothic'; font-size: 12px; font-weight: 700;
               border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #B3122C; border-bottom: 2px solid #C8102E; }
QTabBar::tab:hover { color: #9E1027; }
"""


def portrait(key: str, size: int, silhouette: bool) -> QPixmap:
    """도감용 얼굴(서 있는 모습). 못 만난 캐릭터는 검은 실루엣."""
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    sprites = image_sprites(key)
    if sprites is not None:
        img, anchor = sprites.images[sprites.sequence("idle")[0]]
        s = size * 0.95 / img.height()
        p.drawImage(QRectF((size - img.width() * s) / 2, size - img.height() * s, img.width() * s,
                           img.height() * s), img)
    else:
        draw_character(p, CHARACTERS[key], Pose(kind="idle", t=0.3), QRectF(0, 0, size, size))
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


class ShrinePanel(QWidget):
    def __init__(self, state: GameState, on_upgrade: Callable[[], None], on_omikuji: Callable[[], None],
                 on_decor: Callable[[str, str], None], on_pray: Callable[[str], None], tab: int = 0):
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
        self.setFixedWidth(490)

        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 16)
        v.setSpacing(8)

        # ── 신사 ──
        self.title = QLabel(objectName="title")
        self.sub = QLabel(objectName="sub")
        v.addWidget(self.title)
        v.addWidget(self.sub)
        self.tabs = QTabWidget()
        v.addWidget(self.tabs)
        page1, page2, page3, page4 = QWidget(), QWidget(), QWidget(), QWidget()
        p1, p3, p4 = QVBoxLayout(page1), QVBoxLayout(page3), QVBoxLayout(page4)
        for lay in (p1, p3, p4):
            lay.setContentsMargins(0, 10, 0, 0)
            lay.setSpacing(10)
        self.tabs.addTab(page1, "신사")
        self.tabs.addTab(page4, "참배")
        self.tabs.addTab(page2, "도감")
        self.tabs.addTab(page3, "꾸미기")
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
        p1.addStretch(1)

        # ── 도감 ──
        grid = QGridLayout(page2)
        grid.setContentsMargins(0, 10, 0, 0)
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
            info.addStretch(1)
            h.addWidget(pic)
            h.addLayout(info, 1)
            grid.addWidget(card, i // 2, i % 2)
            self.cards[key] = (pic, name, goals)

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
        p4.addStretch(1)

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
        p3.addStretch(1)
        self._anchor = None
        self.tabs.currentChanged.connect(self._fit_tab)
        self.tabs.setCurrentIndex(tab)
        self._fit_tab(self.tabs.currentIndex())
        self.refresh()
        self._timer = QTimer(self, timeout=self.refresh, interval=1000)   # 열려 있는 동안 새전 등 갱신
        self._timer.start()

    # ── 내용 ──
    def refresh(self) -> None:
        s = self.state
        self.title.setText(f"⛩  {s.stage_name}  ({s.shrine_level}단계)")
        boost = income_multiplier(s)
        self.sub.setText(f"새전 {s.saisen:,}   ·   분당 새전 {s.income_per_min * boost}"
                         + ("  (번영 기원 ×2)" if boost > 1 else ""))
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

        if can_draw(s):
            self.omi_label.setText("오늘의 오미쿠지를 뽑아 보세요. 좋은 운세일수록 새전을 많이 받아요.")
            self.omi_btn.setText("오미쿠지 뽑기")
            self.omi_btn.setEnabled(True)
        else:
            self.omi_label.setText("오늘은 이미 뽑았어요. 내일 또 만나요!")
            self.omi_btn.setText("내일 다시")
            self.omi_btn.setEnabled(False)
        self.omi_label.setWordWrap(True)

        for key, (pic, name, goals) in self.cards.items():
            met = key in s.unlocked
            if pic.property("met") != met:          # 그림은 만났을 때만 다시 그림
                pic.setPixmap(portrait(key, PORTRAIT, silhouette=not met))
                pic.setProperty("met", met)
            name.setText(CHARACTERS[key].name if met else "???")
            name.setObjectName("name" if met else "locked")
            name.style().unpolish(name)
            name.style().polish(name)
            unlock = UNLOCKS[key]
            if not unlock.goals:
                label, bar = goals[0]
                label.setText("신사의 주인")
                label.setObjectName("done")
                label.style().unpolish(label)
                label.style().polish(label)
                bar.hide()
            for (label, bar), goal in zip(goals, unlock.goals):
                if met:
                    label.setText("함께 지내는 중")
                    label.setObjectName("done")
                    bar.hide()
                else:
                    label.setText(goal.label(s))
                    bar.setValue(int(goal.ratio(s) * 1000))
                label.style().unpolish(label)
                label.style().polish(label)
            if met:                                   # 조건이 여러 개여도 "함께 지내는 중" 한 줄만
                for label, bar in goals[1:]:
                    label.hide()
                    bar.hide()
        hours = s.runtime_sec / 3600
        self.stats.setText(f"모은 새전 {s.saisen_total:,}   ·   쓰다듬기 {s.pats:,}번   ·   함께한 시간 {hours:.1f}시간"
                           f"   ·   붙잡은 새전 도둑 {s.thief_caught}번"
                           + (f"\n장식 보너스 분당 +{s.decor_bonus}" if s.decor_bonus else ""))

        for key, (btn, price) in self.decor_rows.items():
            if key not in s.decor_owned:
                btn.setText(f"구입  {price:,}")
                btn.setObjectName("small")
                btn.setEnabled(s.saisen >= price)
            elif key in s.decor_pos:
                btn.setText("치우기")
                btn.setObjectName("ghost")
                btn.setEnabled(True)
            else:
                btn.setText("놓기")
                btn.setObjectName("small")
                btn.setEnabled(True)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _omikuji(self) -> None:
        self.close()             # 오미쿠지 종이를 띄우려고 창은 닫음
        self.on_omikuji()

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

    def _upgrade(self) -> None:
        self.on_upgrade()
        self.refresh()

    def _fit_tab(self, index: int) -> None:
        """창 높이를 지금 탭 내용에 맞춤 (QTabWidget 은 늘 가장 긴 탭 높이를 쓰므로 직접 계산).
        아래쪽은 신사 위에 고정."""
        page = self.tabs.widget(index)
        lay = page.layout()
        width = self.width() - 36
        ph = lay.heightForWidth(width) if lay.hasHeightForWidth() else page.sizeHint().height()
        ph = max(ph, page.minimumSizeHint().height()) + 14   # 줄바꿈된 글자가 잘리지 않게 여유
        chrome = self.sizeHint().height() - self.tabs.sizeHint().height()
        self.setFixedHeight(chrome + self.tabs.tabBar().sizeHint().height() + ph + 8)
        if self._anchor is not None:
            self._place(*self._anchor)

    def _place(self, cx: float, bottom: float, screen_left: float, screen_right: float) -> None:
        x = min(max(cx - self.width() / 2, screen_left + 8), screen_right - self.width() - 8)
        self.move(QPoint(round(x), round(bottom - self.height() - 6)))

    def show_above(self, cx: float, bottom: float, screen_left: float, screen_right: float) -> None:
        self._anchor = (cx, bottom, screen_left, screen_right)
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
