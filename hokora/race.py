# -*- coding: utf-8 -*-
"""요정 달리기 (우마무스메 오마주): 써니 · 루나 · 스타 · 치르노가 작업표시줄 위를 달린다. 한 명에게 새전을 건다.

- 출전표: 그날 컨디션에 따라 배당이 다르다. 배당 = 0.9 ÷ 이길 확률 (길게 보면 신사가 10% 가져감).
- 결과는 출발할 때 정해지고, 달리는 동안 앞서거니 뒤서거니 하다가 그대로 들어온다.
- 건 친구가 1착이면 건 새전 × 배당. 경주가 끝나면 다음 출전표가 새로 나온다.
창은 작업표시줄 바로 위 좁은 띠 (클릭은 뒤로 통과).
"""
from __future__ import annotations

import math
import random
import time
from typing import Callable

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .sprites import image_sprites
from .state import GameState

RUNNERS = ("sunny", "luna", "star", "cirno")
NAMES = {"sunny": "서니", "luna": "루나", "star": "스타", "cirno": "치르노"}
COLORS = {"sunny": "#E8833A", "luna": "#C9A64A", "star": "#3D6FD8", "cirno": "#3FB7E4"}
CONDITIONS = [(1.5, "절호조"), (1.2, "호조"), (1.0, "보통"), (0.75, "부진")]
BETS = (1_000, 10_000, 100_000)
HOUSE = 0.9
RACE_SECONDS = 13.0
AFTER = 3.0               # 다 들어오고 결과를 보여 주는 시간
SCALE = 0.8               # 친구 그림 크기 (작업표시줄의 친구보다 조금 작게)
LANE = 20                 # 레인 간격
OVERRUN = 40              # 결승선을 지나 더 달리는 거리


def new_card(rng: random.Random | None = None) -> list[list]:
    """[[키, 배당, 컨디션], …]"""
    rng = rng or random.Random()
    picks = {k: rng.choice(CONDITIONS) for k in RUNNERS}
    w = {k: picks[k][0] * rng.uniform(0.85, 1.15) for k in RUNNERS}
    total = sum(w.values())
    return [[k, max(1.2, round(HOUSE * total / w[k], 1)), picks[k][1]] for k in RUNNERS]


def card(s: GameState) -> list[list]:
    if len(s.race_card) != len(RUNNERS):
        s.race_card = new_card()
    return s.race_card


def odds_of(s: GameState, key: str) -> float:
    return next(o for k, o, _c in card(s) if k == key)


def decide(c: list[list], rng: random.Random | None = None) -> str:
    """배당에서 이길 확률을 되짚어 1착을 뽑는다 (확률 ∝ 1 / 배당)."""
    rng = rng or random.Random()
    keys = [k for k, _o, _c in c]
    return rng.choices(keys, weights=[1 / o for _k, o, _c in c])[0]


def settle(s: GameState) -> tuple[str, int, float, str, int] | None:
    """달리는 중이던 내기를 정산 → (건 친구, 건 새전, 배당, 1착, 받은 새전). 없으면 None.

    건 새전은 이미 빠져 있으므로, 이기면 돌려받는 몫(원금)은 '모은 새전'에 세지 않고 번 만큼만 센다.
    """
    if len(s.race_pending) != 4:
        s.race_pending = []
        return None
    key, bet, odds, winner = s.race_pending
    s.race_pending = []
    s.race_card = new_card()                        # 다음 경주 출전표
    pay = 0
    if winner == key:
        pay = int(bet * odds)
        s.saisen += bet
        s.add_saisen(pay - bet)
        s.race_wins += 1
    s.race_profit += pay - bet
    return key, bet, odds, winner, pay


def blocked(s: GameState, bet: int, running: bool) -> str:
    if running:
        return "지금 달리는 중이에요"
    if s.saisen < bet:
        return f"새전이 {bet - s.saisen:,} 모자라요"
    return ""


