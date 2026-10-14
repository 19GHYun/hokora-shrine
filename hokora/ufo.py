# -*- coding: utf-8 -*-
"""누에의 UFO: 가끔 정체불명의 UFO 가 날아와 친구를 빛으로 빨아올린다 (eSheep 의 UFO 오마주).

UFO 를 여러 번 누르면 격추 → 친구가 떨어져 돌아오고 새전. 빨려 올라가는 친구를 마우스로 잡아채도 구출.
못 막으면 친구는 UFO 를 타고 갔다가 AWAY_TIME 뒤 선물을 들고 돌아온다.
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from .app import Game
    from .pet import PetWindow

CHANCE_PER_30S = 1 / 150   # 30초마다 주사위 → 평균 75분에 한 번쯤
FIRST_AFTER = 15 * 60      # 켠 뒤 이만큼은 안 옴
HP = (5, 8)                # 격추까지 누르는 횟수
LIFT_TIME = 9.0            # 다 빨려 올라가기까지 (초)
HOVER = 250.0              # 친구 머리 위 이만큼 높이에 멈춤
AWAY_TIME = 10 * 60        # 끌려간 친구가 돌아오기까지 (초)
FLY_SPEED = 420.0
RAINBOW_CHANCE = 0.08      # 무지개 UFO: 보상 ×3
COLORS = ["#E0413A", "#3DAF5A", "#3F7FE0"]   # 성련선의 빨강·초록·파랑 UFO
UW, UH = 104, 64           # UFO 창 크기
LINES_SAVED = ["살았다…!", "무서웠어~!", "고마워!", "외계인은 없었어…"]
NUE_STEPS = [  # 격추된 UFO 에서 떨어진 누에: (몇 초 뒤, 동작, 몇 초 동안, 말)
    (1.6, "caught", 1.8, "드, 들켰다…!?"),
    (3.6, "skill", 2.4, "정체불명의 UFO의 정체는… 바로 나야!"),
    (6.2, "bow", 1.2, "다음엔 안 들킬 거야~"),
]
NUE_LEAVE = 7.6


def ease(t: float) -> float:
    return t * t * (3 - 2 * t)


class UfoWindow(QWidget):
    """UFO 본체 (누르면 맞음)."""

    def __init__(self, ufo: "Ufo"):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(UW, UH)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("정체불명의 UFO — 여러 번 눌러서 쫓아내요!")
        self.ufo = ufo

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.ufo.hit()

    def paintEvent(self, _e) -> None:
        u = self.ufo
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = UW / 2, UH / 2 + 6
        if u.flash > 0:
            p.translate(math.sin(u.t * 70) * 3 * u.flash, 0)
        if u.rainbow:
            body = QColor.fromHsvF((u.t * 0.35) % 1.0, 0.65, 0.95)
        else:
            body = QColor(u.color)
        dome = QPainterPath()                                         # 유리 지붕
        dome.addEllipse(QRectF(cx - 20, cy - 30, 40, 36))
        p.setPen(QPen(QColor(255, 255, 255, 180), 1.2))
        g = QLinearGradient(0, cy - 30, 0, cy)
        g.setColorAt(0, QColor(200, 240, 255, 220))
        g.setColorAt(1, QColor(120, 190, 230, 150))
        p.setBrush(g)
        p.drawPath(dome)
        if u.passenger:                                               # 끌려간 친구 그림자
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(60, 40, 50, 150))
            p.drawEllipse(QRectF(cx - 7, cy - 22, 14, 14))
        rim = QRectF(cx - 48, cy - 10, 96, 26)                        # 접시
        g2 = QLinearGradient(0, rim.top(), 0, rim.bottom())
        g2.setColorAt(0, body.lighter(140))
        g2.setColorAt(0.5, body)
        g2.setColorAt(1, body.darker(170))
        p.setPen(QPen(body.darker(200), 1.5))
        p.setBrush(g2)
        p.drawEllipse(rim)
        for i in range(6):                                            # 깜빡이는 불빛
            a = math.pi * (0.15 + 0.7 * i / 5)
            x = cx - math.cos(a) * 40
            on = int(u.t * 6 + i) % 3 == 0
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 240, 120) if on else QColor(255, 255, 255, 150))
            p.drawEllipse(QPointF(x, cy + 6), 3.2, 3.2)
        if u.hp_max:                                                  # 남은 힘
            w = 50 * max(0, u.hp) / u.hp_max
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 70))
            p.drawRoundedRect(QRectF(cx - 25, 2, 50, 5), 2, 2)
            p.setBrush(QColor("#F2C230"))
            p.drawRoundedRect(QRectF(cx - 25, 2, w, 5), 2, 2)
        if u.flash > 0:                                               # 맞은 순간 번쩍
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, int(170 * u.flash)))
            p.drawEllipse(rim.adjusted(-4, -16, 4, 4))
        if u.phase == "hit":                                          # 격추: 연기
            for i in range(4):
                ph = (u.t * 1.6 + i / 4) % 1.0
                p.setBrush(QColor(90, 90, 90, int(140 * (1 - ph))))
                p.drawEllipse(QPointF(cx + 30 - i * 14, cy - 6 - ph * 22), 5 + ph * 7, 5 + ph * 7)
        p.end()


class BeamWindow(QWidget):
    """빨아올리는 빛 (클릭은 통과)."""

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.t = 0.0

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cone = QPainterPath(QPointF(w / 2 - 16, 0))
        cone.lineTo(w / 2 + 16, 0)
        cone.lineTo(w - 4, h)
        cone.lineTo(4, h)
        cone.closeSubpath()
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor(220, 255, 170, 120))
        g.setColorAt(1, QColor(220, 255, 170, 40))
        p.fillPath(cone, g)
        p.setClipPath(cone)
        p.setPen(QPen(QColor(255, 255, 220, 90), 2))
        for i in range(6):                                            # 위로 올라가는 빛 줄
            y = h - ((self.t * 90 + i * h / 6) % h)
            p.drawLine(QPointF(0, y), QPointF(w, y))
        glow = QRadialGradient(QPointF(w / 2, h), w / 2)
        glow.setColorAt(0, QColor(240, 255, 200, 90))
        glow.setColorAt(1, QColor(240, 255, 200, 0))
        p.setClipping(False)
        p.fillRect(QRectF(0, h - 30, w, 30), glow)
        p.end()


class Ufo:
    """UFO 한 번 (Game 이 매 프레임 step). 다 끝나면 done."""

    def __init__(self, game: "Game", pet: "PetWindow", rng: random.Random | None = None):
        rng = rng or random.Random()
        self.game, self.pet = game, pet
        self.rainbow = rng.random() < RAINBOW_CHANCE
        self.color = rng.choice(COLORS)
        self.hp = self.hp_max = rng.randint(*HP)
        self.t = 0.0
        self.flash = 0.0
        self.phase = "arrive"
        self.passenger = False
        self.done = False
        self.lift = 0.0
        self.y0 = 0.0
        self.side = rng.choice((-1, 1))
        self.x = game.left - UW if self.side < 0 else game.right + UW
        self.y = game.top + 50
        self.hit_at = 0.0
        self.win = UfoWindow(self)
        self.beam = BeamWindow()
        self._place()
        self.win.show()

    def windows(self) -> list[QWidget]:
        return [self.beam, self.win] if self.beam.isVisible() else [self.win]

    @property
    def target(self) -> tuple[float, float]:
        return self.pet.pos_x, max(self.game.top + 60, self.pet.pos_y - HOVER)

    def _free(self) -> bool:
        """친구가 아직 데려갈 수 있는 상태인가 (사라졌거나 사용자가 잡고 있으면 아님)."""
        p = self.pet
        return p in self.game.pets and p.isVisible() and p._press_pos is None

    def step(self, dt: float) -> None:
        self.t += dt
        self.flash = max(0.0, self.flash - dt * 3)
        self.beam.t = self.t
        if self.phase == "arrive":
            if not self._free() or (self.pet.scripted and not self.lift):
                self._leave()
            else:
                tx, ty = self.target
                dx, dy = tx - self.x, ty - self.y
                d = math.hypot(dx, dy)
                if d <= FLY_SPEED * dt + 2:
                    self.x, self.y = tx, ty
                    self._start_beam()
                else:
                    self.x += dx / d * FLY_SPEED * dt
                    self.y += dy / d * FLY_SPEED * dt
        elif self.phase == "beam":
            if not self._free():                       # 사용자가 잡아채서 구출
                self._rescued()
            else:
                self.lift = min(1.0, self.lift + dt / LIFT_TIME)
                p = self.pet
                top = self.y + UH / 2 + 20
                p.pos_x = self.x + math.sin(self.t * 3) * 4
                p.pos_y = self.y0 + (top - self.y0) * ease(self.lift)
                p.state, p.on, p.vx, p.vy = "held", None, 0.0, 0.0
                p._place()
                p.update()
                if self.lift >= 1.0:
                    self._abduct()
        elif self.phase == "hit":
            self.y += math.sin(self.t * 20) * 0.6
            if self.t - self.hit_at > 0.9:
                self._leave()
        elif self.phase == "leave":
            self.x += self.side * 320 * dt
            self.y -= 280 * dt
            if self.y < self.game.top - UH - 20 or not self.game.left - 200 < self.x < self.game.right + 200:
                self.close()
                return
        self._place()

    def _place(self) -> None:
        bob = math.sin(self.t * 2.4) * 4 if self.phase in ("arrive", "beam") else 0.0
        self.win.move(round(self.x - UW / 2), round(self.y - UH / 2 + bob))
        self.win.update()
        if self.beam.isVisible():
            self.beam.move(round(self.x - self.beam.width() / 2), round(self.y + UH / 2 - 8 + bob))
            self.beam.update()

    def _start_beam(self) -> None:
        p = self.pet
        self.phase = "beam"
        self.y0 = p.pos_y
        p.scripted = True
        p._follow = p._to_cursor = False
        h = max(40, round(self.y0 - (self.y + UH / 2 - 8) + 6))
        self.beam.setFixedSize(110, h)
        if not self.game.hidden_for_fullscreen:
            self.beam.show()
            self.game._restack()
        self.game.ufo_beam(p)

    def hit(self) -> None:
        """UFO 를 누름."""
        if self.phase not in ("arrive", "beam"):
            return
        self.hp -= 1
        self.flash = 1.0
        if self.hp <= 0:
            self._shot_down()

    def _release(self) -> None:
        """빛을 끄고 친구를 놓아줌 (떨어지다 착지하면 신남)."""
        self.beam.hide()
        p = self.pet
        if p.scripted and self.phase == "beam":
            p.scripted = False
            if p._press_pos is None:
                p.state, p.on, p.vx, p.vy = "fall", None, 0.0, 0.0
                p._slid = True                          # 착지하면 폴짝 (미끄럼 착지와 같은 신남)

    def _shot_down(self) -> None:
        was_beam = self.phase == "beam"
        self._release()
        self.phase, self.hit_at = "hit", self.t
        self.game.ufo_shot(self, was_beam)

    def _rescued(self) -> None:
        self._release()
        self.phase = "leave"
        self.game.ufo_rescued(self)

    def _abduct(self) -> None:
        self.beam.hide()
        self.passenger = True
        self.pet.scripted = False
        self.phase = "leave"
        self.game.ufo_abduct(self.pet)

    def _leave(self) -> None:
        self._release()
        self.phase = "leave"

    def cancel(self) -> None:
        """전체화면·낮잠: 조용히 친구를 내려놓고 사라짐."""
        self._release()
        self.close()

    def close(self) -> None:
        self.done = True
        for w in (self.win, self.beam):
            w.close()
            w.deleteLater()


def nue_appears(game: "Game", x: float, y: float) -> "PetWindow | None":
    """격추된 UFO 에서 누에가 떨어져 "들켰다!" 하고는 사라짐 (그림이 있을 때만)."""
    from .guests import fade
    from .pet import PetWindow
    from .render import GUESTS
    from .sprites import image_sprites
    if image_sprites("nue") is None or game.hidden_for_fullscreen:
        return None
    pet = PetWindow(GUESTS["nue"], game, x)
    pet.pos_x, pet.pos_y = x, y
    pet.state, pet.on, pet.vx, pet.vy, pet.scripted = "fall", None, 0.0, 0.0, True
    pet.facing = 1 if x < game.shrine.pos_x else -1
    pet._place()
    game.guests.append(pet)
    pet.show()

    def act(kind: str, secs: float, text: str) -> None:
        if pet in game.guests and pet.on is not None:
            pet.act(kind, secs)
            game.events._say(pet, text, secs + 0.6)

    def leave() -> None:
        if pet in game.guests:
            game.guests.remove(pet)
            fade(pet, 0.0, 0.8, lambda: (pet.close(), pet.deleteLater()))
    for at, kind, secs, text in NUE_STEPS:
        game.later(at, lambda kind=kind, secs=secs, text=text: act(kind, secs, text))
    game.later(NUE_LEAVE, leave)
    return pet
