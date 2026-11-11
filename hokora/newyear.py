# -*- coding: utf-8 -*-
"""연말연시 행사.

- 연말 대청소 (煤払い, 12월 13일 ~ 31일): 하루 한 번, 작업표시줄에 먼지 뭉치가 굴러다니고 신사 처마에 거미줄이 생긴다.
  90초 안에 눌러서 치운다 (거미줄은 두 번). 친구들도 달려가 같이 치운다.
  치운 만큼 새전, 다 치우면 보너스 새전 + 옷감, 다 치운 날이 5일이 되면 옷감을 더.
- 새해 첫 참배 (初詣, 1월 1일 ~ 7일): 그해 처음 켜면 친구들이 신사 앞에 모여 소원을 빈다.
  새해 새전 + 다음 오미쿠지는 대길·중길 + 친구 모두 호감도. 연하장(그해 간지 카드)을 그림으로 저장할 수 있다.
- 해가 바뀌는 순간 켜 두었으면 「謹賀新年」 불꽃놀이 (app.py).
날짜는 yearend.today() (HOKORA_TODAY 로 바꿔 시험).
"""
from __future__ import annotations

import logging
import math
import random
import time
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from . import yearend
from .state import GameState

if TYPE_CHECKING:
    from .app import Game

log = logging.getLogger("Hokora.newyear")

# ── 대청소 ──
CLEAN_FROM_DAY = 13               # 12월 13일 ~ 31일
CLEAN_TIME = 90.0
CLEAN_AFTER = (180.0, 480.0)      # 켜고 이만큼 지나 저절로 (오늘 아직 안 했으면)
DUST_N, WEB_N = 9, 3
WEB_HP = 2                        # 거미줄은 두 번 눌러야
HELP_EVERY = (3.0, 5.5)           # 친구가 도우러 가는 간격
HELP_SPEED = 90.0
CLEAR_CLOTH = 5
FULL_DAYS, FULL_DAYS_CLOTH = 5, 30

# ── 새해 ──
HATSUMODE_LAST_DAY = 7            # 1월 1일 ~ 7일 (마츠노우치)
HATSUMODE_HEARTS = 2              # 친구 모두 호감도 +2
NENGAJO_LAST_DAY = 31             # 연하장은 1월 한 달

STEMS = "甲乙丙丁戊己庚辛壬癸"
STEMS_KO = "갑을병정무기경신임계"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
BRANCHES_KO = "자축인묘진사오미신유술해"
ANIMALS = ["쥐", "소", "호랑이", "토끼", "용", "뱀", "말", "양", "원숭이", "닭", "개", "돼지"]
STEM_COLOR = ["푸른", "푸른", "붉은", "붉은", "황금", "황금", "흰", "흰", "검은", "검은"]


def zodiac(year: int) -> tuple[str, str, str]:
    """(한자 간지 「丁未年」, 한글 「정미년」, 「붉은 양의 해」)."""
    i, j = (year - 4) % 10, (year - 4) % 12
    return (f"{STEMS[i]}{BRANCHES[j]}年", f"{STEMS_KO[i]}{BRANCHES_KO[j]}년", f"{STEM_COLOR[i]} {ANIMALS[j]}의 해")


def clean_season(d: date | None = None) -> bool:
    d = d or yearend.today()
    return d.month == 12 and d.day >= CLEAN_FROM_DAY


def clean_blocked(s: GameState, d: date | None = None) -> str:
    d = d or yearend.today()
    if not clean_season(d):
        return f"12월 {CLEAN_FROM_DAY}일부터 31일까지 해요"
    if s.clean_day == d.isoformat():
        return "오늘 대청소는 끝났어요 (내일 또!)"
    return ""


