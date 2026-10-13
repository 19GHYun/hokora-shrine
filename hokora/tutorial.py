# -*- coding: utf-8 -*-
"""처음 안내: 처음 켠 사람에게 하나씩 해 보게 하는 짧은 말풍선 안내.

해야 할 일을 하면 다음 안내로 넘어가고, 끝나면 새전 100. 말풍선을 누르면 안내를 그만 본다.
설정 창에서 "처음 안내 다시 보기"로 다시 볼 수 있다.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .state import GameState

DONE = 99
REWARD = 100
# (해야 할 일, 안내, 가리킬 곳: "pet" = 첫 친구 / "shrine")
STEPS = [
    ("pat", "👆 레이무를 짧게 클릭해서 쓰다듬어 봐요! 하트가 뜨고 새전이 들어와요", "pet"),
    ("throw", "🤾 캐릭터를 끌었다가 놓으면 던질 수 있어요. 한번 휙 던져 봐요!", "pet"),
    ("panel", "⛩ 신사를 누르면 신사 관리 창이 열려요. 키우기·도감·꾸미기가 다 여기 있어요", "shrine"),
    ("omikuji", "🔮 신사 관리 창 '신사' 탭에서 오늘의 오미쿠지를 뽑아 봐요", "shrine"),
    ("menu", "🖱 캐릭터를 우클릭해 봐요. 말 걸기·선물·원정, 그리고 ⚙ 설정이 있어요", "pet"),
]


def decide(s: GameState) -> None:
    """저장에 안내 기록이 없으면: 이미 하던 사람은 건너뛰고, 처음이면 시작."""
    if s.tutorial < 0:
        s.tutorial = DONE if (s.saisen_total > 0 or len(s.unlocked) > 1) else 0


def current(s: GameState) -> tuple[str, str, str] | None:
    return STEPS[s.tutorial] if 0 <= s.tutorial < len(STEPS) else None


def advance(s: GameState, event: str) -> bool:
    """그 단계의 일을 했으면 다음으로. 안내가 끝났으면 True."""
    step = current(s)
    if step is None or step[0] != event:
        return False
    s.tutorial += 1
    if s.tutorial >= len(STEPS):
        s.tutorial = DONE
        s.add_saisen(REWARD)
        return True
    return False


class Tip(QWidget):
    """안내 말풍선 (꼬리가 아래를 가리킴). 누르면 안내 그만 보기."""

    PAD, TAIL = 12, 9

    def __init__(self, on_skip):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("누르면 안내를 그만 봐요")
        self.on_skip = on_skip
        self.text = ""
        self.f = QFont("Malgun Gothic", 10)
        self.f.setBold(True)
        self.f_small = QFont("Malgun Gothic", 7)
        self._pos = None

    def set_text(self, text: str) -> None:
        self.text = text
        fm = QFontMetricsF(self.f)
        w = min(420.0, fm.horizontalAdvance(text) + self.PAD * 2 + 6)
        h = fm.boundingRect(QRectF(0, 0, w - self.PAD * 2, 999), Qt.TextWordWrap, text).height()
        self.setFixedSize(int(w), int(h + self.PAD * 2 + 16 + self.TAIL))
        self._pos = None
        self.update()

    def point_at(self, cx: float, top: float) -> None:
        pos = (round(cx - self.width() / 2), round(top - self.height()))
        if pos != self._pos:
            self._pos = pos
            self.move(*pos)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.on_skip()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        body = QRectF(2, 2, self.width() - 4, self.height() - self.TAIL - 4)
        path = QPainterPath()
        path.addRoundedRect(body, 12, 12)
        tail = QPainterPath()
        cx = self.width() / 2
        tail.moveTo(cx - 8, body.bottom() - 1)
        tail.lineTo(cx, self.height() - 2)
        tail.lineTo(cx + 8, body.bottom() - 1)
        tail.closeSubpath()
        path = path.united(tail)
        p.setPen(QPen(QColor("#C8102E"), 2))
        p.setBrush(QColor(255, 250, 236, 250))
        p.drawPath(path)
        p.setFont(self.f)
        p.setPen(QColor("#9E1027"))
        p.drawText(body.adjusted(self.PAD, self.PAD - 2, -self.PAD, -16), Qt.TextWordWrap, self.text)
        p.setFont(self.f_small)
        p.setPen(QColor("#A8989C"))
        p.drawText(body.adjusted(self.PAD, 0, -self.PAD, -4), Qt.AlignRight | Qt.AlignBottom, "처음 안내 · 누르면 그만 보기")
        p.end()
