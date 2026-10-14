# -*- coding: utf-8 -*-
"""신사 안 들여다보기: 쉬는 친구들이 코타츠(여름엔 밥상)에 둘러앉아 귤을 까먹거나 낮잠을 잔다.

둥근 창 너머로 지금 시간·계절·날씨·진짜 달, 도코노마엔 칭호 족자와 지닌 부적, 어항엔 낚은 물고기.
안에 있는 친구 = 해금했지만 지금 작업표시줄에 안 나와 있고 원정도 안 간 친구 (Game.room_friends).
"""
from __future__ import annotations

import math
import random
import time
from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QGuiApplication, QLinearGradient, QPainter, QPainterPath,
                           QPen, QRadialGradient)
from PySide6.QtWidgets import QWidget

from . import achievements, expedition, fishing, moon, omamori, season, wardrobe, weather
from .pet import _heart, _zzz
from .render import CHARACTERS, Pose, draw_character
from .sprites import DISPLAY_H

if TYPE_CHECKING:
    from .app import Game

W, H = 600, 400
ROOM_H = 360                 # 아래 40px 은 안내 줄
FLOOR_Y = 250
K = 1.45                     # 방 안 친구 크기 (작업표시줄의 몇 배)
WIN_C, WIN_R = QPointF(108, 100), 58      # 둥근 창
SYNC_EVERY = 2.0
# 자리: (발 x, 발 y, 바라보는 쪽, 층 0=상 뒤 1=상 옆 2=앞, 자세)
SLOTS = [
    (238, 240, 1, 0, "sit"), (362, 240, -1, 0, "sit"),
    (170, 318, 1, 1, "sit"), (430, 318, -1, 1, "sit"),
    (84, 352, 1, 2, "sleep"), (522, 352, -1, 2, "sleep"),
]
ROOM_LINES = {
    "reimu": ["코타츠에서 나가기 싫어…", "새전함은… 내일 볼래.", "차가 딱 좋게 우러났네."],
    "marisa": ["여기 따뜻하다제~", "귤 하나만 더 먹을게다제!", "레이무, 이 책 빌려 간다제."],
    "cirno": ["코타츠는 너무 뜨거워…! 그래도 좋아!", "귤 얼려 먹으면 더 맛있어!", "아타이는 최강이라 안 졸려…"],
    "sakuya": ["차를 새로 내올게요.", "아가씨가 찾으시기 전까지만 쉴게요.", "귤 껍질은 제가 치울게요."],
    "sanae": ["모리야 신사에도 코타츠 놔야겠어요!", "귤 까 드릴까요?", "기적처럼 따뜻하네요~"],
    "remilia": ["…이 정도면 나쁘지 않네.", "홍차는 없어? 녹차도 괜찮아.", "햇빛만 안 들면 어디든 좋아."],
    "flandre": ["언니, 귤 까 줘~", "코타츠 안에서 숨바꼭질하자!", "따뜻해서 졸려…"],
    "youmu": ["유유코 님이 이 귤을 보시면 큰일이에요…", "잠깐만 쉬었다 갈게요.", "칼은 저쪽에 세워 둘게요."],
    "meiling": ["여긴 지킬 문이 없어서 편하네요~", "쿨… 앗, 안 잤어요!", "기공으로 데운 차예요!"],
}
COMMON = ["따뜻하다~", "조금만 더 있을래…", "귤 맛있다!"]
SUMMER = ["수박 시원하다~", "더워… 부채질 좀…", "보리차 한 잔 더!"]
SLEEPY = ["쿨…", "음냐… 새전…", "5분만 더…"]
MIKAN = ["귤 맛있다~", "손이 노랗게 됐어!", "하나만 더…", "껍질로 토끼 만들었어!"]
MELON = ["수박 맛있다~", "씨 멀리 뱉기 하자!", "하나만 더…"]
FISH_IN_BOWL = ("golden_koi", "koi", "goldfish", "eel", "catfish", "funa", "medaka")


def friend_line(key: str, summer: bool, asleep: bool) -> str:
    if asleep:
        return random.choice(SLEEPY)
    lines = [ln for ln in ROOM_LINES.get(key, []) if not (summer and "코타츠" in ln)]
    return random.choice(lines + (SUMMER if summer else COMMON))


