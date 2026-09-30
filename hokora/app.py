# -*- coding: utf-8 -*-
"""Hokora 본체: 캐릭터·신사 창을 띄우고 시간·새전·저장을 관리한다."""
from __future__ import annotations

import getpass
import logging
import os
import random
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QObject, QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QAction, QCursor, QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import __version__, winutil
from .bubble import say
from .decor import DecorWindow
from .events import Events
from .omikuji import FortuneSlip, can_draw
from .omikuji import draw as draw_omikuji
from .panel import ShrinePanel
from .pet import CURSOR, PetWindow
from .prayer import WISHES, income_multiplier, pat_multiplier
from .prayer import buy as buy_wish
from .progress import UNLOCKS, newly_unlocked
from .render import CHARACTERS, Pose, draw_character
from .shrine import ShrineWindow
from .state import APP_NAME, DECOR, LOG_DIR, PAT_REWARD, SaveStore

log = logging.getLogger("Hokora")
ENTRY_SCRIPT = Path(sys.argv[0]).resolve()
INSTANCE_SERVER = f"{APP_NAME}-{getpass.getuser()}"
FPS_BUSY = 30            # 걷기·뛰기·던지기·잡기 — 부드럽게
FPS_CALM = 15            # 모두 가만히 있거나 앉아 있을 때 — CPU 를 아끼려고
PLATFORM_SLOW = 400      # 창 발판을 다시 읽는 간격(ms)
PLATFORM_FAST = 100      # 캐릭터가 창 위에 있을 때 (창을 끌면 바로 따라가게)
JUMP_UP_MAX = 700        # 이보다 높은 창으로는 점프하지 않음 (px) — 작업표시줄에서 화면 중간쯤 창까지
NAP_AFTER = float(os.environ.get("HOKORA_NAP_AFTER", 600))   # 이만큼(초) 자리를 비우면 낮잠
GREETINGS = ["어서 와요!", "잘 다녀왔어요?", "기다렸어요~", "zZ… 앗, 왔다!"]
JUMP_REACH = 600         # 옆으로 이보다 먼 창으로는 점프하지 않음 (px)
INCOME_EVERY = 30        # 새전이 들어오는 간격(초)
SAVE_EVERY = 60

