# -*- coding: utf-8 -*-
"""손님 방문: 가끔 신사에 손님이 찾아온다. 신사가 커질수록 찾아오는 손님이 늘어난다.

- 세 요정 (처음부터): 셋이 몰래 와서 장난친다. 서니는 빛을 굴절시켜 반투명하게 숨어 새전을 조금 털고
  장식 하나를 숨기고, 루나는 소리를 지워 친구들 말풍선이 "……"가 되고, 스타는 망을 보다가
  커서가 다가오면 제일 먼저 도망간다. 요정을 클릭하거나 붙잡으면 사과하고 새전을 두고 간다.
- 아야 (신사 2단계부터): 하늘에서 휙 내려와 친구 하나를 취재하고 사진을 찍은 뒤, 붕붕마루 신문 호외를 낸다.
  기사가 나면 참배객이 늘어 30분 동안 새전 수입이 1.5배.
- 스이카 (신사 3단계부터): 안개로 나타나 신사 앞에서 술을 마시며 비틀비틀. 기분이 좋으면 새전을 크게
  두고 간다. 술을 대접하면 꼭, 두 배로.

손님도 PetWindow 라서 쓰다듬기·들어서 던지기가 똑같이 되고, 늘 각본(scripted)으로만 움직인다.
"""
from __future__ import annotations

import logging
import math
import os
import random
import time
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QAbstractAnimation, QPointF, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

from . import affection as aff
from . import omamori
from .bubble import say
from .news import NewsCard, answer_for, make_article
from .pet import RUN_SPEED, PetWindow
from .render import GUESTS
from .state import DECOR

if TYPE_CHECKING:
    from PySide6.QtWidgets import QMenu

    from .app import Game

log = logging.getLogger("Hokora.guests")

# 방문 종류 → (손님들, 찾아오기 시작하는 신사 단계)
VISITS = {
    "fairies": (("sunny", "luna", "star"), 1),
    "aya": (("aya",), 2),
    "suika": (("suika",), 3),
}
VISIT_CHECK = 60.0        # 이 간격으로 손님이 올지 주사위
VISIT_CHANCE = 0.15
VISIT_COOLDOWN = 15 * 60  # 손님이 다녀간 뒤 이만큼은 쉼 → 평균 20분쯤에 한 번
FIRST_VISIT = 4 * 60      # 켠 뒤 이만큼 지나야 첫 손님
MAX_VISIT = 180.0         # 무슨 일이 있어도 이만큼 지나면 돌아감
BUBBLE_UP = 76

FAIRY_PRANK = 20.0        # 요정 장난 시간
FAIRY_SENSE = 150.0       # 스타가 커서를 알아채는 거리
FAIRY_REACT = 0.9         # 알아채고 도망가기까지 (이 사이에 클릭하면 잡음)
FAIRY_APOLOGY = 10        # 붙잡힌 요정이 두고 가는 새전 × 신사 단계
SUNNY_ALPHA = 0.35        # 서니가 숨었을 때 보이는 정도
NEWS_DELAY = 3.0          # 아야가 떠나고 호외가 나오기까지
SUIKA_STAY = (55.0, 80.0)
SAKE_PRICE = aff.GIFTS["sake"][2]

GUEST_TALK = {
    "sunny": ["우린 장난 안 쳤어! …아마도.", "서니 밀크! 빛의 요정이야!", "안 보였지? 헤헤."],
    "luna": ["쉿… 조용히 해 줘.", "루나 차일드예요. 소리를 지울 수 있어요.", "…다음엔 안 들킬 거예요."],
    "star": ["스타 사파이어야. 다 느껴진다구.", "너 방금 이쪽으로 오고 있었지?", "도망가는 건 내가 제일 빨라!"],
    "aya": ["붕붕마루 신문, 한 부 어떠세요?", "특종 냄새가 나요!", "이 신사, 기사거리가 많네요."],
    "suika": ["한 잔 할래~?", "오니는 거짓말 안 해!", "여기 술맛 좋다~ 딸꾹!"],
}
APOLOGY = {
    "sunny": "들켰다~ 미안해, 돌려줄게!",
    "luna": "죄송해요… 소리 돌려 드릴게요.",
    "star": "나까지 잡히다니… 미안해~",
}
GUEST_ABOUT = {  # 도감: (아직 못 만났을 때 힌트, 만난 뒤 설명)
    "sunny": ("장난을 좋아하는 빛의 요정", "빛을 굴절시켜 숨어서 새전을 슬쩍"),
    "luna": ("소리를 지우는 달의 요정", "친구들 말소리를 지워 버려요"),
    "star": ("무엇이든 알아채는 별의 요정", "커서가 다가오면 제일 먼저 도망가요"),
    "aya": ("특종을 찾아다니는 까마귀 텐구", "취재하고 붕붕마루 신문 호외를 내요"),
    "suika": ("술을 좋아하는 작은 오니", "술을 대접하면 새전 두 배"),
}
INTERVIEW_Q = ["최근 새전 사정은 어떤가요?", "독자들께 한 말씀 부탁드려요!", "요즘 신사에 무슨 일이 있었나요?"]
DRINK_WITH = {  # 스이카가 한 잔 권했을 때
    "reimu": "…낮술은 좀 그렇지 않아?", "marisa": "오, 좋지! 한 잔만!", "cirno": "얼음 넣어 줄까?",
    "sakuya": "근무 중이라서요.", "sanae": "미성년자는 안 돼요!", "remilia": "와인이라면 몰라도.",
    "flandre": "나도 마실래!",
}


