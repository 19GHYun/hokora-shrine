# -*- coding: utf-8 -*-
"""설정 창: 우클릭 메뉴에 쌓여 있던 켜고 끄기를 한곳에. 화면 붐빔 조절·저장 백업도 여기."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from . import winutil
from .guests import BELL_PRICE
from .panel import STYLE

if TYPE_CHECKING:
    from .app import Game

CROWD = ((0, "전부"), (3, "3명"), (5, "5명"), (7, "7명"))
SIZES = ((1.0, "보통"), (0.85, "작게"), (0.7, "아주 작게"))


class SettingsWindow(QWidget):
    def __init__(self, game: "Game"):
        super().__init__(None, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("panel")
        self.setStyleSheet(STYLE)
        self.game = game
        s = game.state
        self.setFixedWidth(430)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 16)
        v.setSpacing(7)
        v.addWidget(QLabel("⚙  설정", objectName="title"))

        def check(text: str, on: bool, fn, tip: str = "") -> QCheckBox:
            c = QCheckBox(text)
            c.setChecked(on)
            c.setCursor(Qt.PointingHandCursor)
            c.setToolTip(tip)
            c.toggled.connect(fn)
            v.addWidget(c)
            return c

        v.addWidget(QLabel("놀이", objectName="section"))
        check("마우스 커서에도 올라타기", s.cursor_play, game.set_cursor_play, "커서를 가만히 두면 폴짝 올라타요")
        check("창 위에도 올라가기", s.climb, game.set_climb, "열려 있는 창 윗변으로 점프해요")
        check("스펠카드 컷인", s.cutin, game.set_cutin, "특기를 쓸 때 스펠카드 이름이 지나가요")
        check("시계 친구  (정각마다 팻말로 시간을 알려 줘요)", s.clock_friend, game.set_clock_friend)
        check("PC 상태에 반응  (배터리·CPU·늦은 밤·휴지통)", s.pc_react, game.set_pc_react,
              "읽기만 하고 아무것도 바꾸지 않아요 (휴지통도 알려 주기만)")

        v.addWidget(QLabel("보기", objectName="section"))
        check("계절·날씨 연출  (벚꽃잎·단풍·눈·반딧불·비·안개)", s.season_fx, game.set_season_fx)
        check("신사 옆에 장식 보이기  (꺼도 효과는 그대로)", s.show_decor, game.set_show_decor)
        check("센본토리이 보이기  (꺼도 분당 새전은 그대로)", s.show_torii, game.set_show_torii)
        check("전체화면에서도 돌아다니기  (영상·브라우저 전체화면)", s.fullscreen_show, game.set_fullscreen_show,
              "끄면 전체화면일 때 모두 숨어요. 전용 전체화면 게임에서는 켜도 숨어요 (게임 방해 방지)")
        self.size_btns = self._choices(v, "크기", SIZES, s.size_scale, lambda k: game.on_action("scale", k))
        self.crowd_btns = self._choices(v, "동시에 나와 있는 친구", CROWD, s.max_out, game.set_max_out)
        crowd_tip = QLabel("정하면 나머지 친구는 신사에서 쉬다가 10분마다 번갈아 나와요.", objectName="goal")
        crowd_tip.setWordWrap(True)
        v.addWidget(crowd_tip)

        v.addWidget(QLabel("🔔 손님 방울", objectName="section"))
        self.bell_check = check("손님이 오면 알려 주기  (Windows 알림 + 딸랑~)", s.guest_bell_on, game.set_guest_bell,
                                "다른 일을 하고 있어도 손님을 놓치지 않아요")
        self.bell_buy = QWidget()
        brow = QHBoxLayout(self.bell_buy)
        brow.setContentsMargins(0, 0, 0, 0)
        btip = QLabel("손님이 찾아오면 Windows 알림으로 알려 주는 방울이에요.", objectName="goal")
        btip.setWordWrap(True)
        self.bell_btn = QPushButton(f"달기  {BELL_PRICE:,}", objectName="upgrade")
        self.bell_btn.setCursor(Qt.PointingHandCursor)
        self.bell_btn.setEnabled(s.saisen >= BELL_PRICE)
        self.bell_btn.setToolTip(f"새전 {BELL_PRICE:,}" + ("" if s.saisen >= BELL_PRICE else " — 새전이 모자라요"))
        self.bell_btn.clicked.connect(self._buy_bell)
        brow.addWidget(btip, 1)
        brow.addWidget(self.bell_btn)
        v.addWidget(self.bell_buy)
        self.bell_check.setVisible(s.guest_bell)
        self.bell_buy.setVisible(not s.guest_bell)

        v.addWidget(QLabel("시스템", objectName="section"))
        if winutil.IS_WIN:
            check("Windows 시작 시 자동 실행", winutil.get_autostart() is not None, game.set_autostart)
        row = QHBoxLayout()
        for text, fn in (("📖 처음 안내 다시 보기", self._tutorial), ("📁 데이터 폴더 열기", game.open_data_dir)):
            b = QPushButton(text, objectName="ghost")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)

        v.addWidget(QLabel("💾 저장 백업", objectName="section"))
        tip = QLabel("하루에 한 번 저절로 백업해요 (최근 7개). 되돌리면 그 시점으로 돌아가고 Hokora 가 다시 켜져요.",
                     objectName="goal")
        tip.setWordWrap(True)
        v.addWidget(tip)
        now_btn = QPushButton("지금 백업하기", objectName="small")
        now_btn.setCursor(Qt.PointingHandCursor)
        now_btn.clicked.connect(self._backup_now)
        v.addWidget(now_btn, 0, Qt.AlignLeft)
        self.backup_box = QVBoxLayout()
        self.backup_box.setSpacing(3)
        v.addLayout(self.backup_box)
        self._fill_backups()

    def _choices(self, v, label: str, options, current, fn) -> dict:
        row = QHBoxLayout()
        row.addWidget(QLabel(label, objectName="goal"))
        btns = {}
        for value, text in options:
            b = QPushButton(text, objectName="small" if abs(float(value) - float(current)) < 0.01 else "ghost")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, value=value, btns=btns, fn=fn: self._pick(btns, value, fn))
            row.addWidget(b)
            btns[value] = b
        row.addStretch(1)
        v.addLayout(row)
        return btns

    @staticmethod
    def _pick(btns: dict, value, fn) -> None:
        fn(value)
        for k, b in btns.items():
            b.setObjectName("small" if k == value else "ghost")
            b.style().unpolish(b)
            b.style().polish(b)

    def _buy_bell(self) -> None:
        if self.game.buy_guest_bell():
            self.bell_buy.hide()
            self.bell_check.setChecked(True)
            self.bell_check.show()
            self.adjustSize()

    def _tutorial(self) -> None:
        self.close()
        self.game.restart_tutorial()

    def _backup_now(self) -> None:
        self.game.save()
        self.game.store.backup(force=True)
        self._fill_backups()

    def _fill_backups(self) -> None:
        while self.backup_box.count():
            item = self.backup_box.takeAt(0)
            if item.layout():
                while item.layout().count():
                    w = item.layout().takeAt(0).widget()
                    if w:
                        w.deleteLater()
            elif item.widget():
                item.widget().deleteLater()
        rows = self.game.store.backups()
        if not rows:
            self.backup_box.addWidget(QLabel("아직 백업이 없어요.", objectName="sub"))
        for path, info in rows:
            row = QHBoxLayout()
            when = datetime.fromtimestamp(path.stat().st_mtime)
            lab = QLabel(f"{when:%m월 %d일 %H:%M}   ·   새전 {info.get('saisen', 0):,}   ·   "
                         f"{info.get('shrine_level', 1)}단계   ·   친구 {len(info.get('unlocked', []))}명", objectName="goal")
            b = QPushButton("되돌리기", objectName="ghost")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, path=path: self._restore(path))
            row.addWidget(lab, 1)
            row.addWidget(b)
            self.backup_box.addLayout(row)
        self.adjustSize()

    def _restore(self, path) -> None:
        ok = QMessageBox.question(None, "Hokora 백업 되돌리기",
                                  f"{path.name} 시점으로 되돌릴까요?\n지금 진행 상황은 따로 백업해 두고, Hokora 가 다시 켜져요.")
        if ok == QMessageBox.Yes:
            self.close()
            self.game.restore_backup(path)

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