def spot_reward(s: GameState) -> int:
    return max(10, s.income_per_min // 2)


def clear_bonus(s: GameState) -> int:
    return max(300, s.income_per_min * 20)


def hatsumode_due(s: GameState, d: date | None = None) -> bool:
    d = d or yearend.today()
    return d.month == 1 and d.day <= HATSUMODE_LAST_DAY and s.hatsumode_year < d.year


def hatsumode_gift(s: GameState) -> int:
    return max(3000, s.income_per_min * 120)


def nengajo_season(d: date | None = None) -> bool:
    d = d or yearend.today()
    return d.month == 1 and d.day <= NENGAJO_LAST_DAY


def hatsumode(s: GameState, d: date | None = None) -> int:
    """새해 첫 참배의 선물을 줌 → 새해 새전. 친구 호감도는 app 이 (하트가 늘면 말풍선이 떠야 하므로)."""
    d = d or yearend.today()
    s.hatsumode_year = d.year
    gift = hatsumode_gift(s)
    s.add_saisen(gift)
    s.fate_boost = True                                    # 새해 첫 오미쿠지는 대길·중길
    if s.omikuji_date == date.today().isoformat():         # 오늘 이미 뽑았으면 한 번 더
        s.omikuji_extra += 1
    return gift


# ── 먼지 · 거미줄 ──
class DustSpot(QWidget):
    """먼지 뭉치(바닥) 또는 거미줄(처마). 누르면 치움 (거미줄은 두 번)."""

    def __init__(self, kind: str, on_hit: Callable[["DustSpot"], None], seed: int):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setCursor(Qt.PointingHandCursor)
        self.kind, self.on_hit = kind, on_hit
        self.hp = WEB_HP if kind == "web" else 1
        self.rng = random.Random(seed)
        self.cleaned = False
        self.gone = False
        self.target = False              # 친구가 치우러 가는 중
        self.puff_at = 0.0
        self.shake_at = 0.0
        self.setFixedSize(*((58, 58) if kind == "web" else (44, 34)))
        # 먼지 뭉치: 털 뭉치를 이루는 작은 동그라미들 (x, y, 반지름, 회색)
        self.blobs = [(self.rng.uniform(12, 32), self.rng.uniform(12, 26), self.rng.uniform(5, 9),
                       self.rng.randint(95, 150)) for _ in range(9)]
        self.fibers = [(self.rng.uniform(0, math.tau), self.rng.uniform(10, 18)) for _ in range(10)]
        self.timer = QTimer(self, timeout=self._tick, interval=33)
        self.destroyed.connect(lambda *_: setattr(self, "gone", True))

    @property
    def center_x(self) -> float:
        return self.x() + self.width() / 2

    def hit(self) -> bool:
        """한 번 치움 → 다 치웠으면 True."""
        if self.cleaned:
            return False
        self.hp -= 1
        self.shake_at = time.monotonic()
        if self.hp <= 0:
            self.cleaned = True
            self.puff_at = time.monotonic()
        self.timer.start()
        self.update()
        return self.cleaned

    def mousePressEvent(self, _e) -> None:
        if not self.cleaned:
            self.on_hit(self)

    def _tick(self) -> None:
        now = time.monotonic()
        if self.cleaned and now - self.puff_at > 0.6:
            self.gone = True
            self.close()
            return
        if not self.cleaned and now - self.shake_at > 0.3:
            self.timer.stop()
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        now = time.monotonic()
        if self.cleaned:                                         # 퐁! 반짝이며 사라짐
            u = min(1.0, (now - self.puff_at) / 0.6)
            p.setPen(Qt.NoPen)
            for k in range(6):
                a = k * math.tau / 6
                r = 6 + 16 * u
                p.setBrush(QColor(255, 236, 160, int(220 * (1 - u))))
                p.drawEllipse(QPointF(self.width() / 2 + math.cos(a) * r, self.height() / 2 + math.sin(a) * r), 3, 3)
            p.setBrush(QColor(200, 200, 205, int(120 * (1 - u))))
            p.drawEllipse(QPointF(self.width() / 2, self.height() / 2), 10 * (1 + u), 8 * (1 + u))
            p.end()
            return
        if now - self.shake_at < 0.3:
            p.translate(3 if int(now * 40) % 2 else -3, 0)
        if self.kind == "web":
            self._web(p)
        else:
            self._dust(p)
        p.end()

    def _dust(self, p: QPainter) -> None:
        p.setPen(QPen(QColor(110, 110, 118, 150), 1))
        cx, cy = 22, 20
        for a, ln in self.fibers:                               # 삐죽 나온 실 보푸라기
            p.drawLine(QPointF(cx, cy), QPointF(cx + math.cos(a) * ln, cy + math.sin(a) * ln * 0.6))
        p.setPen(Qt.NoPen)
        for x, y, r, g in self.blobs:
            p.setBrush(QColor(g, g, g + 6, 225))
            p.drawEllipse(QPointF(x, y), r, r * 0.85)
        p.setBrush(QColor(255, 255, 255, 60))
        p.drawEllipse(QPointF(18, 15), 4, 3)

    def _web(self, p: QPainter) -> None:
        w = self.width()
        cx, cy = w / 2, 6.0                                     # 위쪽 가운데에 매달림
        alpha = 230 if self.hp >= WEB_HP else 130               # 한 번 걷어 내면 흐려짐
        p.setPen(QPen(QColor(235, 235, 240, alpha), 1.2))
        spokes = [math.pi * (0.08 + 0.84 * k / 6) for k in range(7)]
        for a in spokes:
            p.drawLine(QPointF(cx, cy), QPointF(cx + math.cos(a) * 28, cy + math.sin(a) * 48))
        p.setPen(QPen(QColor(220, 220, 228, alpha), 1))
        for ring in (0.3, 0.55, 0.8, 1.0):
            path = QPainterPath()
            for i, a in enumerate(spokes):
                pt = QPointF(cx + math.cos(a) * 28 * ring, cy + math.sin(a) * 48 * ring)
                if i == 0:
                    path.moveTo(pt)
                else:
                    prev = spokes[i - 1]
                    mid = (a + prev) / 2
                    ctrl = QPointF(cx + math.cos(mid) * 24 * ring, cy + math.sin(mid) * 41 * ring)   # 살짝 처짐
                    path.quadTo(ctrl, pt)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        p.setPen(QPen(QColor(60, 60, 70, alpha), 1))            # 작은 거미
        p.setBrush(QColor(60, 60, 70, alpha))
        p.drawLine(QPointF(cx, cy), QPointF(cx + 6, 30))
        p.drawEllipse(QPointF(cx + 6, 32), 3, 3)


class Cleaning:
    """하루 한 판. Game 이 만들고, 끝나면 game.cleaning = None."""

    def __init__(self, game: "Game", rng: random.Random | None = None):
        self.game = game
        self.rng = rng or random.Random()
        self.spots: list[DustSpot] = []
        self.helpers: dict[object, DustSpot] = {}       # 도우러 가는 친구 → 먼지
        self.cleaned = 0
        self.by_friends = 0
        self.earned = 0
        self.started = time.monotonic()
        self.ends = self.started + CLEAN_TIME
        self.next_help = self.started + self.rng.uniform(*HELP_EVERY)
        self.warned = False
        self.over = False
        self.timer = QTimer(game, timeout=self.tick, interval=200)

    @property
    def total(self) -> int:
        return len(self.spots)

    def windows(self) -> list[QWidget]:
        return [w for w in self.spots if not w.gone]

    def left(self) -> float:
        return max(0.0, self.ends - time.monotonic())

    def start(self) -> None:
        g = self.game
        g.state.clean_day = yearend.today().isoformat()
        self._place()
        if not g.hidden_for_fullscreen:
            for w in self.spots:
                w.show()
        self.timer.start()
        log.info("대청소 시작: %d곳", self.total)

    def _place(self) -> None:
        g = self.game
        ground = g.ground_under(g.shrine.pos_x)
        sx = g.shrine.pos_x
        lo, hi = max(ground.x1 + 30, sx - 480), min(ground.x2 - 30, sx + 480)
        xs: list[float] = []
        for _ in range(DUST_N * 20):                     # 서로 너무 붙지 않게
            if len(xs) >= DUST_N:
                break
            x = self.rng.uniform(lo, hi)
            if all(abs(x - o) > 46 for o in xs):
                xs.append(x)
        for i, x in enumerate(xs):
            w = DustSpot("dust", self.hit, self.rng.randrange(1 << 30))
            w.move(round(x - w.width() / 2), round(ground.y - w.height() + 3))
            self.spots.append(w)
        sh = g.shrine                                     # 처마 밑: 신사 창의 양쪽 위, 가운데
        hooks = [(sh.x() + sh.width() * 0.2, sh.y() + sh.height() * 0.38),
                 (sh.x() + sh.width() * 0.8, sh.y() + sh.height() * 0.38),
                 (sh.x() + sh.width() * 0.5, sh.y() + sh.height() * 0.5)]
        for hx, hy in hooks[:WEB_N]:
            w = DustSpot("web", self.hit, self.rng.randrange(1 << 30))
            w.move(round(hx - w.width() / 2), round(hy))
            self.spots.append(w)

    # ── 치우기 ──
    def hit(self, spot: DustSpot, pet=None) -> None:
        if self.over or not spot.hit():
            return
        g = self.game
        s = g.state
        self.cleaned += 1
        reward = spot_reward(s)
        self.earned += reward
        s.add_saisen(reward)
        s.clean_spots += 1
        g.shrine.set_saisen(s.saisen)
        g.shrine.pop(f"+{reward:,}")
        if pet is not None:
            self.by_friends += 1
        if self.cleaned >= self.total:
            g.later(0.7, self.finish)

    def tick(self) -> None:
        if self.over:
            return
        now = time.monotonic()
        if now >= self.ends:
            self.finish()
            return
        if not self.warned and self.ends - now <= 30:
            self.warned = True
            n = self.total - self.cleaned
            self.game._say_at_shrine(f"🧹 30초 남았어요!  남은 먼지 {n}곳")
        self._helpers_tick(now)

    def _free_pets(self) -> list:
        g = self.game
        ground = g.ground_under(g.shrine.pos_x)
        return [p for p in g.pets if p.grounded and p.on == ground.hwnd and p not in self.helpers
                and p.state not in ("sleep",) and not g.napping]

    def _helpers_tick(self, now: float) -> None:
        g = self.game
        for pet, spot in list(self.helpers.items()):
            if pet not in g.pets or pet.on is None or pet.state == "held" or spot.cleaned or spot.gone:
                self._release(pet)
                continue
            if abs(pet.pos_x - spot.center_x) < 14 or pet.vx == 0:
                pet.vx = 0.0
                pet.act("skill" if pet.ch.key == "reimu" else "happy", 1.0)   # 레이무는 빗자루질
                self._release(pet, keep_act=True)
                if abs(pet.pos_x - spot.center_x) < 40:
                    g.later(0.5, lambda p=pet, sp=spot: self._friend_clean(p, sp))
        if now < self.next_help or g.hidden_for_fullscreen:
            return
        self.next_help = now + self.rng.uniform(*HELP_EVERY)
        free = self._free_pets()
        todo = [w for w in self.spots if w.kind == "dust" and not w.cleaned and not w.target and not w.gone]
        if not free or not todo:
            return
        pet = self.rng.choice(free)
        spot = min(todo, key=lambda w: abs(w.center_x - pet.pos_x))
        spot.target = True
        self.helpers[pet] = spot
        pet.scripted = True
        d = 1 if spot.center_x > pet.pos_x else -1
        pet.act("walk", 30, vx=d * HELP_SPEED)
        if self.rng.random() < 0.5:
            g.events._say(pet, self.rng.choice(["내가 치울게!", "먼지 발견!", "깨끗하게~", "영차!"]), 1.6)

    def _friend_clean(self, pet, spot: DustSpot) -> None:
        if self.over or spot.cleaned or spot.gone:
            return
        self.hit(spot, pet)
        if pet in self.game.pets and self.rng.random() < 0.4:
            self.game.events._say(pet, self.rng.choice(["반짝반짝!", "깨끗해졌다~", "다음!"]), 1.4)

    def _release(self, pet, keep_act: bool = False) -> None:
        spot = self.helpers.pop(pet, None)
        if spot is not None and not spot.cleaned:
            spot.target = False
        pet.scripted = False
        if not keep_act and pet.state == "walk":
            pet.act("idle", 1.0)                         # 걷던 채로 멈춰 서 있지 않게 (곧 스스로 다음 행동)

    # ── 끝 ──
    def finish(self, quiet: bool = False) -> None:
        if self.over:
            return
        self.over = True
        self.timer.stop()
        for pet in list(self.helpers):
            self._release(pet)
        for w in self.spots:
            if not w.gone:
                w.gone = True
                w.close()
        g = self.game
        s = g.state
        clear = self.cleaned >= self.total > 0 and not quiet
        bonus = cloth = 0
        if clear:
            bonus, cloth = clear_bonus(s), CLEAR_CLOTH
            s.add_saisen(bonus)
            s.clean_days += 1
            if s.clean_days == FULL_DAYS:
                cloth += FULL_DAYS_CLOTH
            s.cloth += cloth
            g.shrine.set_saisen(s.saisen)
            for p in g.pets:
                if p.grounded:
                    p.react(True)
        g.cleaning_done(self, clear, bonus, cloth, quiet)
        log.info("대청소 끝: %d/%d (친구 %d), 새전 %d + 보너스 %d", self.cleaned, self.total, self.by_friends,
                 self.earned, bonus)

    def cancel(self) -> None:
        """전체화면 등으로 그만둠 — 치운 만큼은 받고, 오늘 다시 할 수 있게."""
        self.game.state.clean_day = ""
        self.finish(quiet=True)


# ── 연하장 카드 (새해 첫 참배 때) ──
class NewYearCard(QWidget):
    """「謹賀新年」 카드. 단추로 연하장 그림 저장, 다른 곳을 누르면 닫힘. 60초 뒤 저절로 닫힘."""

    W, H = 340, 330

    def __init__(self, year: int, gift: int, on_save: Callable[[], None]):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.W, self.H)
        self.year, self.gift, self.on_save = year, gift, on_save
        self.saved = False
        self.btn = QRectF(40, self.H - 62, self.W - 80, 40)

    def show_above(self, cx: float, bottom: float) -> None:
        self.move(round(cx - self.width() / 2), round(bottom - self.height() - 8))
        self.show()
        QTimer.singleShot(60_000, self.close)

    def mousePressEvent(self, e) -> None:
        if self.btn.contains(e.position()) and not self.saved:
            self.saved = True
            self.on_save()
            self.update()
        else:
            self.close()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 16, 16)
        g = QLinearGradient(0, 0, 0, self.H)
        g.setColorAt(0, QColor("#B3122C"))
        g.setColorAt(1, QColor("#7E0C1F"))
        p.setPen(QPen(QColor("#D4A017"), 2))
        p.setBrush(g)
        p.drawPath(path)
        p.setPen(QPen(QColor(212, 160, 23, 160), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(8, 8, -8, -8), 11, 11)
        _plum(p, 36, 40, 1.0)
        _plum(p, self.W - 40, 52, 0.8)
        kanji, ko, animal = zodiac(self.year)

        def text(rect: QRectF, t: str, size: int, color: str, bold: bool = True, family: str = "Malgun Gothic") -> None:
            f = QFont(family)
            f.setPixelSize(size)
            f.setBold(bold)
            p.setFont(f)
            p.setPen(QColor(color))
            p.drawText(rect, Qt.AlignHCenter | Qt.AlignVCenter | Qt.TextWordWrap, t)

        text(QRectF(0, 26, self.W, 60), "謹賀新年", 42, "#F6D77A", True, "Yu Mincho")
        text(QRectF(0, 88, self.W, 26), f"{self.year}年 {kanji} · {animal}", 15, "#FFE9EC")
        text(QRectF(20, 122, self.W - 40, 30), "🎍 새해 복 많이 받으세요!", 19, "#FFFFFF")
        text(QRectF(24, 160, self.W - 48, 80),
             f"새해 첫 참배를 했어요.\n새해 새전 +{self.gift:,}\n다음 오미쿠지는 대길·중길 · 친구 모두 호감도 +{HATSUMODE_HEARTS}",
             13, "#FFF3D6", False)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 235) if not self.saved else QColor(255, 255, 255, 120))
        p.drawRoundedRect(self.btn, 12, 12)
        text(self.btn, "✓ 저장했어요 (클립보드에도)" if self.saved else "🖼  연하장 그림으로 저장", 14, "#B3122C")
        p.end()