def available(s) -> list[str]:
    """지금 신사 단계에 찾아올 수 있는 방문 종류."""
    return [k for k, (_, stage) in VISITS.items() if s.shrine_level >= stage]


def guest_stage(key: str) -> int:
    return next(stage for keys, stage in VISITS.values() if key in keys)


# ── 화면 효과 (클릭은 통과) ──
class _Overlay(QWidget):
    def __init__(self, w: int, h: int, seconds: float):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(w, h)
        self.start, self.seconds = time.monotonic(), seconds
        self.timer = QTimer(self, timeout=self._tick, interval=33)
        self.timer.start()

    @property
    def age(self) -> float:
        return (time.monotonic() - self.start) / self.seconds

    def _tick(self) -> None:
        if self.age >= 1:
            self.close()
        else:
            self.update()


class Flash(_Overlay):
    """카메라 플래시: 하얗게 번쩍했다 사라짐."""

    def __init__(self, cx: float, cy: float, seconds: float = 0.45):
        super().__init__(240, 240, seconds)
        self.move(round(cx - 120), round(cy - 120))

    def paintEvent(self, _e) -> None:
        a = max(0.0, 1 - self.age) ** 1.5
        g = QRadialGradient(QPointF(120, 120), 120)
        g.setColorAt(0, QColor(255, 255, 255, int(250 * a)))
        g.setColorAt(0.35, QColor(255, 255, 240, int(170 * a)))
        g.setColorAt(1, QColor(255, 255, 255, 0))
        p = QPainter(self)
        p.fillRect(self.rect(), g)
        p.end()


class Mist(_Overlay):
    """스이카가 안개로 모였다 흩어질 때의 뭉게뭉게."""

    def __init__(self, cx: float, ground: float, seconds: float = 1.6):
        super().__init__(180, 150, seconds)
        self.move(round(cx - 90), round(ground - 140))
        rng = random.Random()
        self.puffs = [(rng.uniform(40, 140), rng.uniform(40, 125), rng.uniform(14, 26), rng.uniform(0, 0.35))
                      for _ in range(16)]

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        for x, y, r, delay in self.puffs:
            t = (self.age - delay) / (1 - delay)
            if t <= 0:
                continue
            a = math.sin(min(t, 1.0) * math.pi)          # 짙어졌다 옅어짐
            rr = r * (0.6 + t * 0.7)
            p.setBrush(QColor(214, 200, 232, int(170 * a)))
            p.drawEllipse(QPointF(x, y - t * 14), rr, rr)
        p.end()


class Guest:
    """손님 한 명 = PetWindow 하나 + 각본용 메모."""

    def __init__(self, visit: "Visit", key: str, x: float):
        self.visit, self.key = visit, key
        self.pet = PetWindow(GUESTS[key], visit.game, x)
        self.pet.scripted = True
        self.pet.setWindowOpacity(0.0)
        self.goal: float | None = None
        self._speed, self._run = 0.0, False
        self.caught = False
        self.gone = False        # 떠나는 중 (사라지는 애니메이션)
        self.removed = False     # 창까지 닫힘
        self.step = ""           # 이 손님만의 진행 단계
        self.until = 0.0

    @property
    def name(self) -> str:
        return self.pet.ch.name

    @property
    def ready(self) -> bool:
        """발판 위에 서 있음 (잡히거나 날아가는 중이 아님)."""
        p = self.pet
        return p.on is not None and p.state not in ("held", "fall", "jump")

    def go(self, x: float, speed: float, run: bool = False) -> None:
        self.goal, self._speed, self._run = x, speed, run
        d = 1 if x > self.pet.pos_x else -1
        self.pet.act("run" if run else "walk", 99, vx=d * speed)

    def arrived(self) -> bool:
        """목표까지 걸어갔으면(또는 발판 끝에 막혔으면) 멈추고 True."""
        p = self.pet
        if self.goal is None:
            return True
        if not self.ready:
            return False
        if p.state not in ("walk", "run"):                  # 도중에 붙잡혔다 내려옴 → 다시 걸음
            self.go(self.goal, self._speed, self._run)
        if abs(p.pos_x - self.goal) < 8 or p.vx == 0 or (p.vx > 0) != (self.goal > p.pos_x):
            self.goal = None
            p.act("idle", 99)
            return True
        return False

    def face(self, x: float) -> None:
        self.pet.facing = 1 if x > self.pet.pos_x else -1

    def fade(self, to: float, seconds: float, then: Callable[[], None] | None = None) -> None:
        anim = QPropertyAnimation(self.pet, b"windowOpacity", self.pet)
        anim.setDuration(int(seconds * 1000))
        anim.setStartValue(self.pet.windowOpacity())
        anim.setEndValue(to)
        if then is not None:
            anim.finished.connect(then)
        anim.start(QAbstractAnimation.DeleteWhenStopped)


