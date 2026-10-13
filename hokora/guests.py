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

from PySide6.QtCore import QAbstractAnimation, QPointF, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from . import affection as aff
from . import omamori, season, wardrobe, weather
from .decor import decor_image
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
    "tewi": (("tewi",), 1),
    "koishi": (("koishi",), 2),
    "nitori": (("nitori",), 3),
    "yuyuko": (("yuyuko",), 2),
    "mystia": (("mystia",), 1),        # 밤에만
    "reisen": (("reisen",), 2),
    "patchouli": (("patchouli",), 2),
    "yukari": (("yukari",), 3),
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
TEWI_STAY = 40.0
KOISHI_STAY = 60.0
KOISHI_ALPHA = 0.22       # 코이시가 보이는 정도 (무의식 — 거의 투명)
NITORI_STAY = 70.0
YUYUKO_STAY = 75.0
YUYUKO_FOODS = {  # 키 → (아이콘, 이름, 배부름, 값(× 신사 단계)). 배부름 100 이면 만족
    "onigiri": ("🍙", "주먹밥", 20, 50),
    "dango": ("🍡", "경단", 35, 120),
    "bento": ("🍱", "도시락", 60, 250),
}
MYSTIA_STAY = 90.0
MYSTIA_MENU = {  # 키 → (아이콘, 이름, 설명)
    "kabayaki": ("🐟", "장어구이", "30분 동안 새전 수입 ×1.3"),
    "oden": ("🍢", "오뎅", "친구 모두 호감도 +2"),
    "song": ("🎵", "미스티아의 노래", "옷감 +10, 다들 신나게"),
}


PATCHY_STAY = 80.0
PATCHY_SPELLS = {  # 키 → (날씨, 아이콘, 이름, 설명, 시간(초))
    "clear": ("clear", "☀", "쾌청 마법", "1시간 동안 쾌청 (수입 ×1.2)", 3600),
    "sunshower": ("sunshower", "🌈", "여우비 마법", "1시간 동안 여우비 (오미쿠지 행운)", 3600),
    "fog": ("fog", "🌫", "안개 마법", "1시간 동안 짙은 안개 (손님 ×2)", 3600),
    "aurora": ("aurora", "✨", "오로라 마법", "30분 동안 오로라 (수입 ×2)", 1800),
}
YUKARI_STAY = 60.0
YUKARI_TRICKS = 3


def patchy_price(s, key: str) -> int:
    per = max(5, s.income_per_min)
    return {"clear": per * 10, "sunshower": 150 * s.shrine_level, "fog": 120 * s.shrine_level,
            "aurora": per * 25}[key]


REISEN_STAY = 70.0
REISEN_MEDS = {  # 키 → (아이콘, 이름, 설명)
    "energy": ("💊", "피로회복약", "1시간 동안 쓰다듬기 새전 ×2"),
    "dream": ("🌙", "꿈나라 약", "다음에 꺼져 있는 동안 새전함 2배"),
    "luck": ("🍀", "행운의 약", "다음 오미쿠지가 대길 쪽으로"),
}


def reisen_price(s, key: str) -> int:
    if key == "energy":
        return max(100, s.income_per_min * 15)
    return (300 if key == "dream" else 200) * s.shrine_level


def mystia_price(s, key: str) -> int:
    if key == "kabayaki":
        return max(150, s.income_per_min * 40)
    return (100 if key == "oden" else 150) * s.shrine_level
NITORI_GOODS = {  # 니토리 노점: 키 → (아이콘, 이름, 설명). 들를 때마다 셋을 골라 펼침
    "fan": ("⚡", "증기 선풍기", "30분 동안 새전 수입 ×1.5"),
    "cloth": ("🧵", "옷감 묶음", "옷감 +30"),
    "charm": ("🎴", "부적 뽑기 1번", "20% 할인"),
    "outfit": ("👘", "의상실 뽑기 1번", "20% 할인"),
    "cucumber": ("🥒", "오이", "니토리가 좋아해요 — 나머지 물건 반값!"),
}


def nitori_price(s, key: str) -> int:
    if key == "fan":
        return max(200, s.income_per_min * 60)
    if key == "cloth":
        return 3000 * s.shrine_level
    if key == "charm":
        return int(omamori.price(s) * 0.8)
    if key == "outfit":
        return int(wardrobe.price(s) * 0.8)
    return 100

GUEST_TALK = {
    "sunny": ["우린 장난 안 쳤어! …아마도.", "서니 밀크! 빛의 요정이야!", "안 보였지? 헤헤."],
    "luna": ["쉿… 조용히 해 줘.", "루나 차일드예요. 소리를 지울 수 있어요.", "…다음엔 안 들킬 거예요."],
    "star": ["스타 사파이어야. 다 느껴진다구.", "너 방금 이쪽으로 오고 있었지?", "도망가는 건 내가 제일 빨라!"],
    "aya": ["붕붕마루 신문, 한 부 어떠세요?", "특종 냄새가 나요!", "이 신사, 기사거리가 많네요."],
    "suika": ["한 잔 할래~?", "오니는 거짓말 안 해!", "여기 술맛 좋다~ 딸꾹!"],
    "tewi": ["행운이 필요해? 대가는 당근이야~", "함정? 무슨 함정~?", "이나바 테위, 오래 산 토끼야!"],
    "koishi": ["……어라, 나 보여?", "무의식이 이끄는 대로~", "언니한테는 비밀이야."],
    "nitori": ["맹우! 뭐 필요한 거 있어?", "갓파의 기술은 세계 제일!", "오이 있으면 줘~"],
    "yuyuko": ["배고파~ 뭐 먹을 거 없어?", "요우무는 잘 지내려나~", "꽃구경엔 경단이지~"],
    "mystia": ["어서 와요~ 오늘은 장어가 맛있어요!", "♪ 밤참은 포장마차에서~", "참새는 굽지 않아요!"],
    "reisen": ["영원정 약 배달 왔어요.", "테위 못 봤어요? 또 땡땡이를…", "스승님 약은 잘 들어요!"],
    "patchouli": ["…책 읽는 중이야.", "도서관 밖은 공기가 안 좋아… 콜록.", "마리사가 빌려 간 책, 못 봤어?"],
    "yukari": ["어머, 경계 너머에서 실례할게요.", "환상향은 모든 것을 받아들이죠.", "레이무는 잘 지내나요? 후후."],
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
    "tewi": ("행운을 나눠 주는 장난꾸러기 토끼", "함정을 파요. 쓰다듬으면 오미쿠지 행운"),
    "koishi": ("무의식으로 다니는 사토리 요괴", "거의 투명하게 숨어 있어요 — 찾아서 클릭!"),
    "nitori": ("발명품을 파는 갓파 엔지니어", "노점에서 선풍기·옷감·뽑기를 팔아요"),
    "yuyuko": ("배고픈 명계의 아가씨", "먹을 걸 대접하면 새전을 두고 가요 (3번이면 요우무가)"),
    "mystia": ("밤에만 여는 포장마차 주인", "장어구이·오뎅·노래를 팔아요"),
    "reisen": ("영원정의 약 행상 토끼", "피로회복약·꿈나라 약·행운의 약을 팔아요"),
    "patchouli": ("도서관에서 나온 마법사", "새전을 받고 날씨를 바꾸는 마법을 걸어 줘요"),
    "yukari": ("경계를 다루는 요괴", "틈(스키마)으로 친구들을 엉뚱한 곳에 옮겨요"),
}
INTERVIEW_Q = ["최근 새전 사정은 어떤가요?", "독자들께 한 말씀 부탁드려요!", "요즘 신사에 무슨 일이 있었나요?"]
DRINK_WITH = {  # 스이카가 한 잔 권했을 때
    "reimu": "…낮술은 좀 그렇지 않아?", "marisa": "오, 좋지! 한 잔만!", "cirno": "얼음 넣어 줄까?",
    "sakuya": "근무 중이라서요.", "sanae": "미성년자는 안 돼요!", "remilia": "와인이라면 몰라도.",
    "flandre": "나도 마실래!", "youmu": "근무 중이라… 한 잔만이요.",
}