def draw_friend(p: QPainter, key: str, skin: str | None, kind: str, t: float, x: float, y: float,
                k: float, facing: int) -> None:
    """방 안 친구 한 명 (발이 (x, y))."""
    images = wardrobe.sprites_for(key, skin)
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 38))
    p.drawEllipse(QRectF(x - 20 * k, y - 4 * k, 40 * k, 8 * k))
    if images is None:
        r = QRectF(x - 28 * k, y - 67 * k, 56 * k, 67 * k)
        draw_character(p, CHARACTERS[key], Pose(kind={"sleep": "sleep", "happy": "happy"}.get(kind, "sit"),
                                                 t=t, facing=facing), r)
        p.restore()
        return
    loop = {"sit": 8.0, "sleep": 4.0, "happy": 1.0}.get(kind, 2.856)
    name, dy, _angle, _ = images.pick(kind, (t % loop) / loop, t, False)
    img, anchor = images.images[name]
    s = images.scale * k
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.translate(x, y + dy * k)
    if facing != images.facing:
        p.scale(-1, 1)
    p.drawImage(QRectF(-anchor.x() * s, -anchor.y() * s, img.width() * s, img.height() * s), img)
    p.restore()


class RoomWindow(QWidget):
    def __init__(self, game: "Game", invited: list[str]):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFixedSize(W, H)
        self.game = game
        self.invited = invited
        self.t = 0.0
        self.seats: dict[str, int] = {}                  # 친구 → SLOTS 번호
        self.happy_until: dict[str, float] = {}
        self.bubbles: list[list] = []                    # [친구, 글, 끝나는 시각]
        self.hearts: list[list[float]] = []              # [나이, x, y]
        self.hits: dict[str, QRectF] = {}
        self.eaten = 0
        self.particles: list[list[float]] = []           # 둥근 창 밖 [x, y, vx, vy, 크기, 각도, 씨앗]
        self._drag = None
        self._last = time.monotonic()
        self._synced = 0.0
        self.close_rect = QRectF(W - 34, 8, 24, 24)
        self.basket_rect = QRectF(268, 198, 64, 32)        # 상 가운데 (뒤에 앉은 두 친구 사이)
        self.sync()
        self.timer = QTimer(self, timeout=self._tick, interval=66)
        self.timer.start()

    # ── 상태 ──
    @property
    def summer(self) -> bool:
        return season.season() == "summer"

    @property
    def night(self) -> bool:
        return season.is_night()

    def asleep(self, key: str) -> bool:
        slot = SLOTS[self.seats[key]]
        return (self.night or slot[4] == "sleep") and time.monotonic() >= self.happy_until.get(key, 0.0)

    def sync(self) -> None:
        """안에 있는 친구가 바뀌었으면 자리를 다시 (나간 친구는 빼고, 들어온 친구는 빈자리로)."""
        friends = self.game.room_friends()
        self.seats = {k: i for k, i in self.seats.items() if k in friends}
        free = [i for i in range(len(SLOTS)) if i not in self.seats.values()]
        random.shuffle(free)
        free.sort(key=lambda i: SLOTS[i][3])            # 상 둘레부터 채움
        for k in friends:
            if k not in self.seats and free:
                self.seats[k] = free.pop(0)
        self._synced = time.monotonic()

    def _tick(self) -> None:
        now = time.monotonic()
        dt = min(0.2, now - self._last)
        self._last = now
        self.t += dt
        if now - self._synced > SYNC_EVERY:
            self.sync()
        self.bubbles = [b for b in self.bubbles if b[2] > now]
        for h in self.hearts:
            h[0] += dt
        self.hearts = [h for h in self.hearts if h[0] < 1.2]
        self._step_particles(dt)
        self.update()

    def _step_particles(self, dt: float) -> None:
        kind = self._outside_kind()
        rate = {"snow": 7, "petal": 3, "leaf": 2, "rain": 26, "firefly": 0.6}.get(kind, 0)
        if rate and random.random() < rate * dt:
            x = WIN_C.x() + random.uniform(-WIN_R, WIN_R)
            if kind == "rain":
                self.particles.append([x, WIN_C.y() - WIN_R, -30, 420, 1, 0, random.random(), 0])
            elif kind == "firefly":
                self.particles.append([x, WIN_C.y() + random.uniform(0, WIN_R * 0.7), random.uniform(-8, 8),
                                       random.uniform(-6, 2), 1, 0, random.random(), 0])
            else:
                self.particles.append([x, WIN_C.y() - WIN_R - 4, random.uniform(-14, 6), random.uniform(16, 30),
                                       random.uniform(3, 5), random.uniform(0, 360), random.random(), 0])
        for q in self.particles:
            q[0] += q[2] * dt
            q[1] += q[3] * dt
            q[5] += 60 * dt
            q[7] += dt
        self.particles = [q for q in self.particles
                          if q[1] < WIN_C.y() + WIN_R + 6 and q[7] < 9][-60:]

    def _outside_kind(self) -> str:
        wk = weather.current().key
        if wk in ("drizzle", "storm", "sunshower"):
            return "rain"
        sn = season.season()
        if sn == "winter":
            return "snow"
        if sn == "spring":
            return "petal"
        if sn == "autumn":
            return "leaf"
        return "firefly" if self.night else ""

    # ── 마우스 ──
    def mousePressEvent(self, e) -> None:
        pos = e.position()
        if e.button() != Qt.LeftButton:
            return
        if self.close_rect.contains(pos):
            self.close()
            return
        for key, r in sorted(self.hits.items(), key=lambda kv: -SLOTS[self.seats.get(kv[0], 0)][3]):
            if r.contains(pos):
                self.poke(key)
                return
        if self.basket_rect.contains(pos):
            self.eat()
            return
        self._drag = e.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, e) -> None:
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _e) -> None:
        self._drag = None

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.close()

    def poke(self, key: str) -> None:
        """친구를 누름: 깨어나서 폴짝, 한마디."""
        if key not in self.seats:
            return
        asleep = self.asleep(key)
        self.happy_until[key] = time.monotonic() + (1.0 if not asleep else 0.0)
        self.say(key, friend_line(key, self.summer, asleep))
        x, y = self._head(key)
        if not asleep:
            self.hearts.append([0.0, x, y])

    def eat(self) -> str | None:
        """귤(여름엔 수박) 바구니: 안에 있는 친구 하나가 냠."""
        if not self.seats:
            return None
        key = random.choice(list(self.seats))
        self.eaten += 1
        self.happy_until[key] = time.monotonic() + 1.0
        self.say(key, random.choice(MELON if self.summer else MIKAN))
        self.game.on_room_snack()
        return key

    def say(self, key: str, text: str) -> None:
        self.bubbles = [b for b in self.bubbles if b[0] != key] + [[key, text, time.monotonic() + 2.8]]

    def _head(self, key: str) -> tuple[float, float]:
        x, y, *_ = SLOTS[self.seats[key]]
        return x, y - DISPLAY_H * K * (0.62 if self.asleep(key) else 0.8)

    def closeEvent(self, e) -> None:
        self.timer.stop()
        self.game.room_closed()
        super().closeEvent(e)

    def place_near(self, x: float, y: float) -> None:
        sc = QGuiApplication.screenAt(QPointF(x, y).toPoint()) or QGuiApplication.primaryScreen()
        a = sc.availableGeometry()
        self.move(round(min(max(x - W / 2, a.left() + 8), a.right() - W - 8)),
                  round(min(max(y - H - 16, a.top() + 8), a.bottom() - H - 8)))

    # ── 그리기 ──
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        outline = QPainterPath()
        outline.addRoundedRect(QRectF(1, 1, W - 2, H - 2), 16, 16)
        p.setClipPath(outline)
        self._wall(p)
        self._round_window(p)
        self._tokonoma(p)
        self._floor(p)
        self._fishbowl(p)
        self.hits = {}
        order = sorted(self.seats.items(), key=lambda kv: (SLOTS[kv[1]][3], SLOTS[kv[1]][1]))
        for key, i in order:                             # 상 뒤 친구 → 상 → 상 옆·앞 친구
            if SLOTS[i][3] == 0:
                self._friend(p, key, i)
        self._kotatsu(p)
        for key, i in order:
            if SLOTS[i][3] > 0:
                self._friend(p, key, i)
        if self.night:
            self._night(p)
        if not self.seats:
            self._empty_note(p)
        for age, hx, hy in self.hearts:
            a = max(0.0, 1 - age / 1.2)
            _heart(p, hx, hy - age * 26, 10 + age * 3, QColor(235, 70, 100, int(230 * a)))
        taken: list[QRectF] = []
        for key, text, _until in self.bubbles:
            if key in self.seats:
                taken.append(self._bubble(p, *self._head(key), text, taken))
        self._footer(p)
        self._close_button(p)
        p.setClipping(False)
        p.setPen(QPen(QColor("#C8102E"), 2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(outline)
        p.end()

    def _wall(self, p: QPainter) -> None:
        g = QLinearGradient(0, 0, 0, FLOOR_Y)
        g.setColorAt(0, QColor("#EFE0C4"))
        g.setColorAt(1, QColor("#E3CFAA"))
        p.fillRect(QRectF(0, 0, W, FLOOR_Y), g)
        shoji = QRectF(194, 48, 212, FLOOR_Y - 48 - 4)   # 가운데 미닫이 (장지문)
        p.fillRect(shoji, QColor("#F8F2E4"))
        p.setPen(QPen(QColor("#9C6B42"), 2))
        for i in range(1, 8):
            x = shoji.left() + i * shoji.width() / 8
            p.drawLine(QPointF(x, shoji.top()), QPointF(x, shoji.bottom()))
        for j in range(1, 6):
            y = shoji.top() + j * shoji.height() / 6
            p.drawLine(QPointF(shoji.left(), y), QPointF(shoji.right(), y))
        p.setPen(QPen(QColor("#7A4E2D"), 5))
        p.setBrush(Qt.NoBrush)
        p.drawRect(shoji)
        p.drawLine(QPointF(shoji.center().x(), shoji.top()), QPointF(shoji.center().x(), shoji.bottom()))
        wood = QColor("#6E4528")
        p.fillRect(QRectF(0, 0, W, 16), QColor("#5B3A22"))          # 천장 들보
        p.fillRect(QRectF(0, 40, W, 7), wood)                         # 나게시
        for x in (0, 186, 414, W - 14):                               # 기둥
            p.fillRect(QRectF(x, 0, 14, FLOOR_Y), wood)
        lamp = QRectF(W / 2 - 20, 18, 40, 22)                         # 종이 등
        p.setPen(QPen(QColor("#8A5A32"), 1.2))
        p.setBrush(QColor("#FFF1C9") if not self.night else QColor("#FFD27A"))
        p.drawRoundedRect(lamp, 10, 10)
        p.drawLine(QPointF(W / 2, 16), QPointF(W / 2, 18))

    def _round_window(self, p: QPainter) -> None:
        c, r = WIN_C, WIN_R
        circle = QPainterPath()
        circle.addEllipse(c, r, r)
        p.save()
        p.setClipPath(circle, Qt.IntersectClip)
        h = datetime.now().hour
        sky = QLinearGradient(0, c.y() - r, 0, c.y() + r)
        if self.night:
            sky.setColorAt(0, QColor("#141A3A"))
            sky.setColorAt(1, QColor("#33396A"))
        elif 17 <= h < 19:
            sky.setColorAt(0, QColor("#6C78C9"))
            sky.setColorAt(1, QColor("#FFA27A"))
        elif 5 <= h < 7:
            sky.setColorAt(0, QColor("#9CC8F0"))
            sky.setColorAt(1, QColor("#FFD3A8"))
        else:
            sky.setColorAt(0, QColor("#8EC9F5"))
            sky.setColorAt(1, QColor("#DDF1FF"))
        p.fillRect(QRectF(c.x() - r, c.y() - r, r * 2, r * 2), sky)
        rng = random.Random(7)
        if self.night:
            p.setPen(Qt.NoPen)
            for _ in range(14):                                       # 별
                tw = 0.5 + 0.5 * math.sin(self.t * 2 + rng.random() * 6)
                p.setBrush(QColor(255, 255, 230, int(90 + 120 * tw)))
                p.drawEllipse(QPointF(c.x() + rng.uniform(-r, r), c.y() + rng.uniform(-r, r * 0.4)), 1.1, 1.1)
            moon.draw(p, c.x() + 18, c.y() - 20, 13, dark=QColor(40, 46, 90, 200))
        sn = season.season()
        hill = QPainterPath(QPointF(c.x() - r, c.y() + r))             # 먼 산
        hill.lineTo(c.x() - r, c.y() + 24)
        hill.quadTo(c.x() - 20, c.y() + 2, c.x() + 10, c.y() + 26)
        hill.quadTo(c.x() + 36, c.y() + 12, c.x() + r, c.y() + 30)
        hill.lineTo(c.x() + r, c.y() + r)
        hill.closeSubpath()
        hill_color = {"spring": "#9CC98A", "summer": "#5FA35A", "autumn": "#C9874A", "winter": "#E9EEF5"}[sn]
        p.fillPath(hill, QColor(hill_color).darker(150) if self.night else QColor(hill_color))
        self._branch(p, sn)
        for x, y, _vx, _vy, size, ang, seed, _age in self.particles:
            kind = self._outside_kind()
            if kind == "snow":
                season.draw_snow(p, x, y, size * 0.6, 0.9)
            elif kind == "petal":
                season.draw_petal(p, x, y, size, ang, 0.9)
            elif kind == "leaf":
                season.draw_leaf(p, x, y, size + 1, ang, 0.9, season.LEAF_COLORS[int(seed * 4) % 4])
            elif kind == "rain":
                p.setPen(QPen(QColor(200, 220, 255, 150), 1))
                p.drawLine(QPointF(x, y), QPointF(x - 2, y + 7))
            elif kind == "firefly":
                season.draw_firefly(p, x, y, 0.5 + 0.5 * math.sin(self.t * 3 + seed * 6))
        p.restore()
        p.setPen(QPen(QColor("#7A4E2D"), 1.6))                         # 대나무 창살
        for dx in (-22, 0, 22):
            half = math.sqrt(max(0.0, r * r - dx * dx))
            p.drawLine(QPointF(c.x() + dx, c.y() - half), QPointF(c.x() + dx, c.y() + half))
        p.setPen(QPen(QColor("#6E4528"), 7))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, r, r)

    def _branch(self, p: QPainter, sn: str) -> None:
        """창 위쪽을 가로지르는 계절 가지."""
        c, r = WIN_C, WIN_R
        p.setPen(QPen(QColor("#5B3A22"), 3, Qt.SolidLine, Qt.RoundCap))
        path = QPainterPath(QPointF(c.x() + r, c.y() - r * 0.7))
        path.quadTo(c.x() + 10, c.y() - r * 0.55, c.x() - r * 0.5, c.y() - r * 0.95)
        p.drawPath(path)
        rng = random.Random(3)
        p.setPen(Qt.NoPen)
        if sn == "winter":
            for i in range(6):
                t = i / 5
                pt = path.pointAtPercent(t)
                p.setBrush(QColor(255, 255, 255, 235))
                p.drawEllipse(QRectF(pt.x() - 5, pt.y() - 5, 10, 5))
            return
        color = {"spring": QColor("#F6B8CC"), "summer": QColor("#4E9A47"), "autumn": QColor("#D9412E")}[sn]
        for i in range(11):
            pt = path.pointAtPercent(i / 10)
            p.setBrush(color.lighter(100 + rng.randint(0, 25)))
            rr = rng.uniform(3.5, 6)
            p.drawEllipse(QPointF(pt.x() + rng.uniform(-5, 5), pt.y() + rng.uniform(-4, 6)), rr, rr * 0.8)

    def _tokonoma(self, p: QPainter) -> None:
        s = self.game.state
        p.fillRect(QRectF(428, 48, W - 14 - 428, FLOOR_Y - 48), QColor("#E2CCA5"))
        p.fillRect(QRectF(428, 226, W - 14 - 428, 24), QColor("#8E6038"))          # 도코이타
        p.fillRect(QRectF(428, 226, W - 14 - 428, 3), QColor("#A8784A"))
        scroll = QRectF(476, 62, 62, 136)                                            # 족자
        p.fillRect(scroll.adjusted(-6, 0, 6, 0), QColor("#6F7F5C"))
        paper = scroll.adjusted(2, 10, -2, -10)
        p.fillRect(paper, QColor("#FBF6EA"))
        p.fillRect(QRectF(scroll.left() - 10, scroll.top() - 5, scroll.width() + 20, 6), QColor("#3E2A1C"))
        p.fillRect(QRectF(scroll.left() - 10, scroll.bottom() - 1, scroll.width() + 20, 6), QColor("#3E2A1C"))
        text = achievements.title(s) or s.stage_name
        chars = [ch for ch in text if ch != " "][:8]
        size = 15 if len(chars) <= 5 else 11
        f = QFont("Malgun Gothic", size)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#2B2224"))
        step = min(paper.height() / max(1, len(chars)), size * 1.9)
        y0 = paper.center().y() - step * len(chars) / 2
        for i, ch in enumerate(chars):
            p.drawText(QRectF(paper.left(), y0 + i * step, paper.width(), step), Qt.AlignCenter, ch)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#C8102E"))
        p.drawRect(QRectF(paper.right() - 13, paper.bottom() - 15, 9, 9))           # 낙관
        for i, key in enumerate(s.equipped[:3]):                                     # 지닌 부적
            ch = omamori.CHARMS.get(key)
            if ch is None:
                continue
            x = 444 + i * 22
            bag = QRectF(x, 198, 16, 26)
            p.setBrush(QColor(ch.color))
            p.setPen(QPen(QColor(ch.color).darker(140), 1))
            p.drawRoundedRect(bag, 4, 4)
            p.setBrush(QColor(255, 250, 235))
            p.setPen(Qt.NoPen)
            p.drawRect(QRectF(x + 4, 204, 8, 13))
            p.setPen(QPen(QColor("#E8B923"), 1.4))
            p.drawLine(QPointF(x + 8, 198), QPointF(x + 8, 192))
        vase = QPainterPath(QPointF(552, 226))                                       # 꽃병
        vase.cubicTo(540, 214, 548, 196, 556, 192)
        vase.lineTo(564, 192)
        vase.cubicTo(572, 196, 580, 214, 568, 226)
        vase.closeSubpath()
        p.fillPath(vase, QColor("#3B5C8C"))
        flower = {"spring": "#F6B8CC", "summer": "#7FA8E0", "autumn": "#D9412E", "winter": "#C8102E"}[season.season()]
        p.setPen(QPen(QColor("#4E6B3A"), 1.6))
        for dx, top in ((-8, 150), (2, 140), (10, 158)):
            p.drawLine(QPointF(560, 194), QPointF(560 + dx, top))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(flower))
        for dx, top in ((-8, 150), (2, 140), (10, 158)):
            p.drawEllipse(QPointF(560 + dx, top), 6, 6)

    def _floor(self, p: QPainter) -> None:
        g = QLinearGradient(0, FLOOR_Y, 0, ROOM_H)
        g.setColorAt(0, QColor("#CFC383"))
        g.setColorAt(1, QColor("#DCD196"))
        p.fillRect(QRectF(0, FLOOR_Y, W, ROOM_H - FLOOR_Y), g)
        p.setPen(QPen(QColor(120, 110, 50, 26), 1))
        for y in range(FLOOR_Y + 4, ROOM_H, 4):                                       # 다다미 결
            p.drawLine(QPointF(0, y), QPointF(W, y))
        p.setPen(QPen(QColor("#3E4A2E"), 3))                                           # 다다미 테두리
        p.drawLine(QPointF(0, FLOOR_Y + 1), QPointF(W, FLOOR_Y + 1))
        for x in (150, 300, 450):
            p.drawLine(QPointF(x, FLOOR_Y + 1), QPointF(x, 306))
        p.drawLine(QPointF(0, 306), QPointF(W, 306))
        for x in (75, 225, 375, 525):
            p.drawLine(QPointF(x, 306), QPointF(x, ROOM_H))

    def _fishbowl(self, p: QPainter) -> None:
        s = self.game.state
        p.fillRect(QRectF(46, 212, 124, 8), QColor("#8E6038"))                        # 선반
        p.fillRect(QRectF(56, 220, 6, 10), QColor("#6E4528"))
        p.fillRect(QRectF(154, 220, 6, 10), QColor("#6E4528"))
        fish = [k for k in FISH_IN_BOWL if s.fish.get(k)][:3]
        if not fish:
            return
        bowl = QRectF(78, 168, 62, 44)
        path = QPainterPath()
        path.addEllipse(bowl)
        p.save()
        p.setClipPath(path, Qt.IntersectClip)
        water = QRectF(bowl.left(), bowl.top() + 10, bowl.width(), bowl.height())
        p.fillRect(water, QColor(120, 190, 235, 120))
        for i, key in enumerate(fish):
            fx = bowl.center().x() + math.sin(self.t * 0.7 + i * 2.1) * 16
            fy = bowl.top() + 20 + i * 7 + math.sin(self.t * 1.3 + i) * 2
            going = math.cos(self.t * 0.7 + i * 2.1)
            p.save()
            p.translate(fx, fy)
            if going < 0:
                p.scale(-1, 1)
            fishing.draw_icon(p, QRectF(-10, -6, 20, 12), key)
            p.restore()
        p.restore()
        p.setPen(QPen(QColor(255, 255, 255, 170), 1.4))
        p.setBrush(QColor(255, 255, 255, 30))
        p.drawEllipse(bowl)
        p.setPen(QPen(QColor(255, 255, 255, 200), 2))
        p.drawArc(bowl.adjusted(8, 6, -30, -20), 100 * 16, 70 * 16)

    def _kotatsu(self, p: QPainter) -> None:
        summer = self.summer
        if summer:                                                                     # 여름: 동그란 밥상
            p.setPen(QPen(QColor("#5B3A22"), 1.5))
            p.setBrush(QColor("#7A4E2D"))
            p.drawRect(QRectF(214, 240, 10, 26))
            p.drawRect(QRectF(376, 240, 10, 26))
            p.setBrush(QColor("#A0693E"))
            p.drawEllipse(QRectF(196, 222, 208, 26))
            p.setBrush(QColor("#B57A4A"))
            p.drawEllipse(QRectF(198, 220, 204, 22))
        else:
            futon = QPainterPath(QPointF(186, 236))
            futon.lineTo(414, 236)
            futon.cubicTo(428, 262, 440, 290, 436, 304)
            futon.lineTo(164, 304)
            futon.cubicTo(160, 290, 172, 262, 186, 236)
            futon.closeSubpath()
            p.setPen(QPen(QColor("#8C1F2B"), 1.5))
            p.setBrush(QColor("#B8323F"))
            p.drawPath(futon)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 236, 214, 150))
            rng = random.Random(11)
            for _ in range(22):                                                        # 이불 무늬
                p.drawEllipse(QPointF(rng.uniform(180, 420), rng.uniform(246, 298)), 3.2, 3.2)
            p.setBrush(QColor("#9C6B42"))
            p.setPen(QPen(QColor("#6E4528"), 1.5))
            p.drawRoundedRect(QRectF(192, 224, 216, 14), 3, 3)
        self._snack(p, summer)

    def _snack(self, p: QPainter, summer: bool) -> None:
        b = self.basket_rect
        left = max(1, 5 - self.eaten % 5)
        if summer:
            p.setPen(QPen(QColor("#2E6B2E"), 1))
            for i in range(min(left, 4)):                                             # 수박 조각
                x = b.left() + 8 + i * 15
                tri = QPainterPath(QPointF(x, 222))
                tri.lineTo(x + 14, 222)
                tri.lineTo(x + 7, 206)
                tri.closeSubpath()
                p.setBrush(QColor("#E8433F"))
                p.drawPath(tri)
                p.setBrush(QColor("#3E8E3E"))
                p.drawRect(QRectF(x, 221, 14, 3))
        else:
            p.setPen(QPen(QColor("#8A6532"), 1))
            p.setBrush(QColor("#C49A5A"))
            p.drawEllipse(QRectF(b.left() + 2, 218, 60, 12))                          # 바구니
            spots = [(18, 216), (32, 214), (46, 216), (25, 207), (39, 207)][:left]
            for dx, y in spots:
                p.setPen(QPen(QColor("#C9661A"), 1))
                p.setBrush(QColor("#F28C28"))
                p.drawEllipse(QPointF(b.left() + dx, y), 7, 6.5)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 110))
                p.drawEllipse(QPointF(b.left() + dx - 2, y - 2), 2, 1.6)
            p.setBrush(QColor("#F5A25A"))                                              # 까 놓은 껍질
            for i in range(min(self.eaten, 4)):
                p.drawEllipse(QPointF(214 + i * 9, 231), 4, 2.2)
        for i, cx in enumerate((206, 394)):                                            # 상 양 끝 찻잔 + 김
            p.setPen(QPen(QColor("#8C7A5A"), 1))
            p.setBrush(QColor("#EDE6D2"))
            p.drawRoundedRect(QRectF(cx - 7, 213, 14, 12), 3, 3)
            p.setBrush(QColor("#C9A040") if summer else QColor("#9BB55A"))
            p.drawEllipse(QRectF(cx - 6, 211, 12, 4))
            if not summer:
                p.setPen(QPen(QColor(255, 255, 255, 140), 1.3))
                path = QPainterPath(QPointF(cx, 208))
                ph = self.t * 2 + i
                for k in range(1, 5):
                    path.lineTo(cx + math.sin(ph + k) * 2.5, 208 - k * 4)
                p.drawPath(path)

    def _friend(self, p: QPainter, key: str, i: int) -> None:
        x, y, facing, _layer, _pose = SLOTS[i]
        now = time.monotonic()
        happy = now < self.happy_until.get(key, 0.0)
        kind = "happy" if happy else ("sleep" if self.asleep(key) else "sit")
        t = (self.t + i * 1.7) if not happy else 1.0 - (self.happy_until[key] - now)
        draw_friend(p, key, self.game.state.skins.get(key), kind, t, x, y, K, facing)
        h = DISPLAY_H * K
        self.hits[key] = QRectF(x - 26 * K, y - h * (0.7 if kind == "sleep" else 0.92), 52 * K, h * 0.9)
        if kind == "sleep":
            _zzz(p, x + 16, y - h * 0.6, self.t + i)

    def _night(self, p: QPainter) -> None:
        p.save()
        dark = QPainterPath()
        dark.addRect(QRectF(0, 0, W, ROOM_H))
        hole = QPainterPath()
        hole.addEllipse(WIN_C, WIN_R, WIN_R)
        p.fillPath(dark.subtracted(hole), QColor(18, 22, 60, 92))
        glow = QRadialGradient(QPointF(W / 2, 150), 300)
        glow.setColorAt(0, QColor(255, 196, 110, 70))
        glow.setColorAt(1, QColor(255, 196, 110, 0))
        p.fillRect(QRectF(0, 0, W, ROOM_H), glow)
        p.restore()

    def _empty_note(self, p: QPainter) -> None:
        r = QRectF(190, 120, 220, 54)
        p.setPen(QPen(QColor(200, 16, 46, 90), 1.2))
        p.setBrush(QColor(255, 255, 255, 220))
        p.drawRoundedRect(r, 12, 12)
        f = QFont("Malgun Gothic", 10)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#5A464B"))
        p.drawText(r, Qt.AlignCenter, "다들 밖에서 놀고 있어요\n조금 있다 다시 와 볼까요?")

    def _bubble(self, p: QPainter, x: float, y: float, text: str, taken: list[QRectF]) -> QRectF:
        """말풍선 (먼저 뜬 말풍선과 겹치면 그 위로)."""
        f = QFont("Malgun Gothic", 10)
        f.setBold(True)
        fm = QFontMetricsF(f)
        w, h = fm.horizontalAdvance(text) + 18, fm.height() + 10
        r = QRectF(min(max(x - w / 2, 8), W - w - 8), y - h - 14, w, h)
        while any(r.intersects(o) for o in taken) and r.top() > 24:
            r.translate(0, -(h + 4))
        path = QPainterPath()
        path.addRoundedRect(r, 9, 9)
        tail = QPainterPath(QPointF(x - 5, r.bottom() - 1))
        tail.lineTo(x + 5, r.bottom() - 1)
        tail.lineTo(x, r.bottom() + 8)
        tail.closeSubpath()
        path = path.united(tail)
        p.setPen(QPen(QColor(200, 16, 46, 140), 1.2))
        p.setBrush(QColor(255, 255, 255, 245))
        p.drawPath(path)
        p.setFont(f)
        p.setPen(QColor("#2B1D21"))
        p.drawText(r, Qt.AlignCenter, text)
        return r

    def _footer(self, p: QPainter) -> None:
        s = self.game.state
        r = QRectF(0, ROOM_H, W, H - ROOM_H)
        p.fillRect(r, QColor(255, 247, 248))
        p.fillRect(QRectF(0, ROOM_H, W, 2), QColor("#C8102E"))
        f = QFont("Malgun Gothic", 9)
        p.setFont(f)
        p.setPen(QColor("#5A464B"))
        parts = [f"🏠 신사 안  ·  쉬는 친구 {len(self.seats)}명"]
        names = {e["char"]: e for e in s.expeditions}
        if names:
            now = time.time()
            parts.append("원정 중: " + ", ".join(
                f"{CHARACTERS[k].name.split()[-1]}({_left(expedition.left(e, now))})" for k, e in names.items()
                if k in CHARACTERS))
        if self.invited:
            parts.append("문을 닫으면 " + "·".join(CHARACTERS[k].name.split()[-1] for k in self.invited if k in CHARACTERS)
                         + " 다시 밖으로")
        p.drawText(r.adjusted(14, 0, -14, 0), Qt.AlignLeft | Qt.AlignVCenter, "   ·   ".join(parts))
        p.setPen(QColor("#8C7479"))
        hint = "친구·바구니를 눌러 보세요"
        if QFontMetricsF(f).horizontalAdvance("   ·   ".join(parts) + hint) < W - 60:
            p.drawText(r.adjusted(14, 0, -14, 0), Qt.AlignRight | Qt.AlignVCenter, hint)

    def _close_button(self, p: QPainter) -> None:
        r = self.close_rect
        p.setPen(QPen(QColor(255, 255, 255, 220), 1.2))
        p.setBrush(QColor(200, 16, 46, 220))
        p.drawEllipse(r)
        p.setPen(QPen(QColor("#FFFFFF"), 2.2, Qt.SolidLine, Qt.RoundCap))
        c = r.center()
        p.drawLine(QPointF(c.x() - 5, c.y() - 5), QPointF(c.x() + 5, c.y() + 5))
        p.drawLine(QPointF(c.x() + 5, c.y() - 5), QPointF(c.x() - 5, c.y() + 5))


def _left(sec: float) -> str:
    m = int(sec // 60)
    return f"{m // 60}시간 {m % 60}분" if m >= 60 else f"{max(1, m)}분"