class Visit:
    """손님 방문 한 번. tick 에서 단계(phase)를 진행하고, 손님이 모두 떠나면 done."""

    kind = ""

    def __init__(self, visits: "Visits"):
        self.visits, self.game = visits, visits.game
        self.guests: list[Guest] = []
        self.phase, self.until = "enter", 0.0
        self.started = time.monotonic()
        self._timeline: list[tuple[float, Callable[[], None]]] = []

    # ── 도우미 ──
    def spawn(self, key: str, x: float) -> Guest:
        gu = Guest(self, key, x)
        self.guests.append(gu)
        self.game.guests.append(gu.pet)
        if not self.game.hidden_for_fullscreen:
            gu.pet.show()
        return gu

    def say(self, gu: Guest, text: str, seconds: float = 2.6) -> None:
        if not self.game.hidden_for_fullscreen and not gu.removed:
            say(text, gu.pet.pos_x, gu.pet.pos_y - BUBBLE_UP, seconds)

    def at(self, delay: float, fn: Callable[[], None]) -> None:
        """delay 초 뒤에 (방문이 끝났으면 부르지 않음)."""
        self._timeline.append((time.monotonic() + delay, fn))

    def effect(self, w: QWidget) -> None:
        if self.game.hidden_for_fullscreen:
            w.deleteLater()
            return
        self.game.keep(w)
        w.show()

    def leave(self, gu: Guest, seconds: float = 0.8) -> None:
        """사라지며 떠남."""
        if gu.gone:
            return
        gu.gone = True
        gu.fade(0.0, seconds, lambda: self._remove(gu))

    def _remove(self, gu: Guest) -> None:
        if gu.removed:
            return
        gu.removed = True
        if gu.pet in self.game.guests:
            self.game.guests.remove(gu.pet)
        gu.pet.close()
        gu.pet.deleteLater()

    @property
    def done(self) -> bool:
        return bool(self.guests) and all(gu.removed for gu in self.guests)

    def find(self, pet: PetWindow) -> Guest | None:
        return next((gu for gu in self.guests if gu.pet is pet), None)

    @property
    def ground(self):
        return self.game.ground_under(self.game.shrine.pos_x)

    # ── 진행 ──
    def tick(self, now: float) -> None:
        due = [fn for t, fn in self._timeline if t <= now]
        self._timeline = [(t, fn) for t, fn in self._timeline if t > now]
        for fn in due:
            fn()
        if now - self.started > MAX_VISIT:
            self.cancel()
            return
        self.update(now)

    def update(self, now: float) -> None: ...
    def on_click(self, gu: Guest) -> None: ...
    def fill_menu(self, gu: Guest, menu: "QMenu") -> None: ...
    def finish(self) -> None:
        """모두 떠난 뒤 뒷정리."""

    def cancel(self) -> None:
        """낮잠 등으로 방문을 그만둠 — 모두 조용히 사라짐."""
        self._timeline.clear()
        for gu in self.guests:
            self.leave(gu, 0.4)