def available(s) -> list[str]:
    """지금 신사 단계에 찾아올 수 있는 방문 종류 (미스티아는 밤에만)."""
    return [k for k, (_, stage) in VISITS.items()
            if s.shrine_level >= stage and (k != "mystia" or season.is_night())]


def fade(w: QWidget, to: float, seconds: float, then: Callable[[], None] | None = None) -> None:
    """창을 서서히 나타내거나 사라지게."""
    anim = QPropertyAnimation(w, b"windowOpacity", w)
    anim.setDuration(int(seconds * 1000))
    anim.setStartValue(w.windowOpacity())
    anim.setEndValue(to)
    if then is not None:
        anim.finished.connect(then)
    anim.start(QAbstractAnimation.DeleteWhenStopped)


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


class Pit(_Overlay):
    """테위가 판 함정 구멍."""

    def __init__(self, cx: float, ground: float, seconds: float):
        super().__init__(46, 16, seconds)
        self.timer.setInterval(400)                        # 거의 안 변하니 드물게
        self.move(round(cx - 23), round(ground - 10))

    def paintEvent(self, _e) -> None:
        a = 1.0 if self.age < 0.92 else max(0.0, (1 - self.age) / 0.08)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(140, 98, 58, int(230 * a)))     # 파낸 흙
        p.drawEllipse(QPointF(23, 9), 22, 6)
        p.setBrush(QColor(42, 28, 20, int(240 * a)))      # 구멍
        p.drawEllipse(QPointF(23, 9.5), 15, 3.8)
        p.end()


class Stall(QWidget):
    """미스티아의 포장마차 (클릭은 통과)."""

    H = 96

    def __init__(self, cx: float, ground: float, k: float):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.img = decor_image("yatai")
        h = self.H * k
        w = self.img.width() * h / max(1, self.img.height())
        self.setFixedSize(max(10, round(w)), round(h) + 2)
        self.move(round(cx - w / 2), round(ground - h))
        self.setWindowOpacity(0.0)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(QRectF(0, 0, self.width(), self.height() - 2), self.img)
        p.end()


class Gap(_Overlay):
    """유카리의 틈(스키마): 보라색 틈이 열렸다 닫힘, 양끝에 빨간 리본, 안에서 눈이 내다봄."""

    def __init__(self, cx: float, ground: float, seconds: float = 2.2, h: float = 86):
        super().__init__(70, int(h) + 24, seconds)
        self.move(round(cx - 35), round(ground - h - 12))
        self.h = h
        self.eyes = [(random.uniform(-6, 6), random.uniform(0.25, 0.75)) for _ in range(3)]

    def paintEvent(self, _e) -> None:
        a = self.age
        open_ = min(1.0, a / 0.15) if a < 0.8 else max(0.0, (1 - a) / 0.2)
        cx, top, h = 35.0, 12.0, self.h
        wd = 13 * open_
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if wd > 0.5:
            path = QPainterPath()
            path.moveTo(cx, top)
            path.quadTo(cx + wd * 2, top + h / 2, cx, top + h)
            path.quadTo(cx - wd * 2, top + h / 2, cx, top)
            p.setPen(QPen(QColor(120, 70, 170), 1.6))
            p.setBrush(QColor(40, 14, 60, 235))
            p.drawPath(path)
            for ex, ey in self.eyes:                          # 안에서 내다보는 눈
                y = top + h * ey
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(250, 236, 200, int(230 * open_)))
                p.drawEllipse(QPointF(cx + ex * open_, y), 4.2 * open_, 2.4 * open_)
                p.setBrush(QColor(170, 30, 50, int(240 * open_)))
                p.drawEllipse(QPointF(cx + ex * open_, y), 1.5 * open_, 1.5 * open_)
        p.setPen(Qt.NoPen)                                    # 양끝 리본
        p.setBrush(QColor(200, 30, 50, int(255 * max(open_, 0.0))))
        for y in (top, top + h):
            p.drawEllipse(QPointF(cx - 5, y), 5, 3.4)
            p.drawEllipse(QPointF(cx + 5, y), 5, 3.4)
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
        fade(self.pet, to, seconds, then)


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


