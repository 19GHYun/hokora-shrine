# -*- coding: utf-8 -*-
"""니토리의 오이 시세 (동물의 숲 무 주식 오마주).

일요일·월요일 오전에 니토리에게서 오이를 사 두고, 월요일 오후부터 토요일까지 하루 두 번(오전·오후)
바뀌는 시세에 판다. 다음 일요일이 되면 남은 오이는 시든다. 그 주의 시세 모양(패턴)은 주마다 하나:
들쭉날쭉 / 대폭등 / 계속 내림 / 소폭등.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .state import GameState

if TYPE_CHECKING:
    from .app import Game

MAX_HAVE = 3000
BUY_STEPS = (10, 100)
SLOTS = 12                            # 월 오전 … 토 오후
SLOT_NAMES = [f"{d} {h}" for d in "월화수목금토" for h in ("오전", "오후")]
PATTERNS = {0: "들쭉날쭉", 1: "대폭등", 2: "계속 내림", 3: "소폭등"}
PATTERN_WEIGHTS = (35, 25, 15, 25)
HINTS = {  # 월요일에 니토리가 하는 말 (70% 는 이 주의 패턴, 30% 는 아무거나)
    0: "글쎄, 오르락내리락 하겠는걸?",
    1: "이번 주는 왠지 느낌이 엄청 좋아!",
    2: "음… 이번 주는 영 별로일지도.",
    3: "조금은 오를 것 같은데~",
}


def week_of(d: date) -> date:
    """그 주의 일요일 (주는 일요일부터)."""
    return d - timedelta(days=(d.weekday() + 1) % 7)


def slot_of(now: datetime) -> int:
    """지금 시세 칸 (월 오전 = 0 … 토 오후 = 11). 일요일은 -1."""
    if now.weekday() == 6:
        return -1
    return now.weekday() * 2 + (1 if now.hour >= 12 else 0)


def can_buy(now: datetime) -> bool:
    return slot_of(now) <= 0                    # 일요일 · 월요일 오전


def can_sell(now: datetime) -> bool:
    return slot_of(now) >= 1                    # 월요일 오후 ~ 토요일


def make_prices(seed: int, base: int) -> tuple[int, list[int]]:
    """(패턴, 12칸 시세)."""
    rng = random.Random(seed)
    pat = rng.choices(range(4), weights=PATTERN_WEIGHTS)[0]
    m: list[float] = []

    def falling(n: int, start: float) -> None:
        r = start
        for _ in range(n):
            m.append(r)
            r -= rng.uniform(0.03, 0.05)
    if pat == 0:
        while len(m) < SLOTS:
            m.extend(rng.uniform(0.9, 1.4) for _ in range(rng.randint(1, 3)))
            falling(rng.randint(2, 3), rng.uniform(0.6, 0.8))
    elif pat == 1:
        start = rng.randint(1, 7)
        falling(start, rng.uniform(0.85, 0.9))
        m += [rng.uniform(0.9, 1.4), rng.uniform(1.4, 2.0), rng.uniform(2.0, 6.0),
              rng.uniform(1.4, 2.0), rng.uniform(0.9, 1.4)]
        m.extend(rng.uniform(0.4, 0.9) for _ in range(SLOTS - len(m)))
    elif pat == 2:
        falling(SLOTS, rng.uniform(0.85, 0.9))
    else:
        start = rng.randint(1, 7)
        falling(start, rng.uniform(0.4, 0.9))
        peak = rng.uniform(1.4, 2.0)
        m += [rng.uniform(0.9, 1.4), rng.uniform(0.9, 1.4), rng.uniform(1.4, peak), peak, rng.uniform(1.4, peak)]
        falling(SLOTS - len(m), rng.uniform(0.4, 0.9))
    return pat, [max(9, round(base * x)) for x in m[:SLOTS]]


def refresh(s: GameState, now: datetime | None = None, rng: random.Random | None = None) -> int:
    """새 주가 되었으면 이번 주 값·시세를 정하고, 지난주 오이는 시든다. 시든 오이 수를 돌려줌."""
    now = now or datetime.now()
    wk = week_of(now.date()).isoformat()
    wilted = 0
    if s.cuke_week != wk:
        rng = rng or random.Random()
        s.cuke_week = wk
        s.cuke_base = rng.randint(90, 110)
        s.cuke_seed = rng.randrange(1 << 30)
        s.cuke_hint = rng.random() < 0.7
    if s.cuke_have and s.cuke_bought != wk:
        wilted, s.cuke_have, s.cuke_paid = s.cuke_have, 0, 0
    return wilted


def prices(s: GameState) -> list[int]:
    return make_prices(s.cuke_seed, s.cuke_base)[1]


def pattern(s: GameState) -> int:
    return make_prices(s.cuke_seed, s.cuke_base)[0]


def price_now(s: GameState, now: datetime | None = None) -> int:
    k = slot_of(now or datetime.now())
    return s.cuke_base if k < 0 else prices(s)[k]


def hint(s: GameState) -> str:
    pat = pattern(s) if s.cuke_hint else random.Random(s.cuke_seed + 7).randrange(4)
    return HINTS[pat]


def buy(s: GameState, n: int, now: datetime | None = None) -> int:
    """오이 n개 사기 (살 수 있는 만큼만). 산 개수."""
    now = now or datetime.now()
    refresh(s, now)
    if not can_buy(now):
        return 0
    n = max(0, min(n, MAX_HAVE - s.cuke_have, s.saisen // s.cuke_base))
    if n:
        cost = n * s.cuke_base
        s.saisen -= cost
        s.cuke_have += n
        s.cuke_paid += cost
        s.cuke_bought = s.cuke_week
    return n


def sell(s: GameState, n: int, now: datetime | None = None) -> int:
    """오이 n개 팔기. 받은 새전."""
    now = now or datetime.now()
    refresh(s, now)
    n = max(0, min(n, s.cuke_have))
    if not can_sell(now) or not n:
        return 0
    price = price_now(s, now)
    got = n * price
    cost = round(s.cuke_paid * n / s.cuke_have)
    s.cuke_have -= n
    s.cuke_paid -= cost
    s.add_saisen(got)
    s.cuke_profit += got - cost
    s.cuke_best = max(s.cuke_best, price)
    return got


class CucumberWindow(QWidget):
    """오이 시세 창: 이번 주 그래프 + 사고팔기."""

    def __init__(self, game: "Game"):
        super().__init__(None, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        from .panel import STYLE, portrait
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("panel")
        self.setStyleSheet(STYLE)
        self.game = game
        self.setFixedWidth(470)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 16)
        v.setSpacing(7)
        top = QHBoxLayout()
        face = QLabel()
        face.setPixmap(portrait("nitori", 54, False))
        top.addWidget(face)
        col = QVBoxLayout()
        col.addWidget(QLabel("🥒  니토리의 오이 시세", objectName="title"))
        self.say = QLabel(objectName="goal")
        self.say.setWordWrap(True)
        col.addWidget(self.say)
        top.addLayout(col, 1)
        v.addLayout(top)
        self.chart = _Chart(self)
        v.addWidget(self.chart)
        self.info = QLabel(objectName="goal")
        self.info.setWordWrap(True)
        v.addWidget(self.info)
        self.row = QHBoxLayout()
        self.btns: list[QPushButton] = []
        v.addLayout(self.row)
        foot = QLabel("일요일·월요일 오전에 사서, 월요일 오후~토요일에 하루 두 번 바뀌는 값에 팔아요. "
                      "다음 일요일이 되면 남은 오이는 시들어요.", objectName="sub")
        foot.setWordWrap(True)
        v.addWidget(foot)
        self.refresh()

    def refresh(self) -> None:
        s = self.game.state
        now = datetime.now()
        wilted = refresh(s, now)
        if wilted:
            self.game.on_cucumber(f"🥒 오이 {wilted:,}개가 시들어 버렸다…")
        price = price_now(s, now)
        while self.row.count():                         # 단추는 매번 새로 (살 때·팔 때가 달라서)
            item = self.row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.btns = []
        for _ in range(3 if can_buy(now) else 2):
            b = QPushButton(objectName="upgrade")
            b.setCursor(Qt.PointingHandCursor)
            self.row.addWidget(b)
            self.btns.append(b)
        self.row.addStretch(1)
        if can_buy(now):
            self.say.setText("싱싱한 오이 있어! 이번 주 값은 개당 " f"{s.cuke_base}. 월요일 오후부터 팔 수 있어~")
            for b, n in zip(self.btns, (*BUY_STEPS, MAX_HAVE)):
                k = min(n, MAX_HAVE - s.cuke_have, s.saisen // s.cuke_base)
                b.setText(f"{'최대' if n == MAX_HAVE else n}개 사기  {k * s.cuke_base:,}" if k else f"{n}개 사기")
                b.setEnabled(k > 0)
                b.clicked.connect(lambda _=False, n=n: self._buy(n))
                b.show()
        else:
            k = slot_of(now)
            self.say.setText((hint(s) + " " if k <= 1 else "") + f"지금 시세는 개당 {price}!")
            for b, (label, frac) in zip(self.btns, (("모두 팔기", 1.0), ("절반 팔기", 0.5))):
                n = max(1, int(s.cuke_have * frac)) if s.cuke_have else 0
                b.setText(f"{label}  +{n * price:,}" if n else label)
                b.setEnabled(n > 0)
                b.clicked.connect(lambda _=False, frac=frac: self._sell(frac))
                b.show()
        if s.cuke_have:
            avg = s.cuke_paid / s.cuke_have
            now_value = s.cuke_have * price
            diff = now_value - s.cuke_paid
            self.info.setText(f"가진 오이 {s.cuke_have:,}개 (산 값 개당 {avg:.0f})  ·  지금 팔면 {now_value:,} "
                              f"({'+' if diff >= 0 else ''}{diff:,})")
        else:
            self.info.setText(f"가진 오이 없음  ·  지금까지 오이로 번 새전 {s.cuke_profit:+,}"
                              + (f"  ·  최고 시세 {s.cuke_best}" if s.cuke_best else ""))
        self.chart.update()
        self.adjustSize()

    def _buy(self, n: int) -> None:
        got = buy(self.game.state, n)
        if got:
            self.game.on_cucumber(f"🥒 오이 {got:,}개를 샀다!")
        self.refresh()

    def _sell(self, frac: float) -> None:
        s = self.game.state
        n = max(1, int(s.cuke_have * frac))
        got = sell(s, n)
        if got:
            self.game.on_cucumber(f"🥒 오이 {n:,}개를 팔았다!  새전 +{got:,}")
        self.refresh()

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
        p.fillRect(QRectF(r.left(), r.top(), r.width(), 4), QColor("#3E8E5A"))
        p.restore()
        p.end()


class _Chart(QWidget):
    """이번 주 시세 막대 (지나간 칸만 보이고, 앞으로는 ?)."""

    def __init__(self, win: CucumberWindow):
        super().__init__(win)
        self.win = win
        self.setFixedHeight(130)

    def paintEvent(self, _e) -> None:
        s = self.win.game.state
        now = datetime.now()
        cur = slot_of(now)
        ps = prices(s)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        top, bottom = 18.0, h - 22.0
        hi = max([s.cuke_base * 1.6] + [ps[i] for i in range(max(0, cur + 1))])
        step = w / SLOTS

        def y_of(v: float) -> float:
            return bottom - (bottom - top) * min(1.0, v / hi)
        base_y = y_of(s.cuke_base)
        p.setPen(QPen(QColor(200, 16, 46, 120), 1, Qt.DashLine))
        p.drawLine(QPointF(0, base_y), QPointF(w, base_y))
        f = QFont("Malgun Gothic", 8)
        p.setFont(f)
        p.drawText(QRectF(w - 90, base_y - 15, 88, 13), Qt.AlignRight, f"산 값 {s.cuke_base}")
        for i in range(SLOTS):
            x = i * step + 4
            label = SLOT_NAMES[i].replace("오전", "AM").replace("오후", "PM")
            p.setPen(QColor("#8C7479"))
            p.drawText(QRectF(i * step, bottom + 3, step, 16), Qt.AlignCenter, label if i % 2 == 0 else "PM")
            if i <= cur:
                v = ps[i]
                bar = QRectF(x, y_of(v), step - 8, bottom - y_of(v))
                good = v >= s.cuke_base
                color = QColor("#3E8E5A") if good else QColor("#C9A06A")
                if i == cur:
                    color = color.lighter(115)
                    p.setPen(QPen(QColor("#C8102E"), 2))
                else:
                    p.setPen(Qt.NoPen)
                p.setBrush(color)
                p.drawRoundedRect(bar, 3, 3)
                p.setPen(QColor("#2B1D21"))
                p.drawText(QRectF(i * step, y_of(v) - 15, step, 14), Qt.AlignCenter, str(v))
            else:
                p.setPen(QColor(140, 116, 121, 120))
                p.drawText(QRectF(i * step, bottom - 22, step, 18), Qt.AlignCenter, "?")
        p.end()

