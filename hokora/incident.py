# -*- coding: utf-8 -*-
"""이변(異変) 해결: 가끔 환상향에 이변이 일어난다. 단서를 모아 흑막을 찾아내고 탄막 승부로 해결한다.

- 신사 2단계부터. 처음 이변은 켠 뒤 20~40분, 그 뒤로는 해결하거나 사라지고 2~4일 뒤.
- 이변이 이어지는 동안 신사 둘레에 이변의 모습이 보이고, 참배객이 줄어 새전 수입 ×0.85.
- 2.5~5분마다 신사 근처에 단서 구슬이 떠오른다 (75초 뒤 사라짐). 눌러서 3개를 모으면 흑막이 나타난다.
- 흑막을 누르거나 우클릭 → ⚔ 탄막 승부 (20초 버티기). 이기면 이변 해결 — 큰 새전과 이변 도감.
- 해결하지 않으면 사흘 뒤 저절로 가라앉는다. UFO 이변 동안은 UFO 가 4배 자주 온다.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from .guests import Flash, Gap, Mist, Visit
from .prayer import INCIDENT_SLUMP
from .render import short_name

if TYPE_CHECKING:
    from PySide6.QtWidgets import QMenu

    from .guests import Guest, Visits
    from .state import GameState


@dataclass(frozen=True)
class Incident:
    key: str
    name: str
    kanji: str
    boss: str
    color: str
    desc: str
    clues: tuple[str, str, str]
    taunt: str
    spell: str
    defeat: str
    after: str

    @property
    def boss_name(self) -> str:
        return short_name(self.boss)


INCIDENTS: dict[str, Incident] = {
    "spring": Incident(
        "spring", "춘설 이변", "春雪異変", "yuyuko", "#F7A8C8",
        "봄이 왔는데도 눈이 그치지 않아요.",
        ("눈 속에 벚꽃잎이 섞여 내려요.", "봄기운이 하늘 위 어딘가로 빨려 가요.",
         "명계의 큰 벚나무를 피우려고 봄을 모으는 누군가가 있어요!"),
        "어머, 여기까지 찾아왔네~ 봄은 조금만 더 빌릴게~", "「반혼접 -팔분 피었다-」",
        "져 버렸네~ 봄은 돌려줄게. 꽃구경은 같이 하자~",
        "모였던 봄기운이 돌아와 늦은 눈이 녹고, 신사 둘레에 벚꽃이 피었다."),
    "night": Incident(
        "night", "영야 이변", "永夜異変", "reisen", "#E04848",
        "밤이 끝나지 않고, 달 모양이 어딘가 이상해요.",
        ("오늘 밤 달이 아주 조금 이지러져 있어요.", "대나무 숲 쪽에서 토끼 발자국이 이어져요.",
         "영원정 사람들이 진짜 달을 숨겨 버렸대요!"),
        "제 눈을 보면 미쳐 버릴 거예요!", "「환파 -마인드 블로잉-」",
        "으으… 스승님께 혼나겠다. 달은 돌려 드릴게요.",
        "가짜 달이 걷히고 진짜 보름달이 떠올랐다. 긴 밤이 드디어 끝났다."),
    "banquet": Incident(
        "banquet", "취몽 이변", "萃夢異変", "suika", "#E8A050",
        "사흘이 멀다 하고 연회가 열리고, 안개가 걷히지 않아요.",
        ("요즘 연회가 너무 자주 열려요.", "안개 속에서 술 냄새가 나요.",
         "흩어진 안개가 한데 모여 작은 사람 모양이 돼요… 오니의 짓이에요!"),
        "들켰네~ 그럼 한판 붙어 볼까!", "「귀신 -미싱 파워-」",
        "하하, 재밌었다! 연회는 이제 적당히 할게~",
        "안개가 걷히고 연회도 잦아들었다. 남은 술은 신사에 봉납되었다."),
    "border": Incident(
        "border", "결계 이변", "結界異変", "yukari", "#9A6AD8",
        "곳곳에 틈이 열리고, 물건이 엉뚱한 곳에서 나와요.",
        ("빗자루가 지붕 위에서 나왔어요.", "허공에 눈이 잔뜩 달린 틈이 보였어요.",
         "경계를 다루는 요괴가 결계를 만지작거리고 있어요!"),
        "어머, 경계를 넘어왔네요. 상대해 드릴게요.", "「자기 -깨달음과 망상의 경계-」",
        "후후, 잘했어요. 결계는 원래대로 돌려 둘게요.",
        "틈이 하나둘 닫히고, 하쿠레이 대결계가 다시 단단해졌다."),
    "ufo": Incident(
        "ufo", "UFO 이변", "星蓮船異変", "nue", "#D03040",
        "하늘에 정체불명의 비행물체가 날아다녀요.",
        ("하늘에 빨갛고 파랗고 초록인 빛이 떠다녀요.", "UFO 조각을 주웠어요… 무늬가 자꾸 바뀌어요.",
         "정체불명의 씨앗! 보는 사람마다 다르게 보이게 하는 요괴예요!"),
        "정체를 알아냈다고? 과연 그럴까~?", "「정체불명 -빨간 UFO 습래-」",
        "쳇, 정체가 들통났네… 오늘은 물러날게.",
        "정체불명의 씨앗이 모두 거둬지고, 하늘의 UFO 도 보이지 않게 되었다."),
}

MIN_STAGE = 2
MULTIPLIER = INCIDENT_SLUMP
CLUES = 3
CLUE_EVERY = (150.0, 300.0)
CLUE_FIRST = 60.0            # 이변이 일어나고 첫 단서까지
CLUE_STAY = 75.0
FIRST_AFTER = (20 * 60.0, 40 * 60.0)
AGAIN_AFTER = (2 * 86400.0, 4 * 86400.0)
EXPIRE = 3 * 86400.0
BOSS_AGAIN = 300.0           # 흑막이 돌아간 뒤 다시 나타나기까지
BOSS_STAY = 120.0
UFO_BOOST = 4.0
LAUGH = ["아직 멀었네~ 또 와!", "후후, 그 정도로는 안 돼.", "한 번 더 해 볼래?"]


def active(s: "GameState") -> Incident | None:
    return INCIDENTS.get(s.incident)


def multiplier(s: "GameState") -> float:
    return MULTIPLIER if s.incident in INCIDENTS else 1.0


def ufo_boost(s: "GameState") -> float:
    return UFO_BOOST if s.incident == "ufo" else 1.0


def start(s: "GameState", key: str, now: float | None = None) -> Incident:
    s.incident, s.incident_since, s.incident_clues = key, now or time.time(), 0
    return INCIDENTS[key]


def roll(s: "GameState", now: float | None = None, rng: random.Random | None = None) -> Incident | None:
    """때가 되면 이변을 일으킨다 (일어난 이변을 돌려줌)."""
    now = now or time.time()
    rng = rng or random.Random()
    if s.incident or s.shrine_level < MIN_STAGE:
        return None
    if not s.incident_next:
        s.incident_next = now + rng.uniform(*FIRST_AFTER)
        return None
    if now < s.incident_next:
        return None
    return start(s, rng.choice(list(INCIDENTS)), now)


def _calm(s: "GameState", now: float, rng: random.Random | None = None) -> None:
    s.incident, s.incident_since, s.incident_clues = "", 0.0, 0
    s.incident_next = now + (rng or random.Random()).uniform(*AGAIN_AFTER)


def expire(s: "GameState", now: float | None = None) -> Incident | None:
    """사흘이 지나면 저절로 가라앉음 (가라앉은 이변을 돌려줌)."""
    now = now or time.time()
    inc = active(s)
    if inc is None or now - s.incident_since < EXPIRE:
        return None
    _calm(s, now)
    return inc


def add_clue(s: "GameState") -> int:
    if s.incident in INCIDENTS:
        s.incident_clues = min(CLUES, s.incident_clues + 1)
    return s.incident_clues


def ready(s: "GameState") -> bool:
    return s.incident in INCIDENTS and s.incident_clues >= CLUES


def reward(s: "GameState") -> int:
    return max(3000, s.income_per_min * 240)


def solve(s: "GameState", now: float | None = None) -> tuple[Incident, int] | None:
    """흑막을 이김 → (해결한 이변, 받은 새전)."""
    inc = active(s)
    if inc is None:
        return None
    amount = reward(s)
    s.add_saisen(amount)
    s.incidents_solved[inc.key] = s.incidents_solved.get(inc.key, 0) + 1
    _calm(s, now or time.time())
    return inc, amount


def solved_total(s: "GameState") -> int:
    return sum(s.incidents_solved.values())


# ── 신사 둘레의 이변 모습 (클릭은 통과) ──
class IncidentFx(QWidget):
    W, H = 760, 320

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(self.W, self.H)
        self.kind = ""
        self.rng = random.Random()
        self.flakes: list[list[float]] = []      # [x, y, 속도, 흔들림 위상, 꽃잎?]
        self.start = time.monotonic()
        self._last = self.start
        self._pos = None
        self.timer = QTimer(self, timeout=self._tick, interval=50)

    def set_kind(self, kind: str) -> None:
        if kind != self.kind:
            self.kind = kind
            self.flakes.clear()
            self.update()

    def follow(self, cx: float, ground: float) -> None:
        pos = (round(cx - self.W / 2), round(ground - self.H + 4))
        if pos != self._pos:
            self._pos = pos
            self.move(*pos)

    def showEvent(self, e) -> None:
        self._last = time.monotonic()
        self.timer.start()
        super().showEvent(e)

    def hideEvent(self, e) -> None:
        self.timer.stop()
        super().hideEvent(e)

    def _tick(self) -> None:
        now = time.monotonic()
        dt, self._last = min(now - self._last, 0.2), now
        if self.kind == "spring":
            while len(self.flakes) < 34:
                self.flakes.append([self.rng.uniform(0, self.W), self.rng.uniform(-20, self.H - 10),   # 처음부터 퍼져 있게
                                    self.rng.uniform(26, 50), self.rng.uniform(0, math.tau), self.rng.random() < 0.3])
            for f in self.flakes:
                f[1] += f[2] * dt
                f[0] += math.sin(now * 1.3 + f[3]) * 14 * dt
                if f[1] > self.H - 6:
                    f[0], f[1] = self.rng.uniform(0, self.W), self.rng.uniform(-40, -4)
        self.update()

    def paintEvent(self, _e) -> None:
        if not self.kind:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = time.monotonic() - self.start
        getattr(self, f"_paint_{self.kind}", lambda *_: None)(p, t)
        p.end()

    def _paint_spring(self, p: QPainter, t: float) -> None:
        p.setPen(Qt.NoPen)
        for x, y, _v, ph, petal in self.flakes:
            if petal:
                p.save()
                p.translate(x, y)
                p.rotate(math.degrees(math.sin(t * 2 + ph)))
                p.setBrush(QColor(247, 168, 200, 210))
                p.drawEllipse(QRectF(-4, -2.5, 8, 5))
                p.restore()
            else:
                p.setBrush(QColor(255, 255, 255, 220))
                p.drawEllipse(QPointF(x, y), 2.4, 2.4)

    def _paint_night(self, p: QPainter, t: float) -> None:
        g = QRadialGradient(QPointF(self.W / 2, self.H), self.W * 0.6)
        g.setColorAt(0, QColor(20, 18, 60, 70))
        g.setColorAt(1, QColor(20, 18, 60, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRect(QRectF(0, 0, self.W, self.H))
        c = QPointF(self.W - 110, 64)                          # 가짜 달: 조금 이지러지고 붉은 기
        halo = QRadialGradient(c, 60)
        halo.setColorAt(0, QColor(255, 220, 200, 90))
        halo.setColorAt(1, QColor(255, 220, 200, 0))
        p.setBrush(halo)
        p.drawEllipse(c, 60, 60)
        moon = QPainterPath()
        moon.addEllipse(c, 30, 30)
        bite = QPainterPath()
        bite.addEllipse(QPointF(c.x() + 22 + 3 * math.sin(t * 0.4), c.y() - 6), 22, 26)
        p.setBrush(QColor(255, 236, 214, 235))
        p.drawPath(moon.subtracted(bite))

    def _paint_banquet(self, p: QPainter, t: float) -> None:
        p.setPen(Qt.NoPen)
        for i in range(9):
            x = (i * 97 + t * (10 + i * 2)) % (self.W + 160) - 80
            y = self.H - 30 - (i % 3) * 22 + 6 * math.sin(t * 0.7 + i)
            r = 46 + (i % 4) * 12
            g = QRadialGradient(QPointF(x, y), r)
            g.setColorAt(0, QColor(236, 214, 226, 80))
            g.setColorAt(1, QColor(236, 214, 226, 0))
            p.setBrush(g)
            p.drawEllipse(QPointF(x, y), r, r * 0.6)

    def _paint_border(self, p: QPainter, t: float) -> None:
        for i, (fx, fy) in enumerate(((0.18, 0.32), (0.8, 0.22), (0.62, 0.55))):
            open_ = max(0.0, math.sin(t * 0.6 + i * 2.1))
            if open_ < 0.05:
                continue
            cx, cy, w, h = self.W * fx, self.H * fy, 70.0, 26 * open_
            path = QPainterPath(QPointF(cx - w / 2, cy))
            path.quadTo(QPointF(cx, cy - h), QPointF(cx + w / 2, cy))
            path.quadTo(QPointF(cx, cy + h), QPointF(cx - w / 2, cy))
            p.setPen(QPen(QColor(200, 30, 60, 200), 2))
            p.setBrush(QColor(40, 10, 60, 210))
            p.drawPath(path)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(230, 40, 60, int(220 * open_)))
            for k in range(3):
                ex = cx - 18 + k * 18
                p.drawEllipse(QPointF(ex, cy + 2 * math.sin(t + k)), 3.5, 2.2 * open_ + 0.6)

    def _paint_ufo(self, p: QPainter, t: float) -> None:
        for i, color in enumerate(("#E04848", "#3D8AE0", "#3FC070")):
            x = self.W * (0.2 + 0.3 * i) + 120 * math.sin(t * (0.5 + 0.17 * i) + i)
            y = 40 + 20 * i + 14 * math.sin(t * 1.3 + i * 2)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            p.drawEllipse(QPointF(x, y), 16, 5)
            p.setBrush(QColor(255, 255, 255, 170))
            p.drawEllipse(QPointF(x, y - 4), 6, 4)
            if int(t * 3 + i) % 2:
                p.setBrush(QColor(255, 240, 160, 230))
                p.drawEllipse(QPointF(x, y + 1), 2, 2)


# ── 단서 구슬 ──
class ClueWindow(QWidget):
    """둥실 떠 있는 단서 구슬. 누르면 on_take, 가만두면 CLUE_STAY 뒤 사라짐."""

    S = 64

    def __init__(self, inc: Incident, on_take: Callable[["ClueWindow"], None], stay: float = CLUE_STAY):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.S, self.S)
        self.setToolTip(f"{inc.name}의 단서 — 눌러서 줍기")
        self.inc, self.on_take, self.stay = inc, on_take, stay
        self.born = time.monotonic()
        self.taken = False
        self.timer = QTimer(self, timeout=self._tick, interval=40)
        self.timer.start()

    @property
    def age(self) -> float:
        return time.monotonic() - self.born

    def _tick(self) -> None:
        if self.age >= self.stay:
            self.timer.stop()
            self.close()
            return
        self.update()

    def mousePressEvent(self, _e) -> None:
        if not self.taken:
            self.taken = True
            self.timer.stop()
            self.on_take(self)
            self.close()

    def paintEvent(self, _e) -> None:
        a = self.age
        alpha = min(1.0, a / 0.6, max(0.0, (self.stay - a) / 3.0))
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(alpha)
        c = QPointF(self.S / 2, self.S / 2 + 5 * math.sin(a * 2.2))
        base = QColor(self.inc.color)
        glow = QRadialGradient(c, self.S / 2)
        glow.setColorAt(0, QColor(base.red(), base.green(), base.blue(), 150))
        glow.setColorAt(1, QColor(base.red(), base.green(), base.blue(), 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(c, self.S / 2, self.S / 2)
        orb = QRadialGradient(QPointF(c.x() - 5, c.y() - 6), 18)
        orb.setColorAt(0, QColor("#FFFFFF"))
        orb.setColorAt(0.35, base.lighter(130))
        orb.setColorAt(1, base.darker(120))
        p.setBrush(orb)
        p.drawEllipse(c, 14, 14)
        p.setPen(QColor("#FFFFFF"))
        f = QFont("Malgun Gothic", 11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(c.x() - 14, c.y() - 14, 28, 28), Qt.AlignCenter, "?")
        p.end()


# ── 흑막 등장 (손님 방문처럼) ──
class IncidentVisit(Visit):
    kind = "incident"

    def __init__(self, visits: "Visits"):
        super().__init__(visits)
        g, sx = self.ground, self.game.shrine.pos_x
        self.inc = active(self.game.state) or INCIDENTS["spring"]
        side = random.choice((-1, 1))
        x = min(max(sx + side * (self.game.shrine.width() / 2 + 110), g.x1 + 40), g.x2 - 40)
        if self.inc.boss == "yukari":
            self.effect(Gap(x, g.y, 2.2))
        elif self.inc.boss == "suika":
            self.effect(Mist(x, g.y))
        else:
            self.effect(Flash(x, g.y - 40))
        self.boss = self.spawn(self.inc.boss, x)
        self.boss.fade(1.0, 1.0)
        self.boss.face(sx)
        now = time.monotonic()
        self.phase, self.next_at = "taunt", now + 1.2
        self.fighting = False
        self.won = False
        self.tries = 0
        self.at(0.8, lambda: self.say(self.boss, f"⚠ {self.inc.name}의 흑막!  {self.inc.taunt}", 3.4))

    def update(self, now: float) -> None:
        b = self.boss
        if b.gone or self.fighting or not b.ready:
            return
        if self.phase == "taunt" and now >= self.next_at:
            b.pet.act("skill", 1.6)
            self.phase, self.next_at = "wait", now + 5.0
        elif self.phase == "wait":
            if now - self.started > BOSS_STAY:
                self.phase = "bye"
                self.say(b, "오늘은 이만~ 다음에 또 보자!", 2.6)
                self.at(2.0, lambda: self.leave(b, 1.0))
            elif now >= self.next_at:
                self.next_at = now + random.uniform(12, 16)
                self.say(b, random.choice(["눌러서 ⚔ 탄막 승부!", "덤벼 보시지!", "이변을 멈추고 싶으면 날 이겨 봐!"]))

    def fight(self) -> bool:
        if self.fighting or self.phase not in ("taunt", "wait") or self.boss.gone:
            return False
        if not self.game.start_dodge(self.inc.boss, boss=True, on_end=self._fought,
                                     near=self.boss.pet.pos_x):
            return False
        self.fighting = True
        self.tries += 1
        self.boss.face(self.game.cursor.x())
        self.say(self.boss, self.inc.spell, 2.4)
        return True

    def _fought(self, won: bool, hits: int) -> None:
        self.fighting = False
        b = self.boss
        self.game.incident_fight_end(won, hits)
        if b.gone:
            return
        if won:
            self.won = True
            self.phase = "beaten"
            b.pet.act("caught", 1.6)
            self.say(b, self.inc.defeat, 3.4)
            self.at(3.6, lambda: self.leave(b, 1.0))
        else:
            b.pet.act("happy", 1.4)
            self.say(b, random.choice(LAUGH))
            self.next_at = time.monotonic() + 6.0

    def on_click(self, gu: "Guest") -> None:
        if not self.fight() and self.phase == "beaten":
            self.say(gu, "약속은 지킬게~")

    def fill_menu(self, gu: "Guest", menu: "QMenu") -> None:
        if self.phase in ("taunt", "wait"):
            menu.addSeparator()
            a = menu.addAction(f"⚔ 탄막 승부!  ({self.inc.name})", self.fight)
            a.setEnabled(not self.fighting)

    def finish(self) -> None:
        self.game.incident_boss_left(self.won)