# ── 테위: 함정을 파고, 쓰다듬으면 행운 ──
class TewiVisit(Visit):
    kind = "tewi"

    def __init__(self, visits: "Visits"):
        super().__init__(visits)
        g, sx = self.ground, self.game.shrine.pos_x
        self.side = random.choice((-1, 1))
        clamp = lambda x: min(max(x, g.x1 + 30), g.x2 - 30)   # noqa: E731
        self.tewi = self.spawn("tewi", clamp(sx + self.side * 400))
        self.tewi.fade(1.0, 0.6)
        self.tewi.go(clamp(sx + self.side * 150), 90, run=True)
        now = time.monotonic()
        self.phase, self.until, self.leave_at = "enter", now + 8, now + TEWI_STAY
        self.pit_x: float | None = None
        self.trapped = False
        self.lucky = False
        self._held = False
        self._lure_at = 0.0
        self.at(0.6, lambda: self.say(self.tewi, "행운의 토끼님 납셨다~"))

    def _idle_after(self, seconds: float) -> None:
        p = self.tewi.pet
        self.at(seconds, lambda: self.phase != "bye" and p.state not in ("held", "fall") and p.act("idle", 99))

    def update(self, now: float) -> None:
        t = self.tewi
        if t.gone:
            return
        p = t.pet
        if p.state == "held":
            self._held = True
        if not t.ready:
            return
        if self._held:
            self._held = False
            p.act("caught", 1.2)
            self.say(t, "놓아줘~ 행운 안 준다!")
            self._idle_after(1.2)
        if now >= self.leave_at and self.phase != "bye":
            return self._bye()
        if self.phase == "enter" and (t.arrived() or now >= self.until):
            t.goal = None
            t.face(self.game.shrine.pos_x)
            p.act("skill", 2.6)                               # 삽을 들고 → 땅을 팜
            self.say(t, "여기에 구멍을 파 볼까~")
            self.phase, self.until = "dig", now + 2.6
        elif self.phase == "dig" and now >= self.until:
            self.pit_x = p.pos_x + p.facing * 30
            self.effect(Pit(self.pit_x, self.ground.y, self.leave_at - now + 1.0))
            p.act("happy", 1.0)
            self.say(t, "헤헤, 함정 완성!")
            self._idle_after(1.0)
            self.phase, self._lure_at = "wait", now + 8
        elif self.phase == "wait" and not self.trapped:
            self._check_pit(now)

    def _check_pit(self, now: float) -> None:
        g = self.ground
        for o in self.game.pets:
            if o.grounded and o.on == g.hwnd and abs(o.pos_x - self.pit_x) < 12:
                self.trapped = True                           # 걸렸다!
                o.pos_x = self.pit_x
                o.act("caught", 1.8)
                o.squash = 0.3
                self.game.events._say(o, "으앗! 함정이다!")
                self.tewi.face(o.pos_x)
                self.tewi.pet.act("happy", 1.2)
                self.at(0.9, lambda: self.say(self.tewi, "헤헤~ 걸렸다 걸렸어!"))
                self._idle_after(1.2)
                return
        if now >= self._lure_at:                              # 아무도 안 오면 가까운 친구를 꾐
            self._lure_at = now + 9
            near = [o for o in self.game.pets if o.grounded and o.on == g.hwnd]
            if near:
                o = min(near, key=lambda o: abs(o.pos_x - self.pit_x))
                d = 1 if self.pit_x > o.pos_x else -1
                o.act("walk", min(8.0, abs(self.pit_x - o.pos_x) / 30 + 1), vx=d * 30)
                self.say(self.tewi, "저기 당근이 떨어져 있네~?")

    def _bye(self) -> None:
        self.phase = "bye"
        t, g = self.tewi, self.ground
        self.say(t, "그럼 안녕~ 깡총!")
        t.go(g.x2 - 20 if self.side > 0 else g.x1 + 20, 110, run=True)
        self.at(3.5, lambda: self.leave(t, 0.6))

    def on_click(self, gu: Guest) -> None:
        if self.lucky:
            self.say(gu, random.choice(["행운은 한 번만~", "헤헤, 또 만지면 함정 판다?"]))
            return
        self.lucky = True
        g, s = self.game, self.game.state
        s.tewi_luck += 1
        if not s.fate_boost:
            s.fate_boost = True
            line = "행운을 나눠 줄게! 다음 오미쿠지는 대길 쪽으로~"
        else:
            amount = max(30, s.income_per_min * 10)
            s.add_saisen(amount)
            g.shrine.set_saisen(s.saisen)
            g.shrine.pop(f"+{amount:,}")
            line = f"행운 듬뿍! 새전 +{amount:,}"
        gu.pet.act("happy", 1.2)
        self._idle_after(1.2)
        self.say(gu, line, 3.0)
        g.save()


# ── 코이시: 거의 투명하게 숨어 다님, 찾아서 클릭하면 선물 ──
class KoishiVisit(Visit):
    kind = "koishi"

    def __init__(self, visits: "Visits"):
        super().__init__(visits)
        g, sx = self.ground, self.game.shrine.pos_x
        spots = [x for x in (random.uniform(g.x1 + 60, g.x2 - 60) for _ in range(12)) if abs(x - sx) > 220]
        self.koishi = self.spawn("koishi", spots[0] if spots else random.uniform(g.x1 + 60, g.x2 - 60))
        self.koishi.fade(KOISHI_ALPHA, 2.0)
        now = time.monotonic()
        self.found = False
        self.leave_at = now + KOISHI_STAY
        self.next_at = now + 2.0
        self.peek_at = now + random.uniform(6, 10)
        self.hint_at = now + random.uniform(12, 20)

    def update(self, now: float) -> None:
        k = self.koishi
        if k.gone or self.found:
            return
        p = k.pet
        if p.state == "held":                                 # 붙잡아도 찾은 것
            return self._found()
        if not k.ready:
            return
        if now >= self.leave_at:                              # 아무도 못 찾음 → 조용히
            self.leave(k, 1.5)
            return
        if now >= self.peek_at:                               # 깜빡 보였다가 다시 사라짐
            self.peek_at = now + random.uniform(7, 12)
            k.fade(0.5, 0.5, lambda: not self.found and not k.gone and k.fade(KOISHI_ALPHA, 1.2))
        if now >= self.hint_at:                               # 친구가 낌새를 챔
            self.hint_at = now + random.uniform(15, 22)
            near = [o for o in self.game.pets if o.grounded and abs(o.pos_x - p.pos_x) < 300]
            if near:
                o = random.choice(near)
                o.facing = 1 if p.pos_x > o.pos_x else -1
                self.game.events._say(o, random.choice(["……? 방금 누가 있었는데", "어라, 기분 탓인가?", "누구 있어?"]))
        if now >= self.next_at:
            r = random.random()
            if r < 0.45:
                secs = random.uniform(2.5, 4)
                p.act("walk", 99, vx=random.choice((-1, 1)) * random.uniform(16, 22))
            elif r < 0.7 and self.game.pets:
                o = random.choice(self.game.pets)
                k.go(o.pos_x - o.facing * 30, 24)             # 친구 바로 뒤에 슬쩍
                secs = 5.0
            else:
                p.act("idle", 99)
                secs = random.uniform(2, 4)
            self.next_at = now + secs

    def _found(self) -> None:
        if self.found:
            return
        self.found = True
        k, g, s = self.koishi, self.game, self.game.state
        k.goal = None
        k.fade(1.0, 0.25)
        if k.pet.state != "held":
            k.pet.act("skill", 1.4)                           # 쉿 → "까꿍!"
        s.koishi_found += 1
        r = random.random()
        if r < 0.5:
            n = 10 * s.shrine_level
            s.cloth += n
            prize = f"옷감 +{n}"
        elif r < 0.8:
            s.saisen += omamori.price(s)                      # 부적 한 번 공짜
            res = omamori.pull(s, 1)
            prize = omamori.CHARMS[res[0][0]].name
        else:
            amount = max(50, s.income_per_min * 30)
            s.add_saisen(amount)
            prize = f"새전 +{amount:,}"
        g.shrine.set_saisen(s.saisen)
        self.say(k, "들켰다~! 대단해!", 2.2)
        self.at(2.3, lambda: self.say(k, f"찾아낸 선물: {prize}", 3.0))
        self.at(1.4, lambda: k.pet.state != "held" and k.pet.act("happy", 99))
        self.at(5.5, lambda: self.leave(k, 1.0))
        log.info("코이시 찾음: %s", prize)
        g.save()

    def on_click(self, gu: Guest) -> None:
        self._found()


