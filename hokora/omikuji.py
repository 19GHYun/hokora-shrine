# -*- coding: utf-8 -*-
"""오미쿠지: 하루 한 번 뽑는 운세. 좋은 운세일수록 새전을 더 받는다."""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .render import CHARACTERS
from .state import GameState


@dataclass(frozen=True)
class Fortune:
    rank: str
    weight: int          # 뽑힐 비율
    reward: int          # 새전 (신사 단계만큼 곱함)
    lines: tuple[str, ...]
    good: bool           # 캐릭터들이 기뻐할지(True) 놀랄지(False)


FORTUNES = [
    Fortune("대길", 5, 100, ("하늘을 나는 듯한 하루!\n마리사도 부러워할 운세.",
                            "새전함이 넘칠 조짐.\n오늘은 뭘 해도 잘 풀려요."), True),
    Fortune("중길", 15, 50, ("차근차근 쌓으면\n큰 복이 돌아와요.",
                            "뜻밖의 손님이\n좋은 소식을 가져올지도."), True),
    Fortune("소길", 25, 30, ("작은 행운이 곁에.\n따뜻한 차 한 잔 어때요?",
                            "서두르지 않으면\n일이 순조로워요."), True),
    Fortune("길", 30, 20, ("평온한 하루.\n신사 마당 쓸기 좋은 날.",
                          "무난하게 흘러가요.\n쉬어 가는 것도 복."), True),
    Fortune("말길", 15, 10, ("복은 늦게 와요.\n기다리면 반드시 와요.",
                            "지금은 준비하는 때.\n내일을 기대해요."), True),
    Fortune("흉", 10, 5, ("조심조심…\n새전을 더 넣으면 운이 바뀔지도?",
                         "치르노의 장난에 주의.\n그래도 내일은 좋아져요."), False),
]
LUCKY_ITEMS = ["대나무 빗자루", "새전함", "빨간 리본", "마법 버섯", "은 회중시계", "얼음 조각",
               "따뜻한 녹차", "경단", "부적", "벚꽃잎"]


@dataclass
class Draw:
    fortune: Fortune
    line: str
    reward: int
    lucky_item: str
    lucky_friend: str


def can_draw(s: GameState, today: date | None = None) -> bool:
    return s.omikuji_date != (today or date.today()).isoformat()


def draw(s: GameState, rng: random.Random | None = None, today: date | None = None) -> Draw:
    """오늘의 운세를 뽑고 새전을 준다 (하루 한 번 — 이미 뽑았으면 호출하지 말 것)."""
    rng = rng or random.Random()
    fortune = rng.choices(FORTUNES, weights=[f.weight for f in FORTUNES])[0]
    reward = fortune.reward * s.shrine_level
    s.add_saisen(reward)
    s.omikuji_date = (today or date.today()).isoformat()
    s.omikuji_count += 1
    friend = CHARACTERS[rng.choice(s.unlocked)].name
    return Draw(fortune, rng.choice(fortune.lines), reward, rng.choice(LUCKY_ITEMS), friend)


class FortuneSlip(QWidget):
    """세로로 긴 오미쿠지 종이. 누르거나 바깥을 누르면 닫힌다."""

    W, H = 190, 330

    def __init__(self, result: Draw):
        super().__init__(None, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFixedSize(self.W, self.H)
        self.result = result

    def show_above(self, cx: float, bottom: float) -> None:
        self.move(QPoint(round(cx - self.W / 2), round(bottom - self.H - 6)))
        self.show()

    def mousePressEvent(self, _e) -> None:
        self.close()

    def paintEvent(self, _e) -> None:
        r = self.result
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        paper = QRectF(6, 6, self.W - 12, self.H - 12)
        path = QPainterPath()
        path.addRoundedRect(paper, 6, 6)
        p.setPen(QPen(QColor(120, 70, 60, 150), 1.2))
        p.setBrush(QColor("#FFFBF3"))
        p.drawPath(path)
        inner = paper.adjusted(10, 10, -10, -10)
        p.setPen(QPen(QColor("#C8102E"), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRect(inner)

        def text(rect: QRectF, s: str, size: float, color: str, bold: bool = False) -> None:
            f = QFont("Malgun Gothic")
            f.setPointSizeF(size)
            f.setBold(bold)
            p.setFont(f)
            p.setPen(QColor(color))
            p.drawText(rect, Qt.AlignHCenter | Qt.AlignVCenter | Qt.TextWordWrap, s)

        x, w = inner.left(), inner.width()
        text(QRectF(x, inner.top() + 6, w, 20), "御 神 籤", 10, "#9E1027", True)
        p.setPen(QPen(QColor(200, 16, 46, 90), 1))
        p.drawLine(int(x + 12), int(inner.top() + 30), int(x + w - 12), int(inner.top() + 30))
        text(QRectF(x, inner.top() + 34, w, 62), r.fortune.rank, 30, "#C8102E", True)
        text(QRectF(x + 8, inner.top() + 100, w - 16, 70), r.line, 9.5, "#2B1D21")
        p.setPen(QPen(QColor(200, 16, 46, 90), 1))
        p.drawLine(int(x + 12), int(inner.top() + 178), int(x + w - 12), int(inner.top() + 178))
        text(QRectF(x, inner.top() + 184, w, 20), f"행운의 물건 · {r.lucky_item}", 8.5, "#5A464B")
        text(QRectF(x, inner.top() + 204, w, 20), f"행운의 친구 · {r.lucky_friend}", 8.5, "#5A464B")
        text(QRectF(x, inner.bottom() - 52, w, 24), f"새전 +{r.reward:,}", 13, "#B8860B", True)
        text(QRectF(x, inner.bottom() - 26, w, 20), "눌러서 닫기", 7.5, "#A8959A")
        p.end()