# ── 세 요정 ──
class FairyVisit(Visit):
    kind = "fairies"

    def __init__(self, visits: "Visits"):
        super().__init__(visits)
        g, sx = self.ground, self.game.shrine.pos_x
        self.side = 1 if (g.x2 - sx) > (sx - g.x1) else -1   # 넓은 쪽에서 몰래 다가옴
        clamp = lambda x: min(max(x, g.x1 + 16), g.x2 - 16)   # noqa: E731
        base = sx + self.side * 430
        self.sunny, self.luna, self.star = (self.spawn(k, clamp(base + self.side * i * 34))
                                            for i, k in enumerate(("sunny", "luna", "star")))
        self.stolen = 0
        self.decor: str | None = None
        self.sensed_at = 0.0
        self._look_at = 0.0
        for gu, off in ((self.sunny, 6), (self.luna, 70), (self.star, 140)):
            gu.fade(1.0, 1.2)
            gu.go(clamp(sx + self.side * off), 75, run=True)
        self.until = time.monotonic() + 12
        self.at(0.6, lambda: self.say(self.star, "쉿, 살금살금~"))

    def update(self, now: float) -> None:
        for gu in self.guests:
            if not gu.caught and not gu.gone and gu.pet.state == "held":
                self.catch(gu)                           # 붙잡아도 잡힘
            if gu.caught and not gu.gone:
                self._apologize(gu, now)
        free = [gu for gu in self.guests if not gu.caught and not gu.gone]
        if self.phase == "enter":
            arrived = [gu.arrived() for gu in free]
            if all(arrived) or now >= self.until:
                self._start_prank(now)
        elif self.phase == "prank":
            if self.star in free and now >= self._look_at and self.star.ready and not self.sensed_at:   # 두리번두리번 망보기
                self._look_at = now + random.uniform(1.2, 2.2)
                self.star.pet.facing = -self.star.pet.facing
            if self._sensed(now, free):
                return
            if now >= self.until:
                for gu in free:
                    gu.pet.act("happy", 1.0)
                if free:
                    self.say(free[0], "장난 성공~!")
                self.at(1.0, lambda: self._run_off(slow=True))
                self.phase = "leave"
        elif self.phase == "flee":
            for gu in free:
                if gu.step == "run" and (now >= gu.until or gu.pet.vx == 0):
                    self.leave(gu, 0.6)

    def _start_prank(self, now: float) -> None:
        self.phase, self.until = "prank", now + FAIRY_PRANK
        free = [gu for gu in self.guests if not gu.caught and not gu.gone]
        if self.sunny in free:
            self.sunny.face(self.game.shrine.pos_x)
            self.sunny.pet.act("skill", 99)
            self.sunny.fade(SUNNY_ALPHA, 0.6)
            self.say(self.sunny, "헤헤, 안 보이지롱~", 2.4)
            self.at(2.6, self._steal)
        if self.luna in free:
            self.luna.pet.act("skill", 99)
            self.at(5.4, lambda: self.luna in self._free() and self._silence())
        if self.star in free:
            self.star.pet.act("idle", 99)
            self.star.pet.facing = self.side
            self._look_at = now + 1.5
            self.at(8.2, lambda: self.star in self._free() and self.say(self.star, "망은 내가 볼게!"))

    def _free(self) -> list[Guest]:
        return [gu for gu in self.guests if not gu.caught and not gu.gone]

    def _silence(self) -> None:
        self.say(self.luna, "쉿… 소리를 지울게.")
        self.visits.silence_until = self.until + 2

    def _steal(self) -> None:
        if self.phase != "prank" or self.sunny not in self._free():
            return
        g, s = self.game, self.game.state
        amount = int(min(max(3, s.saisen * 0.05), 60, s.saisen))
        if amount:
            s.saisen -= amount
            self.stolen = amount
            g.shrine.set_saisen(s.saisen)
            g.shrine.pop(f"-{amount}")
        shown = [k for k, w in g.decors.items() if w.isVisible()]
        if shown:                                          # 장식 하나를 빛으로 가려 숨김
            self.decor = random.choice(shown)
            self.visits.hidden_decor = self.decor
            g.decors[self.decor].hide()
            name = DECOR[self.decor][0]
            self.say(self.sunny, f"{aff.josa(name, '은', '는')} 잠깐 숨겨 둘게~")
        else:
            self.say(self.sunny, "새전 조금만 빌려 갈게~")
        log.info("세 요정 장난: 새전 %d, 장식 %s", amount, self.decor)

    def _sensed(self, now: float, free: list[Guest]) -> bool:
        """스타가 다가오는 커서를 알아채면 도망 (알아챈 뒤 잠깐은 잡을 틈이 있음)."""
        if self.star not in free:
            return False
        c = self.game.cursor
        near = any(abs(c.x() - gu.pet.pos_x) < FAIRY_SENSE and -40 < gu.pet.pos_y - c.y() < FAIRY_SENSE
                   for gu in free)
        if not near:
            self.sensed_at = 0.0
            return False
        if not self.sensed_at:
            self.sensed_at = now
            self.star.face(c.x())
            return False
        if now - self.sensed_at < FAIRY_REACT:
            return False
        self.say(self.star, "앗, 누가 온다! 도망쳐!")
        self._run_off(slow=False)
        return True

    def _run_off(self, slow: bool) -> None:
        """넓은 쪽(들어온 쪽)으로 달아남. 스타가 제일 먼저."""
        self.phase = "flee"
        now = time.monotonic()
        order = [self.star, self.luna, self.sunny]
        for i, gu in enumerate(gu for gu in order if gu in self._free()):
            delay = 0.0 if gu is self.star else 0.35 + i * 0.2
            if not slow and gu is not self.star:
                gu.pet.act("startled", 0.5)
            self.at(delay, lambda gu=gu: self._dash(gu, slow))
            gu.step, gu.until = "wait", now + 99

    def _dash(self, gu: Guest, slow: bool) -> None:
        if gu.caught or gu.gone:
            return
        g = self.ground
        edge = g.x2 - 20 if self.side > 0 else g.x1 + 20
        gu.go(edge, 110 if slow else RUN_SPEED * 0.85, run=True)
        gu.step, gu.until = "run", time.monotonic() + 4.5

    def catch(self, gu: Guest) -> None:
        if gu.caught or gu.gone or gu.key not in APOLOGY:
            return
        gu.caught = True
        gu.goal = None
        gu.fade(1.0, 0.3)                                 # 서니도 모습을 드러냄
        if gu.pet.state != "held":
            gu.pet.act("caught", 1.0)
        gu.step, gu.until = "caught", time.monotonic() + 1.0
        if self.phase in ("enter", "prank") and self._free():   # 하나 잡히면 나머지는 도망
            self._run_off(slow=False)

    def _apologize(self, gu: Guest, now: float) -> None:
        if gu.step == "caught" and now >= gu.until and gu.ready:
            g, s = self.game, self.game.state
            gu.pet.act("bow", 1.8)
            reward = FAIRY_APOLOGY * s.shrine_level
            back = 0
            if gu is self.sunny:
                back, self.stolen = self.stolen, 0
                self._restore_decor()
            s.saisen += back
            s.add_saisen(reward)
            s.fairies_caught += 1
            g.shrine.set_saisen(s.saisen)
            g.shrine.pop(f"+{back + reward}")
            self.say(gu, APOLOGY[gu.key], 2.8)
            log.info("요정 붙잡음: %s (+%d, 돌려받음 %d)", gu.key, reward, back)
            gu.step, gu.until = "bow", now + 1.9
            g.save()
        elif gu.step == "bow" and now >= gu.until:
            self.leave(gu)

    def on_click(self, gu: Guest) -> None:
        self.catch(gu)

    def _restore_decor(self) -> None:
        if self.decor is None:
            return
        g = self.game
        win = g.decors.get(self.decor)
        self.visits.hidden_decor = None
        if win is not None and g.state.show_decor and not g.hidden_for_fullscreen:
            win.show()
        self.decor = None

    def finish(self) -> None:
        if self.decor is not None:
            self._restore_decor()
        self.visits.silence_until = 0.0
        if self.stolen:
            log.info("세 요정 도망: 새전 %d 잃음", self.stolen)

    def cancel(self) -> None:
        if self.stolen:                                   # 낮잠 등으로 끝나면 훔친 새전은 조용히 되돌림
            self.game.state.saisen += self.stolen
            self.game.shrine.set_saisen(self.game.state.saisen)
            self.stolen = 0
        super().cancel()