# ── 니토리: 갓파 노점 ──
class NitoriVisit(Visit):
    kind = "nitori"

    def __init__(self, visits: "Visits"):
        super().__init__(visits)
        g, sx = self.ground, self.game.shrine.pos_x
        self.side = 1 if (g.x2 - sx) > (sx - g.x1) else -1
        clamp = lambda x: min(max(x, g.x1 + 30), g.x2 - 30)   # noqa: E731
        self.nitori = self.spawn("nitori", clamp(sx + self.side * 420))
        self.nitori.fade(1.0, 0.6)
        self.nitori.go(clamp(sx + self.side * 120), 60)
        self.goods = random.sample(sorted(NITORI_GOODS), 3)
        self.sold: set[str] = set()
        self.half = False
        self._held = False
        now = time.monotonic()
        self.phase, self.until, self.leave_at, self.shout_at = "enter", now + 10, now + NITORI_STAY, 0.0

    def _pose(self, seconds: float = 1.6) -> None:
        p = self.nitori.pet
        p.act("skill", seconds)                               # 렌치 → 발명품 자랑
        self.at(seconds, lambda: self.phase != "bye" and p.state not in ("held", "fall") and p.act("idle", 99))

    def update(self, now: float) -> None:
        n = self.nitori
        if n.gone:
            return
        p = n.pet
        if p.state == "held":
            self._held = True
        if not n.ready:
            return
        if self._held:
            self._held = False
            p.act("caught", 1.2)
            self.say(n, "으앗, 물건 쏟아진다~!")
            self.at(1.2, lambda: self.phase != "bye" and p.act("idle", 99))
        if self.phase == "enter" and (n.arrived() or now >= self.until):
            n.goal = None
            n.face(self.game.shrine.pos_x)
            self._pose()
            self.say(n, "갓파 노점 개업! 우클릭해서 구경해~", 3.5)
            self.phase, self.shout_at = "shop", now + 14
        elif self.phase == "shop":
            if now >= self.leave_at or len(self.sold) == len(self.goods):
                self._bye()
            elif now >= self.shout_at:
                self.shout_at = now + random.uniform(12, 18)
                self._pose()
                self.say(n, random.choice(["싸다 싸~! 맹우 특가!", "갓파 기술의 결정체!", "오늘만 이 가격이야~"]))

    def _bye(self) -> None:
        self.phase = "bye"
        n, g = self.nitori, self.ground
        self.say(n, "또 올게, 맹우~!" if self.sold else "다음엔 꼭 사 줘~")
        self.at(1.2, lambda: n.go(g.x2 - 20 if self.side > 0 else g.x1 + 20, 70))
        self.at(5.0, lambda: self.leave(n, 0.8))

    def price(self, key: str) -> int:
        base = nitori_price(self.game.state, key)
        return base // 2 if self.half and key != "cucumber" else base

    def fill_menu(self, gu: Guest, menu: "QMenu") -> None:
        if self.phase != "shop":
            return
        menu.addSeparator()
        head = menu.addAction("🛒 갓파 노점")
        head.setEnabled(False)
        for key in self.goods:
            icon, name, desc = NITORI_GOODS[key]
            price = self.price(key)
            sold = key in self.sold
            a = menu.addAction(f"{icon} {name} — 다 팔림" if sold else f"{icon} {name}  ({desc})   새전 {price:,}",
                               lambda key=key: self.buy(key))
            a.setEnabled(not sold and self.game.state.saisen >= price)

    def buy(self, key: str) -> bool:
        g, s = self.game, self.game.state
        price = self.price(key)
        if key in self.sold or self.phase != "shop" or s.saisen < price:
            return False
        s.saisen -= price
        self.sold.add(key)
        if key == "fan":
            s.nitori_until = time.time() + 1800
            line = "증기 선풍기 가동! 30분 동안 수입 ×1.5"
        elif key == "cloth":
            s.cloth += 30
            line = "옷감 30장, 잘 써~"
        elif key == "charm":
            s.saisen += omamori.price(s)
            res = omamori.pull(s, 1)
            line = f"🎴 {aff.josa(omamori.CHARMS[res[0][0]].name, '이', '가')} 나왔어!"
        elif key == "outfit":
            s.saisen += wardrobe.price(s)
            res = wardrobe.pull(s, 1)
            it = wardrobe.ITEMS[res[0][0]]
            line = f"👘 {it.name}" + (" — 새 옷이다!" if res[0][1] == "new" else " — 옷감으로 바꿨어")
        else:
            self.half = True
            line = "오이다~! 고마워 맹우! 나머지는 반값!"
        g.shrine.set_saisen(s.saisen)
        g.shrine.pop(f"-{price:,}")
        p = self.nitori.pet
        p.act("happy", 1.0)
        self.at(1.0, lambda: self.phase != "bye" and p.act("idle", 99))
        self.say(self.nitori, line, 3.2)
        log.info("니토리 노점: %s (%d)", key, price)
        g.save()
        return True

    def on_click(self, gu: Guest) -> None:
        self._pose(1.4)
        self.say(gu, "우클릭하면 물건을 볼 수 있어!" if self.phase == "shop" else "갓파 노점이야~")