class RaceBoard(QWidget):
    """출전표: 친구마다 컨디션 · 배당과 거는 버튼. 누르면 on_bet(키, 건 새전)."""

    def __init__(self, s: GameState, on_bet: Callable[[str, int], None], running: bool = False):
        super().__init__(None, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout

        from .panel import STYLE, portrait
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("panel")
        self.setStyleSheet(STYLE)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 16)
        v.setSpacing(6)
        v.addWidget(QLabel("🏁  요정 달리기", objectName="title"))
        tip = QLabel("한 명에게 새전을 걸어요. 1착이면 건 새전 × 배당!  컨디션이 좋을수록 잘 달리지만 배당은 낮아요.",
                     objectName="goal")
        tip.setWordWrap(True)
        v.addWidget(tip)
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        self.buttons: dict[tuple[str, int], QPushButton] = {}
        for row, (k, odds, cond) in enumerate(card(s)):
            face = QLabel()
            face.setPixmap(portrait(k, 30, False))
            grid.addWidget(face, row, 0)
            grid.addWidget(QLabel(NAMES[k], objectName="name"), row, 1)
            grid.addWidget(QLabel(f"{cond}  ·  ×{odds:g}", objectName="goal"), row, 2)
            for i, bet in enumerate(BETS):
                b = QPushButton(f"{bet:,}", objectName="small")
                b.setCursor(Qt.PointingHandCursor)
                why = blocked(s, bet, running)
                b.setEnabled(not why)
                b.setToolTip(why or f"{NAMES[k]}에게 {bet:,} 걸기 → 1착이면 {int(bet * odds):,}")
                b.clicked.connect(lambda _=False, k=k, bet=bet: (self.close(), on_bet(k, bet)))
                grid.addWidget(b, row, 3 + i)
                self.buttons[(k, bet)] = b
        v.addLayout(grid)
        rec = QLabel(f"지금까지 {s.race_count}번 · 적중 {s.race_wins}번 · 손익 {s.race_profit:+,}", objectName="sub")
        v.addWidget(rec)

    def show_near(self, pos) -> None:
        from PySide6.QtGui import QGuiApplication
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
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 14, 14)
        p.setPen(QPen(QColor(200, 16, 46, 120), 1.2))
        p.setBrush(QColor(255, 247, 248, 248))
        p.drawPath(path)
        p.end()


