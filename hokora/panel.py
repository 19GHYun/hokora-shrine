# -*- coding: utf-8 -*-
"""신사를 누르면 뜨는 창: 신사 키우기 + 도감. 바깥을 누르면 닫힌다."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QVBoxLayout, QWidget)

from .progress import UNLOCKS
from .render import CHARACTERS, Pose, draw_character
from .sprites import image_sprites
from .state import SHRINE_STAGES, GameState

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


class ShrinePanel(QWidget):
    def __init__(self, state: GameState, on_upgrade: Callable[[], None]):
        super().__init__(None, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("panel")
        self.setStyleSheet(STYLE)
        self.state = state
        self.on_upgrade = on_upgrade
        self.setFixedWidth(490)

        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 16)
        v.setSpacing(8)

        # ── 신사 ──
        self.title = QLabel(objectName="title")
        self.sub = QLabel(objectName="sub")
        v.addWidget(self.title)
        v.addWidget(self.sub)
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
        v.addLayout(up)

        # ── 도감 ──
        v.addWidget(QLabel("도감", objectName="section"))
        grid = QGridLayout()
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
        v.addLayout(grid)

        self.stats = QLabel(objectName="sub")
        v.addWidget(self.stats)
        self.refresh()
        self._timer = QTimer(self, timeout=self.refresh, interval=1000)   # 열려 있는 동안 새전 등 갱신
        self._timer.start()

    # ── 내용 ──
    def refresh(self) -> None:
        s = self.state
        self.title.setText(f"⛩  {s.stage_name}  ({s.shrine_level}단계)")
        self.sub.setText(f"새전 {s.saisen:,}   ·   분당 새전 {s.income_per_min}")
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
        self.stats.setText(f"모은 새전 {s.saisen_total:,}   ·   쓰다듬기 {s.pats:,}번   ·   함께한 시간 {hours:.1f}시간")

    def _upgrade(self) -> None:
        self.on_upgrade()
        self.refresh()

    def show_above(self, cx: float, bottom: float, screen_left: float, screen_right: float) -> None:
        self.adjustSize()
        x = min(max(cx - self.width() / 2, screen_left + 8), screen_right - self.width() - 8)
        self.move(QPoint(round(x), round(bottom - self.height() - 6)))
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
