# -*- coding: utf-8 -*-
"""친구들끼리 노는 것: 콤비 행동, 술래잡기, 탄막놀이."""
from __future__ import annotations

import math
import random
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .pet import RUN_SPEED

if TYPE_CHECKING:
    from .events import Events
    from .pet import PetWindow

# 콤비: (a, b) → (a 동작, b 동작, a 대사, b 대사, 초)
COMBOS = {
    ("reimu", "marisa"): ("sit", "sit", "차 한잔 할래?", "좋지! 과자도 있냐?", 9.0),
    ("remilia", "sakuya"): ("happy", "wave", "사쿠야, 홍차.", "네, 아가씨. 여기 있습니다.", 3.0),
    ("remilia", "flandre"): ("wave", "happy", "플랑, 얌전히 있으렴.", "언니다~!", 3.0),
    ("reimu", "sanae"): ("idle", "wave", "…신앙 뺏으러 왔지?", "그런 거 아니에요~!", 3.0),
    ("cirno", "reimu"): ("skill", "startled", "무녀! 승부다!", "앗 차가워!", 2.0),
    ("marisa", "flandre"): ("wave", "happy", "오, 플랑! 놀자!", "마리사다! 놀자!", 3.0),
    ("sakuya", "reimu"): ("wave", "idle", "신사 청소가 부족하네요.", "…잔소리는 됐어.", 3.0),
}
TAG_TIME = 20.0
DUEL_TIME = 6.0
# 캐릭터별 탄 색 (없으면 흰색)
SHOT_COLORS = {
    "reimu": ("#E23C52", "#FFFFFF"), "marisa": ("#F4D35E", "#FFF6C8"), "cirno": ("#7FD3F7", "#E6F7FF"),
    "sakuya": ("#C8CCD8", "#FFFFFF"), "sanae": ("#5FB84E", "#E4F5DD"), "remilia": ("#C0303A", "#FFB3BC"),
    "flandre": ("#F08A2E", "#FFE08A"), "aya": ("#333333", "#DDDDDD"), "suika": ("#9C6ADE", "#E9DDFB"),
}


def combo_for(a: "PetWindow", b: "PetWindow"):
    """둘이 콤비면 (앞 사람, 뒤 사람, 설정), 아니면 None."""
    for x, y in ((a, b), (b, a)):
        c = COMBOS.get((x.ch.key, y.ch.key))
        if c:
            return x, y, c
    return None


class Tag:
    """술래잡기: 술래는 가장 가까운 친구를 쫓고, 나머지는 도망간다. 닿으면 술래가 바뀐다."""

    def __init__(self, events: "Events", players: list["PetWindow"]):
        self.ev = events
        self.players = players
        self.it = random.choice(players)
        self.until = time.monotonic() + TAG_TIME
        self.pause_until = time.monotonic() + 1.0          # 술래는 1초 세고 출발
        for p in players:
            p.scripted = True
        events._say(self.it, "내가 술래!")

    def tick(self) -> bool:
        """계속하면 True."""
        now = time.monotonic()
        alive = [p for p in self.players if p.scripted and p.on is not None and p.state != "held"]
        if now >= self.until or len(alive) < 2 or self.it not in alive:
            self.end()
            return False
        others = [p for p in alive if p is not self.it]
        target = min(others, key=lambda p: abs(p.pos_x - self.it.pos_x))
        for p in others:                                    # 술래 반대쪽으로 도망
            away = 1 if p.pos_x >= self.it.pos_x else -1
            if p.state != "run" or p.vx == 0 or (p.vx > 0) != (away > 0):
                p.act("run", 99, vx=away * RUN_SPEED * 0.6)
        if now >= self.pause_until:
            d = 1 if target.pos_x > self.it.pos_x else -1
            if self.it.state != "run" or (self.it.vx > 0) != (d > 0) or self.it.vx == 0:
                self.it.act("run", 99, vx=d * RUN_SPEED * 0.75)
        else:
            self.it.act("idle", 99)
        if abs(target.pos_x - self.it.pos_x) < 22 and now >= self.pause_until:
            self.ev._say(self.it, "잡았다!")
            target.act("caught", 99)
            self.it, self.pause_until = target, now + 1.2
        return True

    def end(self) -> None:
        for p in self.players:
            p.scripted = False
            if p.on is not None and p.state not in ("held", "fall", "jump"):
                p.act("happy", 1.0)