def _plum(p: QPainter, x: float, y: float, k: float) -> None:
    """매화 한 송이 (다섯 꽃잎)."""
    p.save()
    p.setPen(Qt.NoPen)
    for i in range(5):
        a = -math.pi / 2 + i * math.tau / 5
        p.setBrush(QColor(255, 214, 224, 235))
        p.drawEllipse(QPointF(x + math.cos(a) * 7 * k, y + math.sin(a) * 7 * k), 6.5 * k, 6.5 * k)
    p.setBrush(QColor("#D4A017"))
    p.drawEllipse(QPointF(x, y), 3.2 * k, 3.2 * k)
    p.restore()


# ── 연하장 그림 (1200×675) ──
W, H = 1200, 675


def make_nengajo(s: GameState, year: int, shrine_img: QImage | None = None) -> QImage:
    from .panel import portrait
    from .render import CHARACTERS
    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    bg = QLinearGradient(0, 0, 0, H)
    bg.setColorAt(0, QColor("#B3122C"))
    bg.setColorAt(1, QColor("#6E0A1B"))
    p.fillRect(QRectF(0, 0, W, H), bg)
    rng = random.Random(year)
    p.setPen(Qt.NoPen)
    for _ in range(18):                                       # 금빛 구름 무늬
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        grad = QRadialGradient(QPointF(x, y), rng.uniform(60, 130))
        grad.setColorAt(0, QColor(246, 215, 122, 40))
        grad.setColorAt(1, QColor(246, 215, 122, 0))
        p.setBrush(grad)
        p.drawEllipse(QPointF(x, y), 130, 80)
    plums = 0
    for _ in range(400):                                      # 매화는 글씨·친구들 자리를 피해 가장자리에만
        if plums >= 14:
            break
        x, y = rng.uniform(40, W - 40), rng.uniform(40, H - 40)
        if 225 < x < 1150 and 50 < y < 610:
            continue
        _plum(p, x, y, rng.uniform(1.2, 2.4))
        plums += 1
    p.setPen(QPen(QColor("#D4A017"), 4))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(18, 18, W - 36, H - 36), 26, 26)
    p.setPen(QPen(QColor(212, 160, 23, 140), 1.5))
    p.drawRoundedRect(QRectF(30, 30, W - 60, H - 60), 20, 20)

    def text(rect: QRectF, t: str, size: int, color: str, bold: bool = True, family: str = "Malgun Gothic",
             align=Qt.AlignHCenter | Qt.AlignVCenter) -> None:
        f = QFont(family)
        f.setPixelSize(size)
        f.setBold(bold)
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(rect, align, t)

    kanji, ko, animal = zodiac(year)
    for i, ch in enumerate("謹賀新年"):                        # 세로 글씨
        text(QRectF(70, 70 + i * 120, 140, 120), ch, 104, "#F6D77A", True, "Yu Mincho")
    text(QRectF(260, 70, 880, 110), f"{year}", 104, "#FFFFFF", True)
    text(QRectF(260, 180, 880, 40), f"{kanji} · {ko} · {animal}", 26, "#FFE9EC", True)
    text(QRectF(260, 226, 880, 44), "새해 복 많이 받으세요!  올해도 잘 부탁해요", 30, "#F6D77A", True)
    if shrine_img is not None and not shrine_img.isNull():
        k = min(300 / max(1, shrine_img.width()), 200 / max(1, shrine_img.height()))
        sw, sh = shrine_img.width() * k, shrine_img.height() * k
        p.drawImage(QRectF(700 - sw / 2, 470 - sh, sw, sh), shrine_img)
    friends = [k for k in CHARACTERS if k in s.unlocked]
    size = 104
    gap = min(112.0, (W - 360) / max(1, len(friends)))
    start = 700 - gap * len(friends) / 2
    for i, key in enumerate(friends):
        p.drawPixmap(QRectF(start + i * gap + (gap - size) / 2, 478, size, size).toRect(),
                     portrait(key, size, False, s.skins.get(key)))
    text(QRectF(260, H - 70, 880, 24), f"{s.stage_name}에서  ·  Hokora — 작업표시줄 위의 나만의 신사 · 東方Project二次創作",
         13, "#FFE9EC", False)
    p.end()
    return img


def save_nengajo(s: GameState, year: int, folder: Path, shrine_img: QImage | None = None) -> tuple[QImage, Path]:
    img = make_nengajo(s, year, shrine_img)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"hokora_연하장_{year}_{datetime.now():%m%d_%H%M%S}.png"
    img.save(str(path))
    return img, path
