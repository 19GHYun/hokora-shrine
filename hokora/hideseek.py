# -*- coding: utf-8 -*-
"""숨바꼭질: 친구들이 화면 곳곳에 숨고, 60초 안에 찾아서 누른다.

숨는 곳: 신사 뒤 (옆으로 빼꼼) · 열린 창 윗변 너머 (머리만) · 화면 왼쪽/오른쪽 끝 (반만) ·
작업표시줄 먼 곳 (흐릿하게) · 화면 위 (거꾸로 매달림). 가끔 숨은 곳이 들썩이며 "키득" — 힌트.
찾으면 새전 + 호감도, 모두 찾으면 보너스. 못 찾은 친구는 끝날 때 "여기 있었지롱~" 하고 나온다.
"""
from __future__ import annotations

import logging
import random
import time
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QWidget

from . import affection as aff
from . import wardrobe
from .bubble import say

if TYPE_CHECKING:
    from .app import Game

log = logging.getLogger("Hokora.hide")

HIDE_TIME = 60.0
MAX_HIDERS = 5
MIN_HIDERS = 2
COOLDOWN = 300.0
HINT_EVERY = (7.0, 11.0)
HIDE_DELAY = 1.6            # "숨는다~!" 하고 사라진 뒤 숨는 곳에 나타나기까지
FAR_ALPHA = 0.45


def sprite_pixmap(key: str, skin: str | None, facing: int = 1) -> tuple[QPixmap, QRectF] | None:
    """(서 있는 그림, 그림 안에서 몸이 있는 사각형) — 그림이 없으면 None."""
    sp = wardrobe.sprites_for(key, skin)
    if sp is None:
        return None
    name = sp.sequence("idle")[0]
    pm, anchor = sp.draw(name, 0.0, 0.0, False, facing, 2.0)
    img, a = sp.images[name]
    s = sp.scale
    left = anchor.x() - a.x() * s if facing == sp.facing else anchor.x() - (img.width() - a.x()) * s   # 뒤집혔으면
    body = QRectF(left, anchor.y() - a.y() * s, img.width() * s, img.height() * s)
    return pm, body


class HideSpot(QWidget):
    """숨은 친구가 보이는 조각 (빼꼼). 누르면 찾음."""

    def __init__(self, key: str, pm: QPixmap, crop: QRectF, flip_v: bool, alpha: float,
                 on_click: Callable[["HideSpot"], None]):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setCursor(Qt.PointingHandCursor)
        self.key, self.pm, self.crop, self.flip_v, self.alpha = key, pm, crop, flip_v, alpha
        self.on_click = on_click
        self.found = False
        self.gone = False            # 닫힘 (다시 보이게 하면 안 됨)
        self.wiggle_until = 0.0
        self.setFixedSize(max(8, round(crop.width())), max(8, round(crop.height())))
        self.timer = QTimer(self, timeout=self.update, interval=40)

    def wiggle(self, seconds: float = 0.8) -> None:
        self.wiggle_until = time.monotonic() + seconds
        self.timer.start()

    def reveal(self) -> None:
        self.alpha = 1.0
        self.update()

    def mousePressEvent(self, _e) -> None:
        if not self.found:
            self.on_click(self)

    def paintEvent(self, _e) -> None:
        now = time.monotonic()
        dx = 0.0
        if now < self.wiggle_until:
            dx = 2.5 if int(now * 25) % 2 else -2.5
        elif self.timer.isActive():
            self.timer.stop()
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setOpacity(self.alpha)
        if self.flip_v:                                   # 거꾸로 매달림
            p.setTransform(QTransform(1, 0, 0, -1, 0, self.height()))
        dpr = self.pm.devicePixelRatio()
        src = QRectF(self.crop.x() * dpr, self.crop.y() * dpr, self.crop.width() * dpr, self.crop.height() * dpr)
        p.drawPixmap(QRectF(dx, 0, self.width(), self.height()), self.pm, src)
        p.end()