# ── 유유코: 배고파~ 먹을 걸 대접하면 새전, 3번 배불리 먹이면 요우무가 찾아옴 ──
class YuyukoVisit(Visit):
    kind = "yuyuko"

    def __init__(self, visits: "Visits"):
        super().__init__(visits)
        g, sx = self.ground, self.game.shrine.pos_x
        side = random.choice((-1, 1))
        self.yuyuko = self.spawn("yuyuko", min(max(sx + side * 110, g.x1 + 40), g.x2 - 40))
        self.yuyuko.fade(0.92, 2.0)                           # 유령이라 스르르
        self.yuyuko.face(sx)
        now = time.monotonic()
        self.full = 0
        self.phase, self.leave_at, self.beg_at = "hungry", now + YUYUKO_STAY, now + 1.5
        self._held = False
        self._youmu_said = False

    def update(self, now: float) -> None:
        y = self.yuyuko
        if y.gone:
            return
        p = y.pet
        if p.state == "held":
            self._held = True
        if not y.ready:
            return
        if self._held:
            self._held = False
            p.act("caught", 1.2)
            self.say(y, "어머, 들어 올리면 배가 더 고파져~")
            self.at(1.2, lambda: self.phase == "hungry" and p.act("idle", 99))
        if not self._youmu_said:                              # 요우무가 있으면 한마디
            youmu = next((o for o in self.game.pets if o.ch.key == "youmu" and o.grounded), None)
            if youmu is not None and abs(youmu.pos_x - p.pos_x) < 500:
                self._youmu_said = True
                self.game.events._say(youmu, "유유코 님! 또 드시러 오셨어요?")
        if self.phase != "hungry":
            return
        if now >= self.leave_at:
            self.phase = "bye"
            self.say(y, "배고파서 돌아갈래~ 다음엔 맛있는 거 줘~", 3.0)
            self.at(2.0, lambda: self.leave(y, 1.5))
        elif now >= self.beg_at:
            self.beg_at = now + random.uniform(12, 18)
            self.say(y, random.choice(["배고파~ 뭐 먹을 거 없어?", "공양물은 없나~?", "우클릭하면 대접할 수 있어~"]))

    def price(self, key: str) -> int:
        return YUYUKO_FOODS[key][3] * self.game.state.shrine_level

    def fill_menu(self, gu: Guest, menu: "QMenu") -> None:
        if self.phase != "hungry":
            return
        menu.addSeparator()
        head = menu.addAction(f"🍽 대접하기  (배부름 {min(self.full, 100)} / 100)")
        head.setEnabled(False)
        for key, (icon, name, fill, _) in YUYUKO_FOODS.items():
            price = self.price(key)
            a = menu.addAction(f"{icon} {name}  (배부름 +{fill})   새전 {price:,}", lambda key=key: self.feed(key))
            a.setEnabled(self.game.state.saisen >= price)

    def feed(self, key: str) -> bool:
        g, s = self.game, self.game.state
        price = self.price(key)
        if self.phase != "hungry" or s.saisen < price:
            return False
        icon, name, fill, _ = YUYUKO_FOODS[key]
        s.saisen -= price
        g.shrine.set_saisen(s.saisen)
        g.shrine.pop(f"-{price:,}")
        self.full += fill
        p = self.yuyuko.pet
        p.act("skill", 2.4)                                   # 냠냠 → 배 통통
        self.say(self.yuyuko, random.choice([f"{icon} 냠냠~ 맛있어!", f"{icon} 와아, {aff.josa(name, '이다', '다')}~!",
                                             f"{icon} 더 줘~"]))
        if self.full >= 100:
            self.phase = "full"
            self.at(2.5, self._satisfied)
        else:
            self.at(2.4, lambda: self.phase == "hungry" and p.act("idle", 99))
        log.info("유유코 대접: %s (%d, 배부름 %d)", key, price, self.full)
        g.save()
        return True

    def _satisfied(self) -> None:
        g, s, y = self.game, self.game.state, self.yuyuko
        y.pet.act("happy", 99)
        amount = max(100, s.income_per_min * 25)
        s.add_saisen(amount)
        s.yuyuko_fed += 1
        g.shrine.set_saisen(s.saisen)
        g.shrine.pop(f"+{amount:,}")
        self.say(y, f"배불러~ 고마워! 새전 +{amount:,}", 3.0)
        if s.yuyuko_fed == 3 and "youmu" not in s.unlocked:
            self.at(3.2, lambda: self.say(y, "답례로 요우무를 보내 줄게~", 3.0))
            self.at(5.0, g.check_unlocks)
        self.at(6.5, lambda: self.leave(y, 1.5))
        g.save()

    def on_click(self, gu: Guest) -> None:
        self.say(gu, random.choice(["후후~ 배고파~", "우클릭하면 맛있는 걸 줄 수 있어~"]) if self.phase == "hungry"
                 else "잘 먹었어~")