class Duel(QWidget):
    """탄막놀이: 두 친구가 마주 보고 알록달록한 탄을 주고받는다 (클릭은 통과, 다치지 않음)."""

    def __init__(self, events: "Events", a: "PetWindow", b: "PetWindow"):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.ev, self.a, self.b = events, a, b
        for p, other in ((a, b), (b, a)):
            p.scripted = True
            p.facing = 1 if other.pos_x > p.pos_x else -1
            p.act("skill", 99)
        x0, x1 = sorted((a.pos_x, b.pos_x))
        self.ground = a.pos_y
        self.setFixedSize(int(x1 - x0 + 120), 170)
        self.move(round(x0 - 60), round(self.ground - 160))
        self.ox, self.oy = x0 - 60, self.ground - 160       # 창의 화면 위치 (탄 좌표 → 창 좌표)
        self.bullets: list[list] = []                       # [x, y, vx, vy, 색, 테두리, 쏜 사람]
        self.start = self.last = time.monotonic()
        self.next_shot = {a: self.start + 0.3, b: self.start + 0.6}
        events._say(a, random.choice(["탄막 승부!", "간다!", "피해 봐!"]))
        self.timer = QTimer(self, timeout=self._tick, interval=33)
        self.timer.start()

    def _tick(self) -> None:
        now = time.monotonic()
        dt, self.last = now - self.last, now
        done = now - self.start > DUEL_TIME
        for shooter, target in ((self.a, self.b), (self.b, self.a)):
            if not done and now >= self.next_shot[shooter]:
                self.next_shot[shooter] = now + random.uniform(0.18, 0.35)
                d = 1 if target.pos_x > shooter.pos_x else -1
                col, rim = SHOT_COLORS.get(shooter.ch.key, ("#FFFFFF", "#DDDDDD"))
                ang = random.uniform(-0.35, 0.25)
                speed = random.uniform(170, 240)
                self.bullets.append([shooter.pos_x + d * 14, shooter.pos_y - 36, d * speed * math.cos(ang),
                                     speed * math.sin(ang), col, rim, shooter])
        for bl in self.bullets:
            bl[0] += bl[2] * dt
            bl[1] += bl[3] * dt
            target = self.b if bl[6] is self.a else self.a
            if abs(bl[0] - target.pos_x) < 12 and target.state == "skill" and random.random() < 0.3:
                target.squash = 0.18                          # 스쳤다! (다치지 않음)
        self.bullets = [bl for bl in self.bullets
                        if self.ox - 10 < bl[0] < self.ox + self.width() + 10 and self.oy - 10 < bl[1] < self.ground]
        if done and not self.bullets:
            self.finish()
            return
        self.update()

    def finish(self) -> None:
        self.timer.stop()
        winner, loser = random.sample([self.a, self.b], 2)
        for p in (self.a, self.b):
            p.scripted = False
        if loser.on is not None:
            loser.act("caught", 1.4)
        if winner.on is not None:
            winner.act("happy", 1.2)
        self.ev._say(loser, random.choice(["졌다~", "다음엔 안 져!", "흐엥…"]))
        self.close()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for x, y, vx, vy, col, rim, _s in self.bullets:
            cx, cy = x - self.ox, y - self.oy
            p.setPen(QPen(QColor(rim), 1.5))
            p.setBrush(QColor(col))
            path = QPainterPath()
            path.addEllipse(QPointF(cx, cy), 4.5, 4.5)
            p.drawPath(path)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 200))
            p.drawEllipse(QRectF(cx - 1.8, cy - 2.2, 2.4, 2.4))
        p.end()