# ── 아야 ──
class AyaVisit(Visit):
    kind = "aya"

    def __init__(self, visits: "Visits"):
        super().__init__(visits)
        g, sx = self.ground, self.game.shrine.pos_x
        cands = [p for p in self.game.pets if p.grounded and p.on == g.hwnd]
        cands.sort(key=lambda p: abs(p.pos_x - sx))
        self.target: PetWindow | None = random.choice(cands[:3]) if cands else None
        tx = self.target.pos_x if self.target else sx
        self.side = 1 if tx - g.x1 < g.x2 - tx else -1        # 넓은 쪽에 서서 취재
        self.stand = min(max(tx + self.side * 40, g.x1 + 30), g.x2 - 30)
        start_x = min(max(self.stand + self.side * 280, g.x1 + 30), g.x2 - 30)
        self.aya = self.spawn("aya", start_x)
        p = self.aya.pet
        p.pos_y = max(self.game.top + 90, g.y - 560)          # 하늘에서 휙
        p.on = None
        if not p._jump_to(self.stand, g.y):
            p.state = "fall"
        p._place()
        self.aya.fade(1.0, 0.3)
        self.phase = "swoop"
        self.thrown = False
        self.answer = ""
        self._held = False

    def update(self, now: float) -> None:
        a = self.aya
        if a.gone:
            return
        if a.pet.state == "held":
            self._held = True
        if not a.ready:
            return
        if self._held:                                    # 던져졌다 착지
            self._held, self.thrown = False, True
            a.goal = None
            a.pet.act("caught", 1.2)
            self.say(a, "으악! 취재 방해예요~!")
            self._release()
            self.phase, self.until = "bye", now + 1.4
            return
        t = self.target
        if self.phase == "swoop":
            a.face(t.pos_x if t else self.game.shrine.pos_x)
            a.pet.act("bow", 1.4)
            self.say(a, "안녕하세요, 붕붕마루 신문의 샤메이마루 아야입니다!", 2.8)
            self.phase, self.until = "greet", now + 1.8
        elif self.phase == "greet" and now >= self.until:
            if t is not None and t.grounded and abs(t.pos_x - a.pet.pos_x) < 700:
                t.scripted = True
                t.act("idle", 99)
                t.facing = 1 if a.pet.pos_x > t.pos_x else -1
                a.go(t.pos_x + (1 if a.pet.pos_x > t.pos_x else -1) * 38, 60)
                self.phase, self.until = "approach", now + 9
            else:
                self.target = None
                self._photo(now)
        elif self.phase == "approach":
            if self._lost():
                return self._photo(now)
            if a.arrived() or now >= self.until:
                a.goal = None
                a.pet.act("idle", 99)
                a.face(t.pos_x)
                t.facing = 1 if a.pet.pos_x > t.pos_x else -1
                self.say(a, random.choice(INTERVIEW_Q), 1.9)
                self.phase, self.until = "ask", now + 2.0
        elif self.phase == "ask" and now >= self.until:
            if self._lost():
                return self._photo(now)
            self.answer = answer_for(t.ch.key)
            self.game.events._say(t, self.answer, 2.6)
            self.phase, self.until = "answer", now + 2.4
        elif self.phase == "answer" and now >= self.until:
            self._photo(now)
        elif self.phase == "photo" and now >= self.until:
            self.say(a, "좋은 기사가 되겠어요! 그럼 이만~")
            a.pet.act("happy", 1.0)
            self._release()
            self.phase, self.until = "bye", now + 1.2
        elif self.phase == "bye" and now >= self.until:
            self._fly_off()

    def _lost(self) -> bool:
        """취재 상대가 붙잡혀 가거나 떨어짐."""
        t = self.target
        if t is None or t.on is None or t.state in ("held", "fall", "jump") or not t.isVisible():
            self._release()
            self.target = None
            return True
        return False

    def _photo(self, now: float) -> None:
        a, t = self.aya, self.target
        a.goal = None
        a.pet.act("skill", 1.6)
        if t is not None:
            a.face(t.pos_x)
        else:
            a.face(self.game.shrine.pos_x)
        self.at(0.45, self._shutter)
        self.phase, self.until = "photo", now + 1.9

    def _shutter(self) -> None:
        a, t = self.aya, self.target
        x = t.pos_x if t is not None else a.pet.pos_x + a.pet.facing * 60
        y = (t.pos_y if t is not None else a.pet.pos_y) - 36
        self.effect(Flash(x, y))
        self.say(a, "찰칵!", 1.2)
        if t is not None and t.on is not None:
            t.act(random.choice(("happy", "wave", "startled")), 1.2)
            t.hearts.append([0.0, t.width() / 2, 40])

    def _release(self) -> None:
        t = self.target
        if t is not None and t.scripted:
            t.scripted = False
            if t.on is not None and t.state == "idle":
                t.act("idle", 1.0)

    def _fly_off(self) -> None:
        a = self.aya
        p = a.pet
        p.state, p.on = "jump", None
        p.vx, p.vy = -self.side * 420, -1000.0
        p.facing = -self.side
        self.leave(a, 0.45)
        self.phase = "gone"
        self.visits.publish(self.target.ch.key if self.target else None, self.answer, self.thrown)

    def on_click(self, gu: Guest) -> None:
        p = gu.pet                                        # 클릭하면 찰칵 (참배객도 한 장)
        c = self.game.cursor
        gu.face(c.x())
        p.squash = 0.15
        self.effect(Flash(c.x(), c.y()))
        self.say(gu, "찰칵! 참배객도 한 장~", 1.6)

    def finish(self) -> None:
        self._release()

    def cancel(self) -> None:
        self._release()
        super().cancel()