# ── 미스티아: 밤의 포장마차 ──
class MystiaVisit(Visit):
    kind = "mystia"

    def __init__(self, visits: "Visits"):
        super().__init__(visits)
        g, sx, game = self.ground, self.game.shrine.pos_x, self.game
        row = game.torii_row
        if row.isVisible():                                   # 도리이 줄과 겹치지 않게 반대편
            self.side = 1 if row.x() + row.width() / 2 < sx else -1
        else:
            self.side = 1 if (g.x2 - sx) > (sx - g.x1) else -1
        k = game.scale
        stall_x = min(max(sx + self.side * (game.shrine.width() / 2 + 70 * k), g.x1 + 80), g.x2 - 80)
        self.stall = Stall(stall_x, g.y, k)
        self.effect(self.stall)
        fade(self.stall, 1.0, 1.2)
        mx = min(max(stall_x + self.side * 75 * k, g.x1 + 30), g.x2 - 30)
        self.mystia = self.spawn("mystia", mx)
        self.mystia.fade(1.0, 1.2)
        self.mystia.face(stall_x)
        now = time.monotonic()
        self.sold: set[str] = set()
        self.phase, self.leave_at, self.shout_at = "open", now + MYSTIA_STAY, now + 1.5
        self._held = False

    def _grill(self, seconds: float = 2.4) -> None:
        p = self.mystia.pet
        p.act("skill", seconds)                               # 부채질 → 꼬치 자랑
        self.at(seconds, lambda: self.phase == "open" and p.state not in ("held", "fall") and p.act("idle", 99))

    def update(self, now: float) -> None:
        m = self.mystia
        if m.gone:
            return
        p = m.pet
        if p.state == "held":
            self._held = True
        if not m.ready:
            return
        if self._held:
            self._held = False
            p.act("caught", 1.2)
            self.say(m, "꺄! 장어 탄다구요~!")
            self.at(1.2, lambda: self.phase == "open" and p.act("idle", 99))
        if self.phase != "open":
            return
        if now >= self.leave_at or len(self.sold) == len(MYSTIA_MENU):
            self._bye()
        elif now >= self.shout_at:
            self.shout_at = now + random.uniform(12, 18)
            self._grill()
            self.say(m, random.choice(["장어 구워요~ 맛있는 장어!", "♪ 밤참 먹고 가요~", "우클릭해서 주문해요!"]))

    def _bye(self) -> None:
        self.phase = "bye"
        self.say(self.mystia, "오늘 장사 끝~ 또 올게요!")
        self.at(1.5, lambda: self.leave(self.mystia, 1.2))
        self.at(1.5, lambda: fade(self.stall, 0.0, 1.2, self.stall.close))

    def cancel(self) -> None:
        if self.phase != "bye":
            self.phase = "bye"
            fade(self.stall, 0.0, 0.4, self.stall.close)
        super().cancel()

    def price(self, key: str) -> int:
        return mystia_price(self.game.state, key)

    def fill_menu(self, gu: Guest, menu: "QMenu") -> None:
        if self.phase != "open":
            return
        menu.addSeparator()
        head = menu.addAction("🏮 미스티아 포장마차")
        head.setEnabled(False)
        for key, (icon, name, desc) in MYSTIA_MENU.items():
            price = self.price(key)
            sold = key in self.sold
            a = menu.addAction(f"{icon} {name} — 오늘은 다 팔렸어요" if sold else f"{icon} {name}  ({desc})   새전 {price:,}",
                               lambda key=key: self.buy(key))
            a.setEnabled(not sold and self.game.state.saisen >= price)

    def buy(self, key: str) -> bool:
        g, s = self.game, self.game.state
        price = self.price(key)
        if self.phase != "open" or key in self.sold or s.saisen < price:
            return False
        s.saisen -= price
        self.sold.add(key)
        g.shrine.set_saisen(s.saisen)
        g.shrine.pop(f"-{price:,}")
        if key == "kabayaki":
            s.mystia_until = time.time() + 1800
            line = "🐟 장어구이 나왔어요! 30분 동안 수입 ×1.3"
            self._grill()
        elif key == "oden":
            for o in g.pets:
                aff.add(s, o.ch.key, 2)
                o.hearts.append([0.0, o.width() / 2, 40])
            line = "🍢 오뎅 한 그릇씩~ 다들 더 친해졌어요!"
        else:
            s.cloth += 10
            for o in g.pets:
                if o.grounded:
                    o.act("happy" if random.random() < 0.5 else "wave", 2.0)
            line = "🎵 ♪ 라~ 라라~ 밤참은 포장마차~ ♪  (옷감 +10)"
        self.say(self.mystia, line, 3.2)
        log.info("미스티아 포장마차: %s (%d)", key, price)
        g.save()
        return True

    def on_click(self, gu: Guest) -> None:
        self.say(gu, "어서 와요~ 우클릭해서 주문해요!" if self.phase == "open" else "또 와요~")


# ── 레이센: 영원정 약 행상 ──
class ReisenVisit(Visit):
    kind = "reisen"

    def __init__(self, visits: "Visits"):
        super().__init__(visits)
        g, sx = self.ground, self.game.shrine.pos_x
        self.side = 1 if (g.x2 - sx) > (sx - g.x1) else -1
        clamp = lambda x: min(max(x, g.x1 + 30), g.x2 - 30)   # noqa: E731
        self.reisen = self.spawn("reisen", clamp(sx + self.side * 420))
        self.reisen.fade(1.0, 0.6)
        self.reisen.go(clamp(sx + self.side * (self.game.shrine.width() / 2 + 60)), 55)
        self.sold: set[str] = set()
        self._held = False
        now = time.monotonic()
        self.phase, self.until, self.leave_at, self.shout_at = "enter", now + 10, now + REISEN_STAY, 0.0

    def _pose(self, seconds: float = 1.6) -> None:
        p = self.reisen.pet
        p.act("skill", seconds)                               # 약병 → 손가락 총
        self.at(seconds, lambda: self.phase == "shop" and p.state not in ("held", "fall") and p.act("idle", 99))

    def update(self, now: float) -> None:
        r = self.reisen
        if r.gone:
            return
        p = r.pet
        if p.state == "held":
            self._held = True
        if not r.ready:
            return
        if self._held:
            self._held = False
            p.act("caught", 1.2)
            self.say(r, "꺅! 약병 깨져요~!")
            self.at(1.2, lambda: self.phase == "shop" and p.act("idle", 99))
        if self.phase == "enter" and (r.arrived() or now >= self.until):
            r.goal = None
            r.face(self.game.shrine.pos_x)
            p.act("bow", 1.2)
            self.say(r, "영원정 약 배달 왔어요. 우클릭해서 골라 주세요!", 3.5)
            self.at(1.2, lambda: self.phase == "shop" and p.act("idle", 99))
            self.phase, self.shout_at = "shop", now + 15
        elif self.phase == "shop":
            if now >= self.leave_at or len(self.sold) == len(REISEN_MEDS):
                self._bye()
            elif now >= self.shout_at:
                self.shout_at = now + random.uniform(14, 20)
                self._pose()
                self.say(r, random.choice(["스승님 특제 약이에요~", "피곤할 땐 피로회복약!", "테위 보면 알려 주세요…"]))

    def _bye(self) -> None:
        self.phase = "bye"
        r, g = self.reisen, self.ground
        self.say(r, "약은 용법·용량을 지켜서~ 그럼!")
        self.at(1.2, lambda: r.go(g.x2 - 20 if self.side > 0 else g.x1 + 20, 70))
        self.at(5.0, lambda: self.leave(r, 0.8))

    def fill_menu(self, gu: Guest, menu: "QMenu") -> None:
        if self.phase != "shop":
            return
        menu.addSeparator()
        head = menu.addAction("💊 영원정 약 행상")
        head.setEnabled(False)
        for key, (icon, name, desc) in REISEN_MEDS.items():
            price = reisen_price(self.game.state, key)
            sold = key in self.sold
            a = menu.addAction(f"{icon} {name} — 다 팔림" if sold else f"{icon} {name}  ({desc})   새전 {price:,}",
                               lambda key=key: self.buy(key))
            a.setEnabled(not sold and self.game.state.saisen >= price)

    def buy(self, key: str) -> bool:
        g, s = self.game, self.game.state
        price = reisen_price(s, key)
        if self.phase != "shop" or key in self.sold or s.saisen < price:
            return False
        s.saisen -= price
        self.sold.add(key)
        g.shrine.set_saisen(s.saisen)
        g.shrine.pop(f"-{price:,}")
        if key == "energy":
            s.reisen_until = time.time() + 3600
            line = "💊 피로회복약! 1시간 동안 쓰다듬기 새전 ×2예요"
            for o in g.pets:
                o.react(True)
        elif key == "dream":
            s.dream_pill = True
            line = "🌙 꿈나라 약! 다음에 꺼져 있는 동안 새전함이 2배예요"
        else:
            s.fate_boost = True
            line = "🍀 행운의 약! 다음 오미쿠지는 대길 쪽으로~"
        self._pose(1.4)
        self.say(self.reisen, line, 3.2)
        log.info("레이센 약: %s (%d)", key, price)
        g.save()
        return True

    def on_click(self, gu: Guest) -> None:
        self._pose(1.4)
        self.say(gu, random.choice(["광기의 눈동자… 는 농담이에요.", "우클릭하면 약을 볼 수 있어요!"]) if self.phase == "shop"
                 else "영원정에서 왔어요.")