MENU_STYLE = """
QMenu { background: #FFFFFF; border: 1px solid rgba(200,16,46,70); padding: 4px; }
QMenu::item { padding: 6px 22px 6px 26px; color: #2B1D21; border-radius: 4px; }
QMenu::item:selected { background: #FBE3E7; color: #9E1027; }
QMenu::item:disabled { color: #9E1027; font-weight: 700; }
QMenu::separator { height: 1px; background: rgba(200,16,46,40); margin: 4px 8px; }
QMenu::indicator { left: 6px; width: 14px; height: 14px; }
"""


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if os.environ.get("HOKORA_DEBUG") == "1" else logging.INFO
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s.%(funcName)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    fh = RotatingFileHandler(LOG_DIR / "hokora.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if sys.stderr is not None:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        root.addHandler(sh)
    sys.excepthook = lambda t, v, tb: log.critical("처리되지 않은 예외", exc_info=(t, v, tb))


def app_icon() -> QIcon:
    """트레이·창 아이콘: 레이무 얼굴을 코드로 그린다."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        # 리본 끝(설계 y≈-6)부터 턱(y≈86)까지가 아이콘을 채우게: 92 단위 = size
        scale = size / 92
        draw_character(p, CHARACTERS["reimu"], Pose(kind="idle", t=0.3),
                       QRectF((size - 100 * scale) / 2, 6 * scale, 100 * scale, 120 * scale))
        p.end()
        icon.addPixmap(QPixmap.fromImage(img))
    return icon


class Game(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.store = SaveStore()
        self.state = self.store.load()
        self._update_bounds()
        self.pets: list[PetWindow] = []
        self.hidden_for_fullscreen = False
        prim = self.app.primaryScreen().availableGeometry()
        self.shrine = ShrineWindow(self, prim.x() + self.state.shrine_x * prim.width(),
                                   self.state.shrine_level)
        self.shrine.set_saisen(self.state.saisen)
        self.decors: dict[str, DecorWindow] = {
            k: DecorWindow(self, k, x) for k, x in self.state.decor_pos.items() if k in DECOR}
        self.events = Events(self)
        self._panel_tab = 0
        keys = list(CHARACTERS) if os.environ.get("HOKORA_ALL") == "1" else self.state.unlocked
        for key in keys:
            self._spawn(key)

        self.clock = QElapsedTimer()
        self.clock.start()
        self.tick_timer = QTimer(self, timeout=self._tick, interval=1000 // FPS_CALM)
        self.income_timer = QTimer(self, timeout=self._income, interval=INCOME_EVERY * 1000)
        self.save_timer = QTimer(self, timeout=self.save, interval=SAVE_EVERY * 1000)
        self.unlock_timer = QTimer(self, timeout=self.check_unlocks, interval=30_000)   # 시간 조건(사쿠야)
        self.panel: ShrinePanel | None = None
        self.napping = False
        self.nap_timer = QTimer(self, timeout=self._check_nap, interval=3000)
        self.watch_timer = QTimer(self, timeout=self._watch, interval=1500)
        # 창 위 발판: 캐릭터가 창 위에 있으면 자주(창을 끌면 따라가게), 아니면 가끔 새로 읽음
        self.window_platforms: list[winutil.Platform] = []
        self.cursor = QCursor.pos()
        self.cursor_vel = QPointF()
        self.cursor_speed = 0.0
        self.cursor_down = False
        self.platform_timer = QTimer(self, timeout=self._refresh_platforms, interval=PLATFORM_SLOW)

        for sc in app.screens():
            sc.availableGeometryChanged.connect(self._on_screen_changed)
        app.screenAdded.connect(self._on_screen_added)
        app.screenRemoved.connect(self._on_screen_changed)
        self.tray = self._make_tray()

    # ── 화면 ──
    def _update_bounds(self) -> None:
        """모니터마다 작업 영역을 읽어, 작업표시줄 윗변을 모니터별 바닥 발판으로 만든다.

        바닥 발판은 창 발판과 똑같이 다루고(hwnd 자리에 음수 번호), 옆 모니터로 걸어가다
        바닥 높이가 다르면 떨어지거나(낮을 때) 돌아서거나 점프한다(높을 때).
        배율이 다른 모니터는 Qt 좌표에 틈이 생기므로, 물리적으로 붙어 있으면 통로로 잇는다.
        """
        monitors = winutil.monitor_rects()
        self.areas: list[winutil.Area] = []
        for sc in self.app.screens():
            g, a, dpr = sc.geometry(), sc.availableGeometry(), sc.devicePixelRatio()
            size = (round(g.width() * dpr), round(g.height() * dpr))
            phys = (next((m for m in monitors if (m[0], m[1]) == (g.x(), g.y())
                          and (m[2] - m[0], m[3] - m[1]) == size), None)
                    or next((m for m in monitors if (m[2] - m[0], m[3] - m[1]) == size), None)
                    or (g.x(), g.y(), g.x() + size[0], g.y() + size[1]))
            self.areas.append(winutil.Area((g.x(), g.y(), g.x() + g.width(), g.y() + g.height()),
                                           (a.x(), a.y(), a.x() + a.width(), a.y() + a.height()), dpr, phys))
        self.left = float(min(a.avail[0] for a in self.areas))
        self.right = float(max(a.avail[2] for a in self.areas))
        self.top = float(min(a.avail[1] for a in self.areas))
        self.bottom = float(max(a.avail[3] for a in self.areas))
        prim = self.app.primaryScreen().availableGeometry()
        self.ground_y = float(prim.bottom() + 1)   # 주 모니터의 작업표시줄 윗변
        # 바닥 발판: 붙어 있고 높이가 같은 모니터끼리는 하나로
        merged: list[list[float]] = []
        for x1, x2, y in sorted((a.avail[0], a.avail[2], a.avail[3]) for a in self.areas):
            if merged and merged[-1][1] == x1 and merged[-1][2] == y:
                merged[-1][1] = x2
            else:
                merged.append([x1, x2, y])
        self.grounds = [winutil.Platform(-(i + 1), x1, x2, y, x1) for i, (x1, x2, y) in enumerate(merged)]
        # 모니터 사이 통로 (가장자리 x, 방향, 도착 x)
        self.portals: list[tuple[float, int, float]] = []
        for a in self.areas:
            for b in self.areas:
                side_by_side = a.phys[2] == b.phys[0] and a.phys[1] < b.phys[3] and b.phys[1] < a.phys[3]
                if a is not b and side_by_side and a.avail[2] != b.avail[0]:
                    self.portals += [(a.avail[2], 1, b.avail[0]), (b.avail[0], -1, a.avail[2])]
        log.info("모니터 %d개, 바닥 %s, 통로 %d개", len(self.areas),
                 [(g.x1, g.x2, g.y) for g in self.grounds], len(self.portals))

    def _on_screen_added(self, sc) -> None:
        sc.availableGeometryChanged.connect(self._on_screen_changed)
        self._on_screen_changed()

    def _on_screen_changed(self, *_):
        self._update_bounds()
        self.shrine.set_level(self.shrine.level)     # 신사를 새 바닥 위로
        for d in getattr(self, "decors", {}).values():
            d.pos_x = d._clamp(d.pos_x)
            d._place()
        log.info("화면 구성 변경")

    def ground_under(self, x: float) -> winutil.Platform:
        """x 에 있는 바닥 (모니터 사이 빈 곳이면 가장 가까운 바닥)."""
        inside = [g for g in self.grounds if g.x1 <= x < g.x2]
        if inside:
            return max(inside, key=lambda g: g.y)
        return min(self.grounds, key=lambda g: min(abs(x - g.x1), abs(x - g.x2)))

    def ground_at(self, x: float) -> float:
        return self.ground_under(x).y

    def _spawn(self, key: str) -> PetWindow:
        g = self.ground_under(self.shrine.pos_x)
        x = random.uniform(g.x1 + 80, g.x2 - 80)
        pet = PetWindow(CHARACTERS[key], self, x)
        self.pets.append(pet)
        return pet

    def windows(self):
        """뒤 → 앞 순서 (맨 위로 다시 올릴 때 이 순서대로라 캐릭터가 가장 앞)."""
        decors = list(self.decors.values()) if self.state.show_decor else []   # 숨긴 장식은 다시 띄우지 않음
        return [*decors, self.shrine, *self.pets]

    def later(self, seconds: float, fn) -> None:
        QTimer.singleShot(int(seconds * 1000), fn)

    def try_skill(self, pet: PetWindow) -> bool:
        return self.events.try_skill(pet)

    def start(self) -> None:
        for w in self.windows():
            w.show()
        self.tick_timer.start()
        self.income_timer.start()
        self.save_timer.start()
        self.unlock_timer.start()
        self.nap_timer.start()
        self.watch_timer.start()
        self.platform_timer.start()
        self._refresh_platforms()
        log.info("시작 — 캐릭터 %d, 신사 %s", len(self.pets), self.state.stage_name)

    # ── 시간 ──
    def _tick(self) -> None:
        dt = min(self.clock.restart() / 1000.0, 0.1)   # 잠자기·절전에서 깨어나도 순간이동 안 하게
        if self.hidden_for_fullscreen:
            return
        self._track_cursor(dt)
        self.state.runtime_sec += dt
        if not 5 <= time.localtime().tm_hour < 20:
            self.state.night_sec += dt
        for pet in self.pets:
            pet.step(dt)
        self.shrine.step(dt)
        self.events.tick()
        fps = FPS_BUSY if any(p.busy for p in self.pets) else FPS_CALM
        if self.tick_timer.interval() != 1000 // fps:
            self.tick_timer.setInterval(1000 // fps)

    def _income(self) -> None:
        s = self.state
        s.income_carry += s.income_per_min * income_multiplier(s) * INCOME_EVERY / 60
        gained = int(s.income_carry)
        if gained:
            s.income_carry -= gained
            s.add_saisen(gained)
            self.shrine.set_saisen(s.saisen)
            if not self.hidden_for_fullscreen:
                self.shrine.pop(f"+{gained}")
            self.check_unlocks()

    def _watch(self) -> None:
        """전체화면(게임·영상)이면 숨기고, 아니면 다시 맨 위로."""
        busy = winutil.fullscreen_app_running()
        if busy != self.hidden_for_fullscreen:
            self.hidden_for_fullscreen = busy
            for w in self.windows():
                w.setVisible(not busy)
            log.info("전체화면 %s → %s", "감지" if busy else "종료", "숨김" if busy else "다시 표시")
        if not busy:
            for w in self.windows():
                winutil.keep_topmost(int(w.winId()))

    # ── 창 위 발판 (PetWindow 가 부름) ──
    @property
    def climbing(self) -> bool:
        return self.state.climb

    @property
    def cursor_play(self) -> bool:
        return self.state.cursor_play

    def _track_cursor(self, dt: float) -> None:
        """커서 위치·속도 (살짝 부드럽게) — 올라타기·따라가기·흔들어 떨어뜨리기에 씀."""
        c = QPointF(QCursor.pos())
        if dt > 0:
            v = (c - self.cursor) / dt
            self.cursor_vel = self.cursor_vel * 0.5 + v * 0.5
            self.cursor_speed = (self.cursor_vel.x() ** 2 + self.cursor_vel.y() ** 2) ** 0.5
        self.cursor = c
        self.cursor_down = winutil.left_button_down()

    def cursor_taken(self, pet: PetWindow) -> bool:
        return any(p is not pet and (p.on == CURSOR or p._to_cursor) for p in self.pets)

    def set_cursor_play(self, on: bool) -> None:
        self.state.cursor_play = on
        if not on:
            for p in self.pets:
                p._to_cursor = p._follow = False
        log.info("커서 놀이: %s", "켬" if on else "끔")

    @property
    def platforms(self) -> list[winutil.Platform]:
        """올라설 수 있는 모든 곳: 모니터별 작업표시줄 바닥 + 창 윗변."""
        return self.grounds + self.window_platforms

    def _refresh_platforms(self) -> None:
        if not self.state.climb or self.hidden_for_fullscreen:
            self.window_platforms = []
        else:
            self.window_platforms = winutil.window_platforms(self.areas)
        fast = any(p.on is not None and p.on > 0 for p in self.pets)
        self.platform_timer.setInterval(PLATFORM_FAST if fast else PLATFORM_SLOW)

    def has_surface_below(self, x: float, y: float) -> bool:
        return any(p.x1 <= x <= p.x2 and p.y > y + 1 for p in self.platforms)

    def portal(self, x: float, direction: int) -> float | None:
        """모니터 사이 틈 앞이면 건너편 x."""
        for edge, d, to in self.portals:
            if d == direction and abs(x - edge) < 24:
                return to + d * 14
        return None

    def find_landing(self, x: float, y0: float, y1: float) -> tuple[float, int] | None:
        """y0 → y1 로 내려오는 동안 처음 닿는 곳 (창 윗변 또는 작업표시줄)."""
        best: tuple[float, int] | None = None
        for p in self.platforms:
            if p.x1 <= x <= p.x2 and y0 <= p.y <= y1 and (best is None or p.y < best[0]):
                best = (p.y, p.hwnd)
        return best

    def platform(self, hwnd: int, x: float, win_left: float):
        """그 창 윗변 중 캐릭터가 서 있는 구간. 창이 옮겨졌으면 옮겨진 만큼 감안해서 찾는다.
        커서(CURSOR)는 커서 끝의 아주 좁은 발판 — win_left 가 커서 x 라서 커서를 따라 움직인다."""
        if hwnd == CURSOR:
            if not self.state.cursor_play:
                return None
            c = self.cursor
            return winutil.Platform(CURSOR, c.x() - 3, c.x() + 3, c.y(), c.x())
        for p in self.platforms:
            if p.hwnd == hwnd:
                moved_x = x + (p.win_left - win_left)
                if p.x1 - 2 <= moved_x <= p.x2 + 2:
                    return p
        return None

    def jump_target(self, pet: PetWindow) -> tuple[float, float] | None:
        """점프해서 갈 만한 곳: 닿을 만한 다른 창 윗변이나 (높이가 다른) 작업표시줄."""
        targets: list[tuple[float, float]] = []
        for p in self.platforms:
            if p.hwnd == pet.on or p.x2 - p.x1 < 80:
                continue
            up = pet.pos_y - p.y
            lo, hi = max(p.x1 + 25, pet.pos_x - JUMP_REACH), min(p.x2 - 25, pet.pos_x + JUMP_REACH)
            if 30 < abs(up) and -700 <= up <= JUMP_UP_MAX and lo < hi:
                targets.append((random.uniform(lo, hi), p.y))
        return random.choice(targets) if targets else None

    def set_climb(self, on: bool) -> None:
        self.state.climb = on
        self._refresh_platforms()      # 끄면 발판이 사라져 창 위의 캐릭터들이 내려옴
        log.info("창 위에도 올라가기: %s", "켬" if on else "끔")

    # ── 상호작용 (PetWindow / ShrineWindow 가 부름) ──
    def on_pat(self, pet: PetWindow) -> None:
        if self.events.is_fleeing(pet):          # 새전 들고 도망가는 마리사를 붙잡음
            self.events.catch()
            return
        if pet.pat():
            reward = PAT_REWARD * pat_multiplier(self.state)
            self.state.pats += 1
            self.state.add_saisen(reward)
            self.shrine.set_saisen(self.state.saisen)
            self.shrine.pop(f"+{reward}")
            self.check_unlocks()

    def on_shrine_moved(self, x: float) -> None:
        prim = self.app.primaryScreen().availableGeometry()   # 주 모니터 기준 비율 (다른 모니터면 0~1 밖)
        self.state.shrine_x = (x - prim.x()) / max(1, prim.width())

    def on_shrine_clicked(self, global_pos: QPoint = None) -> None:
        self.open_panel()

    # ── 신사 키우기 / 해금 ──
    def open_panel(self) -> None:
        if self.panel is not None:
            self.panel.close()
        self.panel = ShrinePanel(self.state, self.upgrade, self.omikuji, self.on_decor, self.pray, self._panel_tab)
        self.panel.tabs.currentChanged.connect(lambda i: setattr(self, "_panel_tab", i))
        self.panel.destroyed.connect(lambda *_: setattr(self, "panel", None))
        top = self.shrine.y() + 20
        self.panel.show_above(self.shrine.pos_x, top, self.left, self.right)

    def _say_at_shrine(self, text: str) -> None:
        say(text, self.shrine.pos_x, self.shrine.y() + 26)

    def _check_nap(self) -> None:
        """자리를 비우면 다들 그 자리에서 낮잠, 돌아오면 깨어나 반긴다."""
        idle = winutil.idle_seconds()
        if not self.napping and idle >= NAP_AFTER:
            self.napping = True
            self.events.cancel_thief()
            log.info("자리 비움 %.0f초 → 낮잠", idle)
        elif self.napping and idle < 3:
            self.napping = False
            log.info("돌아옴 → 깨어남")
            for pet in self.pets:
                pet.wake()
            awake = [p for p in self.pets if p.isVisible()]
            if awake and not self.hidden_for_fullscreen:
                pet = random.choice(awake)
                say(random.choice(GREETINGS), pet.pos_x, pet.pos_y - 72)
            return
        if self.napping:                     # 늦게 착지한 캐릭터도 잠들게
            for pet in self.pets:
                pet.nap()

    # ── 참배 ──
    def pray(self, key: str) -> None:
        if not buy_wish(self.state, key, can_draw(self.state)):
            return
        w = WISHES[key]
        log.info("참배: %s", key)
        self.shrine.set_saisen(self.state.saisen)
        if key == "snack":
            self.gather()
            self.later(1.6, lambda: [p.react(True) for p in self.pets])
            self._say_at_shrine("간식 시간이다~!")
        elif key == "omikuji":
            self._say_at_shrine("소원을 빌었다. 오미쿠지를 한 번 더 뽑을 수 있어요!")
        else:
            self._say_at_shrine(f"{w.icon} {w.name}!  {w.desc}")
        self.save()

    # ── 신사 꾸미기 ──
    def set_show_decor(self, on: bool) -> None:
        """장식을 보이거나 숨김. 숨겨도 놓아 둔 장식의 새전 보너스는 그대로."""
        self.state.show_decor = on
        for win in self.decors.values():
            win.setVisible(on and not self.hidden_for_fullscreen)
        log.info("장식 %s", "보임" if on else "숨김")
        self.save()

    def on_decor(self, key: str, action: str) -> None:
        s = self.state
        if action in ("show", "hide"):
            self.set_show_decor(action == "show")
            return
        if action == "buy":
            if not s.buy_decor(key):
                return
            self.shrine.pop(f"-{DECOR[key][1]}")
            log.info("장식 구입: %s", key)
            action = "place"
        if action == "place" and key in s.decor_owned and key not in self.decors:
            win = DecorWindow(self, key, self._decor_spot(key))
            self.decors[key] = win
            s.decor_pos[key] = win.pos_x
            if not self.hidden_for_fullscreen and s.show_decor:
                win.show()
            name = DECOR[key][0]
            hidden = "" if s.show_decor else "  (장식 숨김 중)"
            self._say_at_shrine(f"{name}{_eul(name)} 놓았다!  분당 새전 +{DECOR[key][2]}{hidden}")
        elif action == "remove" and key in self.decors:
            self.decors.pop(key).close()
            s.decor_pos.pop(key, None)
        self.shrine.set_saisen(s.saisen)
        self.save()

    def _decor_spot(self, key: str) -> float:
        """신사 양옆으로 번갈아 가며, 신사·다른 장식과 겹치지 않는 가장 가까운 빈자리."""
        w = DecorWindow.width_for(key)
        g = self.ground_under(self.shrine.pos_x)
        taken = [(self.shrine.pos_x - self.shrine.width() / 2, self.shrine.pos_x + self.shrine.width() / 2)]
        taken += [(d.pos_x - d.width() / 2, d.pos_x + d.width() / 2) for d in self.decors.values()]
        gap = 8
        for step in range(0, 3000, 10):
            for side in (1, -1):
                x = self.shrine.pos_x + side * (self.shrine.width() / 2 + gap + w / 2 + step)
                lo, hi = x - w / 2 - gap, x + w / 2 + gap
                if g.x1 <= lo and hi <= g.x2 and all(hi <= a or lo >= b for a, b in taken):
                    return x
        return self.shrine.pos_x

    def on_decor_moved(self, key: str, x: float) -> None:
        self.state.decor_pos[key] = x

    def omikuji(self) -> None:
        """하루 한 번 운세. 새전을 받고, 캐릭터들이 기뻐하거나 깜짝 놀란다."""
        if not can_draw(self.state):
            return
        result = draw_omikuji(self.state)
        log.info("오미쿠지: %s (+%d)", result.fortune.rank, result.reward)
        self.shrine.set_saisen(self.state.saisen)
        self.shrine.pop(f"+{result.reward}")
        for pet in self.pets:
            pet.react(result.fortune.good)
        slip = FortuneSlip(result)
        slip.show_above(self.shrine.pos_x, self.shrine.y() + 20)
        self.save()
        self.check_unlocks()

    def upgrade(self) -> None:
        if not self.state.upgrade_shrine():
            return
        s = self.state
        self.shrine.set_level(s.shrine_level)
        self.shrine.set_saisen(s.saisen)
        self.on_shrine_moved(self.shrine.pos_x)
        log.info("신사 업그레이드 → %s", s.stage_name)
        self._say_at_shrine(f"{s.stage_name}로 커졌다!  분당 새전 {s.income_per_min}")
        self.save()
        self.check_unlocks()

    def check_unlocks(self) -> None:
        """조건을 채운 캐릭터가 있으면 하늘에서 신사 옆으로 떨어뜨리며 등장."""
        for key in newly_unlocked(self.state):
            self.state.unlocked.append(key)
            log.info("해금: %s", key)
            if all(p.ch.key != key for p in self.pets):
                pet = self._spawn(key)
                g = self.ground_under(self.shrine.pos_x)
                pet.pos_x = min(max(self.shrine.pos_x + random.uniform(-160, 160), g.x1 + 40), g.x2 - 40)
                pet.pos_y, pet.vx, pet.vy, pet.state, pet.on = max(self.top + 80, g.y - 600), 0.0, 0.0, "fall", None
                pet._place()
                if not self.hidden_for_fullscreen:
                    pet.show()
            if not self.hidden_for_fullscreen:
                self._say_at_shrine(UNLOCKS[key].arrive_line)
            self.save()

    def on_context_menu(self, global_pos: QPoint) -> None:
        menu = QMenu()
        self._fill_menu(menu)
        menu.exec(global_pos)

    def _fill_menu(self, menu: QMenu) -> None:
        s = self.state
        menu.setStyleSheet(MENU_STYLE)
        info = menu.addAction(f"새전 {s.saisen:,}   ·   {s.stage_name} (분당 {s.income_per_min})")
        info.setEnabled(False)
        menu.addSeparator()
        menu.addAction("신사 관리 · 도감", self.open_panel)
        if can_draw(s):
            menu.addAction("오늘의 오미쿠지 뽑기", self.omikuji)
        menu.addAction("모두 불러오기", self.gather)
        if s.decor_pos:
            view = QAction("장식 보이기  (꺼도 효과는 그대로)", menu, checkable=True)
            view.setChecked(s.show_decor)
            view.toggled.connect(self.set_show_decor)
            menu.addAction(view)
        cur = QAction("마우스 커서에도 올라타기", menu, checkable=True)
        cur.setChecked(s.cursor_play)
        cur.toggled.connect(self.set_cursor_play)
        menu.addAction(cur)
        climb = QAction("창 위에도 올라가기", menu, checkable=True)
        climb.setChecked(s.climb)
        climb.toggled.connect(self.set_climb)
        menu.addAction(climb)
        if winutil.IS_WIN:
            a = QAction("Windows 시작 시 자동 실행", menu, checkable=True)
            a.setChecked(winutil.get_autostart() is not None)
            a.toggled.connect(lambda on: winutil.set_autostart(on, ENTRY_SCRIPT))
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction("종료", self.quit)

    def gather(self) -> None:
        """화면 밖이나 구석에 간 캐릭터를 신사 옆으로."""
        self.events.cancel_thief()
        g = self.ground_under(self.shrine.pos_x)
        for pet in self.pets:
            pet.pos_x = min(max(self.shrine.pos_x + random.uniform(-120, 120), g.x1 + 40), g.x2 - 40)
            pet.pos_y, pet.vx, pet.vy, pet.state, pet.on = g.y - 200, 0.0, 0.0, "fall", None
            pet.show()

    def _make_tray(self) -> QSystemTrayIcon | None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QSystemTrayIcon(self.app.windowIcon(), self)
        tray.setToolTip("Hokora — 나만의 신사")
        tray.activated.connect(self._on_tray_activated)
        self._tray_menu = QMenu()
        self._tray_menu.aboutToShow.connect(lambda: (self._tray_menu.clear(), self._fill_menu(self._tray_menu)))
        tray.setContextMenu(self._tray_menu)  # 열 때마다 최신 새전·설정으로 다시 채움
        tray.show()
        return tray

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:  # 왼쪽 클릭: 캐릭터 불러오기
            self.gather()

    # ── 저장 / 종료 ──
    def save(self) -> None:
        if self.store.save(self.state):
            log.debug("저장: 새전 %d", self.state.saisen)

    def quit(self) -> None:
        self.save()
        self.app.quit()


def _eul(word: str) -> str:
    """받침이 있으면 "을", 없으면 "를"."""
    code = ord(word[-1]) - 0xAC00
    return "을" if 0 <= code < 11172 and code % 28 else "를"


def _notify_running_instance() -> bool:
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_SERVER)
    if not sock.waitForConnected(500):
        return False
    sock.write(b"gather\n")
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


def _start_instance_server(game: Game) -> None:
    server = QLocalServer(game)
    QLocalServer.removeServer(INSTANCE_SERVER)
    if not server.listen(INSTANCE_SERVER):
        log.warning("중복 실행 감지 서버 시작 실패: %s", server.errorString())

    def on_connection():
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.disconnected.connect(conn.deleteLater)
            log.info("다시 실행됨 → 캐릭터 불러오기")
            game.gather()

    server.newConnection.connect(on_connection)


def main() -> int:
    setup_logging()
    winutil.set_app_user_model_id(f"YGH.{APP_NAME}")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setFont(QFont("Malgun Gothic", 9))
    if _notify_running_instance():
        log.info("이미 실행 중 — 기존 캐릭터를 불러오고 종료")
        return 0
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())
    log.info("Hokora v%s 시작", __version__)

    # exe 를 옮겼으면 자동 실행 경로 갱신
    registered = winutil.get_autostart()
    if registered is not None and registered != winutil.autostart_command(ENTRY_SCRIPT):
        winutil.set_autostart(True, ENTRY_SCRIPT)

    game = Game(app)
    _start_instance_server(game)
    app.aboutToQuit.connect(game.save)
    app.commitDataRequest.connect(lambda _m: game.save())
    game.start()
    if game.store.problem:
        QMessageBox.warning(None, "Hokora 저장 파일", game.store.problem)
    rc = app.exec()
    log.info("종료 코드 %d", rc)
    return rc