# ── 스이카 ──
class SuikaVisit(Visit):
    kind = "suika"

    def __init__(self, visits: "Visits"):
        super().__init__(visits)
        g, sx = self.ground, self.game.shrine.pos_x
        side = random.choice((-1, 1))
        self.home = min(max(sx + side * random.uniform(90, 180), g.x1 + 40), g.x2 - 40)
        self.suika = self.spawn("suika", self.home)
        self.effect(Mist(self.home, g.y))
        self.suika.fade(1.0, 1.2)
        self.suika.face(sx)
        self.treated = False
        self._held = False
        self.phase, self.until = "arrive", time.monotonic() + 1.3
        self.stay_until = time.monotonic() + random.uniform(*SUIKA_STAY)
        self.next_at = 0.0
        self.at(0.8, lambda: self.say(self.suika, "술 냄새를 따라왔지~ 헤헤"))

    def update(self, now: float) -> None:
        su = self.suika
        if su.gone:
            return
        p = su.pet
        if p.state == "held":
            self._held = True
        if not su.ready:
            return
        if self._held:
            self._held = False
            p.act("caught", 1.4)
            self.say(su, "으아~ 세상이 빙글빙글~")
            self.next_at = now + 1.4
        if self.phase in ("party", "donate"):              # 비틀비틀
            amp = 7.0 if p.state == "walk" else 3.5
            p.tilt = math.sin(now * 2.6) * amp
            p.update()
        if self.phase == "arrive" and now >= self.until:
            p.act("happy", 1.0)
            self.phase, self.next_at = "party", now + 1.0
        elif self.phase == "party":
            if now >= self.stay_until:
                su.go(self.game.shrine.pos_x, 24)
                self.phase, self.until = "donate", now + 8
            elif now >= self.next_at:
                self._activity(now)
        elif self.phase == "donate":
            if su.arrived() or now >= self.until:
                su.goal = None
                self._donate()
                self.phase, self.until = "bye", now + 2.2
        elif self.phase == "bye" and now >= self.until:
            p.tilt = 0.0
            self.effect(Mist(p.pos_x, p.pos_y))
            self.leave(su, 1.0)
            self.phase = "gone"

    def _activity(self, now: float) -> None:
        su, p = self.suika, self.suika.pet
        r = random.random()
        if r < 0.4:                                           # 꿀꺽꿀꺽
            secs = random.uniform(3, 5)
            p.act("skill", secs)
            if random.random() < 0.45:
                self.say(su, random.choice(["꿀꺽꿀꺽~", "크으~ 좋다!", "술이 달다~"]))
        elif r < 0.7:                                         # 비틀비틀 걷기 (신사에서 너무 멀어지면 돌아옴)
            secs = random.uniform(2.5, 4)
            d = random.choice((-1, 1))
            if abs(p.pos_x - self.home) > 150:
                d = 1 if self.home > p.pos_x else -1
            p.act("walk", secs, vx=d * 18)
        elif r < 0.85 or not self._invite():
            secs = random.uniform(2, 3)
            p.act("idle", secs)
            self.say(su, "딸꾹!", 1.4)
        else:
            secs = 3.0
        self.next_at = now + secs

    def _invite(self) -> bool:
        """근처 친구에게 한 잔 권함."""
        su = self.suika
        near = [o for o in self.game.pets if o.grounded and o.on == su.pet.on and abs(o.pos_x - su.pet.pos_x) < 260]
        if not near:
            return False
        o = min(near, key=lambda o: abs(o.pos_x - su.pet.pos_x))
        su.face(o.pos_x)
        su.pet.act("happy", 1.2)
        o.act("sit", 6)
        o.facing = 1 if su.pet.pos_x > o.pos_x else -1
        self.say(su, "너도 한 잔 할래~?")
        self.at(1.4, lambda: self.game.events._say(o, DRINK_WITH.get(o.ch.key, "건배~!")))
        return True

    def _donate(self) -> None:
        g, s, su = self.game, self.game.state, self.suika
        su.face(g.shrine.pos_x)
        if self.treated or random.random() < 0.5:
            amount = max(50, int(s.income_per_min * random.uniform(15, 25))) * (2 if self.treated else 1)
            amount = int(amount * (1 + omamori.bonus(s, "suika")))
            s.add_saisen(amount)
            s.suika_saisen += amount
            g.shrine.set_saisen(s.saisen)
            g.shrine.pop(f"+{amount:,}")
            su.pet.act("happy", 1.4)
            self.say(su, "기분 좋으니까 이거 넣어 둘게~!" if not self.treated else "좋은 술 고마워! 크게 쏜다~!", 3.0)
            log.info("스이카 새전 +%d (대접 %s)", amount, self.treated)
            g.check_unlocks()
            g.save()
        else:
            su.pet.act("wave", 1.6)
            self.say(su, "잘 마시고 간다~ 또 올게!")

    def on_click(self, gu: Guest) -> None:
        gu.pet.act("happy", 1.0)
        gu.face(self.game.cursor.x())
        self.next_at = time.monotonic() + 1.0
        self.say(gu, random.choice(["헤헤~ 한 잔 할래?", "나는 이부키 스이카! 오니야!", "딸꾹!"]), 1.8)

    def fill_menu(self, gu: Guest, menu: "QMenu") -> None:
        if self.treated or self.phase not in ("arrive", "party"):
            return
        a = menu.addAction(f"🍶 술 대접하기  (새전 {SAKE_PRICE})", self.treat)
        a.setEnabled(self.game.state.saisen >= SAKE_PRICE)

    def treat(self) -> None:
        s = self.game.state
        if self.treated or s.saisen < SAKE_PRICE:
            return
        s.saisen -= SAKE_PRICE
        self.treated = True
        self.game.shrine.set_saisen(s.saisen)
        self.suika.pet.act("happy", 1.2)
        self.next_at = time.monotonic() + 1.2
        self.say(self.suika, "오오! 좋은 술이다~! 고마워!", 2.6)
        self.game.save()