# ── 파츄리: 날씨 마법 ──
class PatchouliVisit(Visit):
    kind = "patchouli"

    def __init__(self, visits: "Visits"):
        super().__init__(visits)
        g, sx = self.ground, self.game.shrine.pos_x
        self.side = 1 if (g.x2 - sx) > (sx - g.x1) else -1
        clamp = lambda x: min(max(x, g.x1 + 30), g.x2 - 30)   # noqa: E731
        self.patchy = self.spawn("patchouli", clamp(sx + self.side * 380))
        self.patchy.fade(1.0, 0.8)
        self.patchy.go(clamp(sx + self.side * (self.game.shrine.width() / 2 + 60)), 22)   # 천천히 (운동 부족)
        self.cast = False
        self._held = False
        now = time.monotonic()
        self.phase, self.until, self.leave_at, self.mutter_at = "enter", now + 16, now + PATCHY_STAY, 0.0

    def update(self, now: float) -> None:
        pc = self.patchy
        if pc.gone:
            return
        p = pc.pet
        if p.state == "held":
            self._held = True
        if not pc.ready:
            return
        if self._held:
            self._held = False
            p.act("caught", 1.2)
            self.say(pc, "콜록, 콜록… 흔들지 마…")
            self.at(1.2, lambda: self.phase == "shop" and p.act("idle", 99))
        if self.phase == "enter" and (pc.arrived() or now >= self.until):
            pc.goal = None
            pc.face(self.game.shrine.pos_x)
            p.act("idle", 99)
            self.say(pc, "…날씨가 마음에 안 들면 바꿔 줄 수 있어. 우클릭.", 3.5)
            self.phase, self.mutter_at = "shop", now + 14
        elif self.phase == "shop":
            if now >= self.leave_at:
                self._bye()
            elif now >= self.mutter_at and not self.cast:
                self.mutter_at = now + random.uniform(14, 20)
                p.act("skill", 2.0)                           # 책 읽기
                self.at(2.0, lambda: self.phase == "shop" and p.act("idle", 99))
                self.say(pc, random.choice(["…", "이 책, 꽤 재밌네.", "콜록… 먼지가…", "일월화수목금토…"]))

    def _bye(self) -> None:
        self.phase = "bye"
        pc, g = self.patchy, self.ground
        self.say(pc, "…도서관으로 돌아갈게.")
        self.at(1.2, lambda: pc.go(g.x2 - 20 if self.side > 0 else g.x1 + 20, 30))
        self.at(6.0, lambda: self.leave(pc, 1.0))

    def fill_menu(self, gu: Guest, menu: "QMenu") -> None:
        if self.phase != "shop" or self.cast:
            return
        menu.addSeparator()
        head = menu.addAction("📚 날씨 마법 (한 번만)")
        head.setEnabled(False)
        for key, (_w, icon, name, desc, _secs) in PATCHY_SPELLS.items():
            price = patchy_price(self.game.state, key)
            a = menu.addAction(f"{icon} {name}  ({desc})   새전 {price:,}", lambda key=key: self.buy(key))
            a.setEnabled(self.game.state.saisen >= price)

    def buy(self, key: str) -> bool:
        g, s = self.game, self.game.state
        price = patchy_price(s, key)
        if self.phase != "shop" or self.cast or s.saisen < price:
            return False
        wkey, icon, name, _desc, secs = PATCHY_SPELLS[key]
        s.saisen -= price
        self.cast = True
        g.shrine.set_saisen(s.saisen)
        g.shrine.pop(f"-{price:,}")
        s.weather_magic, s.weather_magic_until = wkey, time.time() + secs
        weather.set_magic(wkey, s.weather_magic_until)
        p = self.patchy.pet
        p.act("skill", 2.4)                                   # 오색 구슬
        self.say(self.patchy, f"{icon} {name}… 일월화수목금토, 날씨여 바뀌어라.", 3.2)
        self.at(2.0, g._refresh_season)
        self.at(2.6, lambda: g._say_at_shrine(f"{icon} 파츄리의 마법으로 날씨가 {weather.WEATHERS[wkey].name}(으)로!"))
        self.at(2.4, lambda: self.phase == "shop" and p.act("idle", 99))
        self.at(8.0, self._bye)
        log.info("파츄리 날씨 마법: %s (%d)", wkey, price)
        g.save()
        return True

    def on_click(self, gu: Guest) -> None:
        self.say(gu, random.choice(["…방해하지 마.", "우클릭하면 날씨 마법을 걸어 줄게."]) if self.phase == "shop"
                 else "…")