class RaceWindow(QWidget):
    """작업표시줄 위 경주로. 다 끝나면 on_finish(1착) 을 부르고 닫힌다."""

    H = 170

    def __init__(self, c: list[list], winner: str, area: QRect, center_x: float, ground_y: float,
                 bet_key: str = "", on_finish: Callable[[str], None] | None = None,
                 hidden: Callable[[], bool] | None = None, rng: random.Random | None = None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        rng = rng or random.Random()
        w = min(area.width(), 1100)
        x = int(min(max(center_x - w / 2, area.left()), area.right() - w + 1))
        self.setGeometry(x, int(ground_y) - self.H, w, self.H)
        self.card, self.winner, self.bet_key = c, winner, bet_key
        self.on_finish, self.hidden = on_finish, hidden or (lambda: False)
        self.start_x, self.goal_x = 70.0, w - 100.0
        self.keys = [k for k, _o, _c in c]
        self.plan: dict[str, tuple[float, float, float, float]] = {}   # 키 → (들어오는 시각, 흔들림 폭, 빠르기, 위상)
        for k in self.keys:
            t_in = RACE_SECONDS if k == winner else RACE_SECONDS + rng.uniform(0.35, 1.6)
            self.plan[k] = (t_in, rng.uniform(0.03, 0.06), rng.uniform(0.6, 1.0), rng.uniform(0, math.tau))
        self.frames: dict[str, tuple] = {}
        for k in self.keys:
            sp = image_sprites(k)
            if sp is not None:
                self.frames[k] = (sp, {n: sp.draw(n, 0.0, 0.0, True, 1, 2.0) for n in sp.sequence("run")},
                                  {n: sp.draw(n, 0.0, 0.0, True, 1, 2.0) for n in sp.sequence("happy")})
        self.started = time.monotonic()
        self.finished = False
        self.timer = QTimer(self, timeout=self._tick, interval=33)
        self.timer.start()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def progress(self, key: str, t: float | None = None) -> float:
        """0 (출발) ~ 1 (결승). 1착은 RACE_SECONDS 에, 나머지는 그보다 늦게 들어온다."""
        t = self.elapsed if t is None else t
        t_in, amp, speed, phase = self.plan[key]
        env = max(0.0, 1 - t / RACE_SECONDS)                       # 끝으로 갈수록 흔들림이 줄어 순서대로 들어옴
        return max(0.0, min(1.0, t / t_in + amp * (math.sin(speed * t + phase) - math.sin(phase)) * env))

    def order(self, t: float | None = None) -> list[str]:
        return sorted(self.keys, key=lambda k: -self.progress(k, t))

    def _tick(self) -> None:
        t = self.elapsed
        last_in = max(p[0] for p in self.plan.values())
        if not self.finished and t >= RACE_SECONDS:
            self.finished = True
            if self.on_finish:
                self.on_finish(self.winner)
        if t >= last_in + AFTER:
            self.timer.stop()
            self.close()
            return
        if self.hidden():
            if self.isVisible():
                self.hide()
            return
        if not self.isVisible():
            self.show()
        self.update()

    def lane_y(self, i: int) -> float:
        """레인 i 의 발 높이 (0 이 맨 뒤)."""
        return self.height() - 8 - (len(self.keys) - 1 - i) * LANE

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        t = self.elapsed
        w = self.width()
        top, bottom = self.lane_y(0) - 14, self.height() - 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(196, 160, 110, 110))
        p.drawRoundedRect(QRectF(self.start_x - 10, top, self.goal_x - self.start_x + 60, bottom - top), 10, 10)
        p.setPen(QPen(QColor(255, 255, 255, 70), 1))
        for i in range(1, len(self.keys)):                                   # 레인 구분선
            y = self.lane_y(i) - 12
            p.drawLine(QPointF(self.start_x - 4, y), QPointF(self.goal_x + 44, y))
        p.setPen(QPen(QColor(255, 255, 255, 210), 2, Qt.DashLine))           # 출발선
        p.drawLine(QPointF(self.start_x, top + 2), QPointF(self.start_x, bottom - 2))
        cell = (bottom - top - 4) / 8
        for i in range(8):                                                   # 결승선 (체크무늬)
            for j in range(2):
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#222222") if (i + j) % 2 else QColor("#FFFFFF"))
                p.drawRect(QRectF(self.goal_x + j * 5, top + 2 + i * cell, 5, cell))
        p.setPen(QPen(QColor(90, 70, 50), 2))
        p.drawLine(QPointF(self.goal_x + 12, top + 2), QPointF(self.goal_x + 12, top - 34))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#C8102E"))
        flag = QPainterPath(QPointF(self.goal_x + 12, top - 34))
        flag.lineTo(self.goal_x + 40, top - 26)
        flag.lineTo(self.goal_x + 12, top - 18)
        p.drawPath(flag)
        f = QFont("Malgun Gothic", 8)
        f.setBold(True)
        p.setFont(f)
        for i, k in enumerate(self.keys):                                    # 레인 이름표 (출발선 왼쪽)
            label = QRectF(2, self.lane_y(i) - 16, self.start_x - 14, 15)
            p.setPen(QPen(QColor("#FFD54A"), 1.5) if k == self.bet_key else Qt.NoPen)
            p.setBrush(QColor(COLORS[k]))
            p.drawRoundedRect(label, 7, 7)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(label, Qt.AlignCenter, ("★" if k == self.bet_key else "") + NAMES[k])
        for i, k in enumerate(self.keys):                                    # 뒤 레인부터 그려 앞 레인이 위로
            base_y = self.lane_y(i)
            t_in = self.plan[k][0]
            done = t >= t_in
            over = OVERRUN * (1 - math.exp(-(t - t_in) * 2.5)) if done else 0.0   # 들어온 뒤 조금 더 달리다 멈춤
            x = self.start_x + (self.goal_x - self.start_x) * self.progress(k, t) + over
            if k in self.frames:
                _sp, run, happy = self.frames[k]
                cheer = done and k == self.winner and t - t_in > 0.6
                frames = happy if cheer else run
                seq = list(frames)
                name = seq[int(t * 4) % len(seq)] if cheer else seq[int((x - self.start_x) / 22) % len(seq)]
                pm, anchor = frames[name]
                p.drawPixmap(QRectF(x - anchor.x() * SCALE, base_y - anchor.y() * SCALE,
                                    pm.width() / pm.devicePixelRatio() * SCALE,
                                    pm.height() / pm.devicePixelRatio() * SCALE), pm, QRectF(pm.rect()))
            else:                                                            # 그림이 없으면 동그라미
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(COLORS[k]))
                p.drawEllipse(QPointF(x, base_y - 16), 12, 16)
            if k == self.bet_key:                                            # 건 친구 머리 위에 ★
                p.setPen(QColor("#FFD54A"))
                p.drawText(QRectF(x - 10, base_y - 74, 20, 16), Qt.AlignCenter, "★")
        if self.finished:                                                    # 1착 발표
            big = QFont("Malgun Gothic", 14)
            big.setBold(True)
            p.setFont(big)
            banner = QRectF(w / 2 - 120, 4, 240, 30)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 250, 240, 235))
            p.drawRoundedRect(banner, 12, 12)
            p.setPen(QColor(COLORS[self.winner]))
            p.drawText(banner, Qt.AlignCenter, f"🏆 1착 {NAMES[self.winner]}!")
        p.end()