VISIT_CLASSES = {"fairies": FairyVisit, "aya": AyaVisit, "suika": SuikaVisit}


class Visits:
    """손님이 올지 정하고, 지금 방문을 진행한다 (Game 이 매 프레임 tick)."""

    def __init__(self, game: "Game"):
        self.game = game
        self.visit: Visit | None = None
        self._next = time.monotonic() + FIRST_VISIT
        self.silence_until = 0.0              # 루나가 소리를 지운 동안 친구들 말풍선은 "……"
        self.hidden_decor: str | None = None  # 서니가 숨긴 장식 (다시 보이지 않게)
        self._forced = os.environ.get("HOKORA_GUEST", "")
        if self._forced in VISITS:            # 시험용: 켜자마자 그 손님이 옴
            self._next = time.monotonic() + 3

    @property
    def silenced(self) -> bool:
        return time.monotonic() < self.silence_until

    def is_guest(self, pet) -> bool:
        return self.visit is not None and self.visit.find(pet) is not None

    def tick(self) -> None:
        g = self.game
        now = time.monotonic()
        if self.visit is not None:
            self.visit.tick(now)
            if self.visit.done:
                self._finish()
            return
        if g.napping or g.hidden_for_fullscreen or now < self._next:
            return
        self._next = now + VISIT_CHECK
        ev = g.events
        if ev.thief or ev.tag or ev.duel:
            return
        if self._forced in VISITS:
            kind, self._forced = self._forced, ""
            self.start(kind)
        elif random.random() < VISIT_CHANCE * (1 + omamori.bonus(g.state, "guest")):
            kinds = available(g.state)
            if kinds:
                self.start(random.choice(kinds))

    def start(self, kind: str) -> bool:
        if self.visit is not None or kind not in VISIT_CLASSES:
            return False
        self.visit = VISIT_CLASSES[kind](self)
        s = self.game.state
        for key in VISITS[kind][0]:
            s.guest_visits[key] = s.guest_visits.get(key, 0) + 1
        log.info("손님 방문: %s", kind)
        return True

    def _finish(self) -> None:
        v, self.visit = self.visit, None
        v.finish()
        self._next = time.monotonic() + VISIT_COOLDOWN
        log.info("손님 돌아감: %s", v.kind)
        self.game.save()

    def cancel(self) -> None:
        if self.visit is not None:
            self.visit.cancel()

    def on_click(self, pet: PetWindow) -> None:
        gu = self.visit.find(pet) if self.visit else None
        if gu is not None and not gu.gone:
            self.visit.on_click(gu)

    def fill_menu(self, pet: PetWindow, menu: "QMenu") -> None:
        gu = self.visit.find(pet) if self.visit else None
        if gu is None:
            return
        menu.addAction("💬 말 걸기", lambda: self._talk(gu))
        self.visit.fill_menu(gu, menu)

    def _talk(self, gu: Guest) -> None:
        if not gu.gone and self.visit is not None:
            gu.face(self.game.cursor.x())
            self.visit.say(gu, random.choice(GUEST_TALK.get(gu.key, ["안녕!"])), 3.0)

    def publish(self, key: str | None, answer: str, thrown: bool) -> None:
        """아야가 떠나고 잠시 뒤 붕붕마루 신문 호외 (기사 효과: 새전 수입 증가)."""
        g = self.game
        article = make_article(g.state, key, answer, thrown)
        g.state.news = (g.state.news + [article.headline])[-5:]
        g.state.news_until = time.time() + article.boost_seconds
        g.save()
        log.info("붕붕마루 신문 호외: %s", article.headline)

        def show():
            if g.hidden_for_fullscreen:
                return
            g.show_card(NewsCard(article))
        QTimer.singleShot(int(NEWS_DELAY * 1000), show)