# ── 유카리: 틈(스키마)으로 친구들을 엉뚱한 곳에 ──
class YukariVisit(Visit):
    kind = "yukari"

    def __init__(self, visits: "Visits"):
        super().__init__(visits)
        g, sx = self.ground, self.game.shrine.pos_x
        side = random.choice((-1, 1))
        x = min(max(sx + side * (self.game.shrine.width() / 2 + 90), g.x1 + 40), g.x2 - 40)
        self.effect(Gap(x - side * 10, g.y, 2.4))
        self.yukari = self.spawn("yukari", x)
        self.yukari.fade(1.0, 1.0)
        self.yukari.face(sx)
        now = time.monotonic()
        self.tricks = 0
        self.moved: list = []
        self._held = False
        self.phase, self.next_at, self.leave_at = "hello", now + 1.2, now + YUKARI_STAY
        self.at(0.8, lambda: self.say(self.yukari, "어머, 경계 너머에서 실례할게요. 후후."))

    def update(self, now: float) -> None:
        yk = self.yukari
        if yk.gone:
            return
        p = yk.pet
        if p.state == "held":
            self._held = True
        if not yk.ready:
            return
        if self._held:
            self._held = False
            p.act("caught", 1.2)
            self.say(yk, "어머나, 숙녀를 들어 올리다니~")
            self.next_at = now + 1.5
        if self.phase == "hello" and now >= self.next_at:
            p.act("bow", 1.2)
            self.phase, self.next_at = "tricks", now + 2.5
        elif self.phase == "tricks" and now >= self.next_at:
            if self.tricks >= YUKARI_TRICKS or now >= self.leave_at:
                self._gift()
            else:
                self._trick()
                self.next_at = now + random.uniform(7, 10)

    def _trick(self) -> None:
        g = self.game
        cands = [o for o in g.pets if o.grounded and o.on is not None and o.isVisible() and o not in self.moved[-2:]]
        if not cands:
            self.tricks += 1
            return
        o = random.choice(cands)
        self.tricks += 1
        self.moved.append(o)
        yk = self.yukari
        yk.face(o.pos_x)
        yk.pet.act("skill", 2.2)                              # 틈 열기 → 부채
        self.at(2.2, lambda: self.phase == "tricks" and yk.pet.state not in ("held", "fall") and yk.pet.act("idle", 99))
        self.effect(Gap(o.pos_x, o.pos_y, 1.6))
        o.act("startled", 1.0)
        fade(o, 0.0, 0.5)
        self.at(0.6, lambda: self._drop_somewhere(o))
        self.say(yk, random.choice(["저 아이, 잠깐 빌릴게요.", "경계를 살짝 바꿔 볼까요.", "후후, 어디로 보낼까~"]))

    def _drop_somewhere(self, o) -> None:
        """다른 바닥·창 위·하늘에서 툭."""
        g = self.game
        spots = [(gr.x1 + 60, gr.x2 - 60, gr.y) for gr in g.grounds if gr.x2 - gr.x1 > 160]
        spots += [(pl.x1 + 30, pl.x2 - 30, pl.y) for pl in g.window_platforms if pl.x2 - pl.x1 > 120]
        x1, x2, y = random.choice(spots) if spots else (g.left + 80, g.right - 80, g.bottom)
        x = random.uniform(x1, max(x1 + 1, x2))
        drop = random.uniform(60, 220)
        o.pos_x, o.pos_y, o.vx, o.vy, o.state, o.on = x, y - drop, 0.0, 0.0, "fall", None
        o._startle_on_land = True
        o._place()
        self.effect(Gap(x, y - drop + 20, 1.4, h=70))
        fade(o, 1.0, 0.4)
        self.game.events._say(o, random.choice(["여, 여긴 어디야?!", "으앗! 틈이다!", "유카리 씨~!"]))

    def _gift(self) -> None:
        self.phase = "bye"
        g, s, yk = self.game, self.game.state, self.yukari
        yk.pet.act("happy", 1.4)
        if random.random() < 0.5:
            n = 10 * s.shrine_level
            s.cloth += n
            prize = f"옷감 +{n}"
        else:
            amount = max(80, s.income_per_min * 20)
            s.add_saisen(amount)
            g.shrine.set_saisen(s.saisen)
            g.shrine.pop(f"+{amount:,}")
            prize = f"새전 +{amount:,}"
        self.say(yk, f"즐거웠어요. 경계의 선물이에요 — {prize}", 3.2)
        log.info("유카리 선물: %s", prize)
        self.at(3.4, lambda: self.effect(Gap(yk.pet.pos_x, yk.pet.pos_y, 1.6)))
        self.at(3.6, lambda: self.leave(yk, 0.6))
        g.save()

    def cancel(self) -> None:
        for o in self.moved:                                  # 사라지던 중이면 다시 보이게
            o.setWindowOpacity(1.0)
        super().cancel()

    def on_click(self, gu: Guest) -> None:
        self.say(gu, random.choice(["후후, 무슨 일이죠?", "틈 안이 궁금한가요?", "레이무에게 안부 전해 줘요."]))


VISIT_CLASSES = {"fairies": FairyVisit, "aya": AyaVisit, "suika": SuikaVisit,
                 "tewi": TewiVisit, "koishi": KoishiVisit, "nitori": NitoriVisit,
                 "yuyuko": YuyukoVisit, "mystia": MystiaVisit, "reisen": ReisenVisit,
                 "patchouli": PatchouliVisit, "yukari": YukariVisit}


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
        elif random.random() < (VISIT_CHANCE * (1 + omamori.bonus(g.state, "guest")) * weather.current().guests
                                * (3.0 if g.state.festival_until > time.time() else 1.0)):          # 예대제엔 손님이 몰려옴
            kinds = available(g.state)
            if kinds:
                if weather.current().key == "drizzle" and "fairies" in kinds and random.random() < 0.5:
                    kinds = ["fairies"]                      # 안개비: 요정들이 장난치기 좋은 날
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
        self._next = time.monotonic() + (VISIT_COOLDOWN / 5 if self.game.state.festival_until > time.time()
                                         else VISIT_COOLDOWN)
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