class HideGame:
    """한 판. Game 이 만들고, 끝나면 game.hide_game = None."""

    def __init__(self, game: "Game", keys: list[str], rng: random.Random | None = None):
        self.game, self.keys = game, keys
        self.rng = rng or random.Random()
        self.spots: dict[str, HideSpot] = {}
        self.found: list[str] = []
        self.earned = 0
        self.started = time.monotonic()
        self.ends = self.started + HIDE_DELAY + HIDE_TIME
        self.next_hint = self.started + HIDE_DELAY + self.rng.uniform(*HINT_EVERY)
        self.over = False
        self.timer = QTimer(game, timeout=self.tick, interval=200)

    # ── 숨기 ──
    def start(self) -> None:
        g = self.game
        for pet in [p for p in g.pets if p.ch.key in self.keys]:
            g.events._say(pet, self.rng.choice(["숨는다~!", "찾아봐~!", "하나, 둘, 셋!"]), 1.4)
            g.pets.remove(pet)
            g._hiding.add(pet.ch.key)
            g.fade_out_pet(pet)
        g.later(HIDE_DELAY, self._hide)
        self.timer.start()
        log.info("숨바꼭질 시작: %s", self.keys)

    def _places(self) -> list[str]:
        kinds = ["shrine_left", "shrine_right", "edge_left", "edge_right", "far", "ceiling"]
        if self.game.window_platforms:
            kinds += ["window", "window"]
        self.rng.shuffle(kinds)
        return kinds

    def _hide(self) -> None:
        if self.over:
            return
        g = self.game
        places = self._places()
        for i, key in enumerate(self.keys):
            made = sprite_pixmap(key, g.state.skins.get(key), self.rng.choice((-1, 1)))
            if made is None:
                continue
            pm, body = made
            spot = self._place(key, pm, body, places[i % len(places)])
            self.spots[key] = spot
            if not g.hidden_for_fullscreen:
                spot.show()
        say("다 숨었어~ 찾아봐!", g.shrine.pos_x, g.shrine.y() + 20, 2.5)

    def _place(self, key: str, pm: QPixmap, body: QRectF, kind: str) -> HideSpot:
        g = self.game
        ground = g.ground_under(g.shrine.pos_x)
        area = QRect(round(ground.x1), round(g.top), round(ground.x2 - ground.x1), round(ground.y - g.top))
        bw, bh = body.width(), body.height()
        alpha, flip = 1.0, False
        if kind in ("shrine_left", "edge_right"):                        # 왼쪽 반만 보임 (오른쪽에서 빼꼼)
            crop = QRectF(body.left(), body.top(), bw * 0.5, bh)
        elif kind in ("shrine_right", "edge_left"):                      # 오른쪽 반만
            crop = QRectF(body.left() + bw * 0.5, body.top(), bw * 0.5, bh)
        elif kind in ("window", "ceiling"):                              # 머리만
            crop = QRectF(body.left(), body.top(), bw, bh * 0.42)
            flip = kind == "ceiling"
        else:                                                            # far: 다 보이지만 흐릿하게
            crop, alpha = QRectF(body), FAR_ALPHA
        spot = HideSpot(key, pm, crop, flip, alpha, self._on_click)
        w, h = spot.width(), spot.height()
        sx, sy = g.shrine.x(), g.shrine.y() + g.shrine.height()
        if kind == "shrine_left":
            x, y = sx + 14 - w, sy - h - 2
        elif kind == "shrine_right":
            x, y = sx + g.shrine.width() - 14, sy - h - 2
        elif kind == "edge_left":
            x, y = area.left(), ground.y - h
        elif kind == "edge_right":
            x, y = area.right() - w + 1, ground.y - h
        elif kind == "ceiling":
            x, y = self.rng.uniform(area.left() + 80, area.right() - 80), area.top()
        elif kind == "window":
            pf = self.rng.choice(g.window_platforms)
            x, y = self.rng.uniform(pf.x1 + 10, max(pf.x1 + 11, pf.x2 - w - 10)), pf.y - h + 3
        else:
            xs = [self.rng.uniform(area.left() + 40, area.right() - 40) for _ in range(12)]
            far = [v for v in xs if abs(v - g.shrine.pos_x) > 320] or xs
            x, y = far[0], ground.y - h
        spot.move(round(x), round(y))
        spot.kind = kind
        return spot

    # ── 진행 ──
    def tick(self) -> None:
        if self.over:
            return
        now = time.monotonic()
        if self.game.hidden_for_fullscreen:                # 전체화면 게임이 켜지면 그만
            self.end(cancelled=True)
            return
        if now >= self.ends:
            self.end()
            return
        if now >= self.next_hint:
            self.next_hint = now + self.rng.uniform(*HINT_EVERY)
            left = [sp for k, sp in self.spots.items() if k not in self.found]
            if left:
                sp = self.rng.choice(left)
                sp.wiggle()
                say(self.rng.choice(["키득", "쉿…", "히히"]), sp.x() + sp.width() / 2, sp.y() - 4, 1.2)

    def left(self) -> float:
        return max(0.0, self.ends - time.monotonic())

    def windows(self) -> list[HideSpot]:
        return [sp for sp in self.spots.values() if not sp.gone]

    def reward_each(self) -> int:
        return max(30, self.game.state.income_per_min * 2)

    def _on_click(self, spot: HideSpot) -> None:
        if self.over or spot.found:
            return
        g, s = self.game, self.game.state
        spot.found = True
        spot.reveal()
        self.found.append(spot.key)
        amount = self.reward_each()
        s.add_saisen(amount)
        s.hide_found += 1
        self.earned += amount
        aff.add(s, spot.key, 1)
        g.shrine.set_saisen(s.saisen)
        g.shrine.pop(f"+{amount:,}")
        say(self.rng.choice(["들켰다~!", "앗, 찾았네!", "어떻게 알았어?!"]), spot.x() + spot.width() / 2, spot.y() - 4, 1.8)
        g.later(0.7, lambda: self._return(spot))
        if len(self.found) == len(self.spots):
            g.later(0.9, self.end)

    def _return(self, spot: HideSpot) -> None:
        g = self.game
        g._hiding.discard(spot.key)
        if spot.key in g._eligible() and not any(p.ch.key == spot.key for p in g.pets):
            g._drop_in(spot.key)
        if not spot.gone:
            spot.gone = True
            spot.close()

    def end(self, cancelled: bool = False) -> None:
        if self.over:
            return
        self.over = True
        self.timer.stop()
        g, s = self.game, self.game.state
        hidden = [sp for k, sp in self.spots.items() if k not in self.found]
        for sp in hidden:
            sp.reveal()
            if not cancelled:
                say("여기 있었지롱~", sp.x() + sp.width() / 2, sp.y() - 4, 2.2)
        bonus = 0
        if self.spots and len(self.found) == len(self.spots) and not cancelled:
            bonus = self.earned // 2
            s.add_saisen(bonus)
        s.hide_games += 1
        g.later(0.1 if cancelled else 2.4, lambda: [self._return(sp) for sp in hidden])
        for k in self.keys:                              # 그림이 없어 못 숨은 친구도 돌아옴
            if k not in self.spots:
                g._hiding.discard(k)
                g._drop_in(k)
        if not cancelled:
            lines = [f"{len(self.found)} / {len(self.spots)}명 찾았다!"]
            if hidden:
                lines.append("못 찾은 친구: " + ", ".join(g.char_name(sp.key) for sp in hidden))
            elif bonus:
                lines.append("모두 찾았다! 보너스까지")
            from .diary import DiaryCard
            g.later(2.8, lambda: g.show_card(DiaryCard("🙈 숨바꼭질", lines, f"새전 +{self.earned + bonus:,}")))
        log.info("숨바꼭질 끝: %d/%d 찾음 (+%d)", len(self.found), len(self.spots), self.earned + bonus)
        g.hide_done()
