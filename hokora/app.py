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

from PySide6.QtCore import QElapsedTimer, QObject, QPoint, QPointF, QProcess, QRectF, Qt, QTimer
from PySide6.QtGui import QCursor, QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import __version__, winutil
from . import affection as aff
from . import achievements, daily, expedition, festival, fishing, omamori, photo, season, torii, tutorial, wardrobe, weather
from . import card, cucumber, goods, ink, lifesense, moon, offering, room, sound, ufo
from .settings import SettingsWindow
from .diary import DiaryCard
from .guests import fade as fade_window
from .spellcard import MIN_GAP as CUTIN_GAP
from .spellcard import CutIn
from .bubble import _alive as bubble_alive
from .bubble import say
from .daily import StampCard
from .decor import DecorWindow
from .diary import MIN_AWAY, PetalBurst, away_card, offline_income
from .events import Events
from .guests import BELL_PRICE, BELL_TEXT, Flash, Visits
from .omikuji import FortuneSlip, can_draw
from .omikuji import draw as draw_omikuji
from .panel import STYLE as PANEL_STYLE
from .panel import ShrinePanel
from .photo import PhotoCard
from .pet import CURSOR, PetWindow
from .prayer import WISHES, income_multiplier, pat_multiplier
from .prayer import buy as buy_wish
from .progress import UNLOCKS, newly_unlocked
from .render import CHARACTERS, Pose, draw_character
from .shrine import ShrineWindow
from .torii import ToriiRow
from .state import APP_NAME, DECOR, LOG_DIR, PAT_REWARD, SAISEN_BOX, SHRINE_SKINS, SaveStore

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
        # 꺼져 있던 동안: 새전함에 쌓인 새전 (일기는 시작한 뒤에 보여줌)
        now = time.time()
        self._away = (now - self.state.last_seen) if self.state.last_seen else 0.0
        self._away_earned = offline_income(self.state, self._away) if self._away > 60 else 0
        if self._away_earned:
            self.state.add_saisen(self._away_earned)
            self.state.dream_pill = False            # 꿈나라 약은 한 번 쓰면 끝
            log.info("꺼져 있던 %.0f분 동안 새전 +%d", self._away / 60, self._away_earned)
        self._nap_start = 0.0
        self._nap_total = 0
        self._cards: list = []
        self._card_queue: list = []              # 일기·출석·신문·사진 카드는 하나씩 차례로
        self.fx = season.SeasonFx()
        self.wfx = weather.WeatherFx()
        self.ffx = festival.FestivalFx()
        self.tip: tutorial.Tip | None = None
        self._out_since: dict[str, float] = {}         # 붐빔 조절: 언제부터 나와 있었나 / 쉬었나
        self._bench_since: dict[str, float] = {}
        self._crowd_n = 0
        self.ink: list[ink.Stroke] = []                # 요술 붓으로 그린 길
        self._ink_next = ink.INK0
        self._ink_canvas: ink.InkCanvas | None = None
        self._room: room.RoomWindow | None = None      # 신사 안 창
        self._room_in: set[str] = set()                # 신사 안을 볼 때 잠깐 들어간 친구
        self.ufo: ufo.Ufo | None = None                # 누에의 UFO
        self._abducted: dict[str, float] = {}          # UFO 에 끌려간 친구 → 돌아오는 시각 (time.time)
        self._started = time.monotonic()
        tutorial.decide(self.state)
        from datetime import datetime as _dt
        self._chimed = (_dt.now().date(), _dt.now().hour)   # 켜자마자 울리지 않게
        self._cpu = lifesense.CpuMeter()
        self._cpu_hot = 0
        self._said: dict[str, float] = {}                   # 반응별 마지막으로 말한 시각
        self._batt_low = False
        self._pc_n = 0
        self.life_timer = QTimer(self, timeout=self._life_tick, interval=20_000)
        weather.set_magic(self.state.weather_magic, self.state.weather_magic_until)
        self._cutin_at = -1e9
        self._night: bool | None = None
        self._update_bounds()
        self.pets: list[PetWindow] = []
        self.guests: list[PetWindow] = []        # 지금 와 있는 손님 (guests.py 가 넣고 뺌)
        self.hidden_for_fullscreen = False
        prim = self.app.primaryScreen().availableGeometry()
        self.shrine = ShrineWindow(self, prim.x() + self.state.shrine_x * prim.width(),
                                   self.state.look_stage)
        if self.state.shrine_skin in SHRINE_SKINS:
            self.shrine.set_skin(self.state.shrine_skin)
        self.torii_row = ToriiRow(self)
        self.offer_tray = offering.OfferTray(self)     # 신사 앞 공물상
        self.shrine.set_saisen(self.state.saisen)
        self.decors: dict[str, DecorWindow] = {
            k: DecorWindow(self, k, x) for k, x in self.state.decor_pos.items() if k in DECOR}
        self.events = Events(self)
        self.visits = Visits(self)
        self._panel_tab = 0
        elig = self._eligible()                    # 쉬는 친구·원정 간 친구는 빼고, 붐빔 조절만큼만
        for key in elig[:self.state.max_out or len(elig)]:
            self._spawn(key)
        for key in elig[self.state.max_out or len(elig):]:
            self._bench_since[key] = time.monotonic()

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
        self.day_timer = QTimer(self, timeout=self._every_half_minute, interval=30_000)   # 날짜·계절·밤, 부탁 진행
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
        self.last_bell = ""
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
        pet.skin = self.state.skins.get(key)
        pet.fx_kind = self.state.effects.get(key)
        self.pets.append(pet)
        return pet

    def windows(self):
        """뒤 → 앞 순서 (맨 위로 다시 올릴 때 이 순서대로라 캐릭터가 가장 앞)."""
        hidden = self.visits.hidden_decor                 # 서니가 숨긴 장식도
        decors = [w for k, w in self.decors.items() if k != hidden] if self.state.show_decor else []
        fx = [self.fx] if self.fx.kind and self.state.season_fx else []   # 흩날림·날씨는 맨 뒤
        fx += [self.wfx] if self.wfx.kind and self.state.season_fx else []
        fx += [self.ffx] if festival.active(self.state) else []
        row = [self.torii_row] if self.state.torii and self.state.show_torii else []
        inks = [st.win for st in self.ink]
        offer = [self.offer_tray] if self.state.offering else []
        sky = self.ufo.windows() if self.ufo is not None else []
        return [*fx, *row, *decors, *inks, self.shrine, *offer, *self.pets, *self.guests, *sky]

    @property
    def scale(self) -> float:
        return self.state.size_scale

    def keep(self, w) -> None:
        """잠깐 떠 있는 창(일기·신문·효과)을 닫힐 때까지 붙잡아 둠."""
        self._cards.append(w)
        w.destroyed.connect(lambda *_: self._cards.remove(w) if w in self._cards else None)

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
        self.day_timer.start()
        self.life_timer.start()
        self._refresh_platforms()
        self._refresh_season()
        self._sync_torii()
        self._sync_offering()
        if os.environ.get("HOKORA_UFO") == "1":            # 시험용: 켜자마자 UFO
            QTimer.singleShot(6000, self.summon_ufo)
        QTimer.singleShot(3500, self._new_day)
        QTimer.singleShot(5000, self._check_expeditions)
        QTimer.singleShot(6500, self._check_achievements)
        QTimer.singleShot(4200, self._tutorial_show)
        self._refresh_festival()
        if self._away >= MIN_AWAY:
            QTimer.singleShot(2500, lambda: self._show_diary(self._away, time.time() - self._away,
                                                             self._away_earned, offline=True))
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
        everyone = [*self.pets, *self.guests]
        for pet in everyone:
            pet.step(dt)
        self.shrine.step(dt)
        if self.ink:
            self._ink_tick()
        if self.ufo is not None:
            self.ufo.step(dt)
            if self.ufo.done:
                self.ufo = None
        if self.tip is not None:
            self._tutorial_follow()
        if (self.fx.isVisible() or self.torii_row.isVisible() or self.wfx.isVisible() or self.ffx.isVisible()
                or self.offer_tray.isVisible()):
            g = self.ground_under(self.shrine.pos_x)
            if self.offer_tray.isVisible():
                self.offer_tray.follow(self.shrine.pos_x, g.y, self.shrine.width())
            if self.ffx.isVisible():
                self.ffx.follow(self.shrine.pos_x, g.y)
            if self.fx.isVisible():
                self.fx.follow(self.shrine.pos_x, g.y)
            if self.wfx.isVisible():
                self.wfx.follow(self.shrine.pos_x, g.y)
            if self.torii_row.isVisible():              # 도리이 줄은 신사 옆에 붙어 다님
                self.torii_row.place(self.shrine.x() + 10, self.shrine.x() + self.shrine.width() - 10, g.y, g.x1, g.x2)
        self.events.tick()
        self.visits.tick()
        fps = FPS_BUSY if any(p.busy for p in everyone) else FPS_CALM
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
        """전체화면(게임·영상)이면 숨기고, 아니면 다시 맨 위로.

        '전체화면에서도 돌아다니기'를 켜면 영상·브라우저 전체화면에선 그대로 두고,
        전용 전체화면 게임·발표 모드에서만 숨는다 (맨 위로 올리다 게임을 방해하지 않게).
        """
        busy = winutil.fullscreen_app_running(games_only=self.state.fullscreen_show)
        if self._ink_canvas is not None:      # 길 그리기 판이 화면을 덮고 있는 동안은 숨지 않음
            busy = False
        if busy != self.hidden_for_fullscreen:
            self.hidden_for_fullscreen = busy
            for w in self.windows():
                w.setVisible(not busy)
            if busy:
                for w in (self._ink_canvas, self._room):
                    if w is not None:
                        w.close()
                if self.ufo is not None:
                    self.ufo.cancel()
                    self.ufo = None
            log.info("전체화면 %s → %s", "감지" if busy else "종료", "숨김" if busy else "다시 표시")
        if not busy:
            self._restack()

    def _restack(self) -> None:
        """뒤 → 앞 순서로 다시 맨 위로. 신사 안 창·그리기 판은 그보다도 위."""
        for w in [*self.windows(), self._room, self._ink_canvas]:
            if w is not None:
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
        fast = any(p.on is not None and p.on > 0 for p in [*self.pets, *self.guests])
        self.platform_timer.setInterval(PLATFORM_FAST if fast else PLATFORM_SLOW)

    def has_surface_below(self, x: float, y: float) -> bool:
        return (any(p.x1 <= x <= p.x2 and p.y > y + 1 for p in self.platforms)
                or any(pc.x1 <= x <= pc.x2 and pc.y_at(x) > y + 1 for pc in self.ink_paths))

    # ── 요술 붓: 그은 선이 발판 (PetWindow 가 부름) ──
    @property
    def has_ink(self) -> bool:
        return bool(self.ink)

    @property
    def ink_paths(self) -> list[ink.InkPath]:
        return [pc for st in self.ink for pc in st.pieces]

    def ink_path(self, hwnd: int) -> ink.InkPath | None:
        for st in self.ink:
            for pc in st.pieces:
                if pc.id == hwnd:
                    return pc
        return None

    def ink_entry(self, on: int, x: float, y: float, d: int) -> tuple[int, float] | None:
        """걷는 발밑에서 시작하는(지나가는) 그린 길 — 앞쪽이 올라가거나 평평할 때만 (발판 아래로 파고들지 않게)."""
        ahead = x + d * 12
        for pc in self.ink_paths:
            if pc.id == on or not (pc.x1 - 3 <= x <= pc.x2 + 3 and pc.x1 <= ahead <= pc.x2):
                continue
            here = pc.y_at(x)
            if abs(here - y) <= 6 and pc.y_at(ahead) <= y + 2:
                return pc.id, here
        return None

    def continue_at(self, on: int, x: float, y: float) -> tuple[int, float, float] | None:
        """발판 끝 바로 너머 x 에서 거의 같은 높이로 이어지는 발판 (그린 길 ↔ 그린 길·창 윗변·작업표시줄)."""
        for pc in self.ink_paths:
            if pc.id != on and pc.x1 - 2 <= x <= pc.x2 + 2 and abs(pc.y_at(x) - y) <= 9:
                return pc.id, pc.y_at(x), 0.0
        if ink.is_ink(on):
            for p in self.platforms:
                if p.hwnd != on and p.hwnd != CURSOR and p.x1 <= x <= p.x2 and abs(p.y - y) <= 9:
                    return p.hwnd, p.y, p.win_left
        return None

    def on_slide(self, pet: PetWindow) -> None:
        self.state.slides += 1

    def start_drawing(self) -> None:
        if self._ink_canvas is not None:
            self._ink_canvas.raise_()
            return
        c = ink.InkCanvas(self.state.ink_color, self.add_stroke, self.clear_ink, self._drawing_done, PANEL_STYLE)
        self._ink_canvas = c
        self.keep(c)
        c.show()
        c.raise_()
        c.activateWindow()
        c.setFocus()
        log.info("길 그리기 시작")

    def _drawing_done(self, color: str) -> None:
        self._ink_canvas = None
        self.state.ink_color = color
        self.save()

    def add_stroke(self, pts: list[tuple[float, float]], color: str = "sumi") -> ink.Stroke | None:
        pts = ink.resample(pts)
        if len(pts) < 2 or ink.length(pts) < ink.MIN_LEN:
            return None
        st = ink.Stroke(pts, color, self._ink_next)
        self._ink_next -= max(1, len(st.pieces))
        self.ink.append(st)
        while len(self.ink) > ink.MAX_STROKES:
            self._remove_stroke(self.ink[0])
        self.state.ink_drawn += 1
        if not self.hidden_for_fullscreen:
            st.win.show()
            self._restack()
        log.info("그린 길: 점 %d개, 조각 %d개", len(pts), len(st.pieces))
        return st

    def _remove_stroke(self, st: ink.Stroke) -> None:
        if st in self.ink:
            self.ink.remove(st)
        st.win.close()
        st.win.deleteLater()

    def clear_ink(self) -> None:
        for st in list(self.ink):
            self._remove_stroke(st)

    def _ink_tick(self) -> None:
        now = time.monotonic()
        for st in list(self.ink):
            a = st.alpha(now)
            if a <= 0:
                self._remove_stroke(st)
            elif a < 1:
                st.win.setWindowOpacity(a)

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
        for pc in self.ink_paths:
            if pc.x1 <= x <= pc.x2:
                y = pc.y_at(x)
                if y0 <= y <= y1 and (best is None or y < best[0]):
                    best = (y, pc.id)
        return best

    def platform(self, hwnd: int, x: float, win_left: float):
        """그 창 윗변 중 캐릭터가 서 있는 구간. 창이 옮겨졌으면 옮겨진 만큼 감안해서 찾는다.
        커서(CURSOR)는 커서 끝의 아주 좁은 발판 — win_left 가 커서 x 라서 커서를 따라 움직인다."""
        if ink.is_ink(hwnd):                     # 그린 길: 서 있는 x 의 높이
            pc = self.ink_path(hwnd)
            if pc is None or not pc.x1 - 2 <= x <= pc.x2 + 2:
                return None
            return winutil.Platform(hwnd, pc.x1, pc.x2, pc.y_at(x), 0.0)
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
        if self.ink and random.random() < 0.7:          # 그린 길이 있으면 그쪽으로 자주
            cands = []
            for pc in self.ink_paths:
                lo, hi = max(pc.x1 + 8, pet.pos_x - JUMP_REACH), min(pc.x2 - 8, pet.pos_x + JUMP_REACH)
                if pc.id == pet.on or lo >= hi:
                    continue
                x = random.uniform(lo, hi)
                up = pet.pos_y - pc.y_at(x)
                if 20 < abs(up) and -700 <= up <= JUMP_UP_MAX:
                    cands.append((x, pc.y_at(x)))
            if cands:
                return random.choice(cands)
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
        if pet in self.guests:                     # 손님은 손님마다 반응이 다름 (요정은 붙잡힘)
            self.visits.on_click(pet)
            return
        if self.events.is_fleeing(pet):          # 새전 들고 도망가는 마리사를 붙잡음
            self.events.catch()
            return
        if pet.pat():
            self._tutorial_event("pat")
            reward = PAT_REWARD * pat_multiplier(self.state) * aff.pat_bonus(self.state, pet.ch.key)
            reward += int(omamori.bonus(self.state, "pat"))           # 복 부적
            now = time.monotonic()
            if now - getattr(pet, "_aff_at", 0.0) >= aff.PAT_GAIN_EVERY:   # 쓰다듬으면 조금씩 친해짐
                pet._aff_at = now
                self._add_affection(pet, 1)
            self.state.pats += 1
            self.state.add_saisen(reward)
            self.shrine.set_saisen(self.state.saisen)
            self.shrine.pop(f"+{reward}")
            daily.bump(self.state, "pat")
            self._daily_check()
            self.check_unlocks()

    def on_thrown(self, pet: PetWindow, speed: float) -> None:
        if speed > 400:                           # 살짝 내려놓은 건 빼고
            self._tutorial_event("throw")
            daily.bump(self.state, "throw")
            self._daily_check()

    def on_shrine_moved(self, x: float) -> None:
        prim = self.app.primaryScreen().availableGeometry()   # 주 모니터 기준 비율 (다른 모니터면 0~1 밖)
        self.state.shrine_x = (x - prim.x()) / max(1, prim.width())

    def on_shrine_clicked(self, global_pos: QPoint = None) -> None:
        self.open_panel()

    # ── 신사 키우기 / 해금 ──
    def open_panel(self) -> None:
        self._tutorial_event("panel")
        if self.panel is not None:
            self.panel.close()
        self.panel = ShrinePanel(self.state, self.upgrade, self.omikuji, self.on_decor, self.pray, self.upgrade_box,
                                 self._panel_tab, self.on_action)
        self.panel.tabs.currentChanged.connect(lambda i: setattr(self, "_panel_tab", i))
        panel = self.panel                        # 예전 창이 늦게 닫혀도 새 창을 잊지 않게
        panel.destroyed.connect(lambda *_: setattr(self, "panel", None) if self.panel is panel else None)
        top = self.shrine.y() + 20
        self.panel.show_above(self.shrine.pos_x, top, self.left, self.right)

    def _say_at_shrine(self, text: str) -> None:
        """신사 위 말풍선. 새 말이 뜨면 앞의 것은 닫음 (연달아 눌러도 겹치지 않게)."""
        if self.hidden_for_fullscreen:
            return
        old = getattr(self, "_shrine_bubble", None)
        if old is not None and old in bubble_alive:
            old.close()
        self._shrine_bubble = say(text, self.shrine.pos_x, self.shrine.y() + 26)

    # ── 오늘의 부탁·출석 ──
    def _every_half_minute(self) -> None:
        self._new_day()
        self._refresh_season()
        self._festival_tick()
        self._crowd_n += 1
        self._crowd_tick(rotate=self._crowd_n % 20 == 0)   # 10분마다 번갈아
        self._check_expeditions()
        self._check_achievements()
        self._daily_check()                        # 새전 모으기·함께 지내기는 시간이 지나며 채워짐
        self._ufo_returns()
        self._ufo_roll()

    def _new_day(self) -> None:
        """날짜가 바뀌면(켰을 때 포함) 오늘의 부탁을 새로 받고 출석 도장."""
        s = self.state
        fresh = daily.new_day(s)
        got = daily.stamp(s)
        if got is not None:
            day, reward = got
            self.shrine.set_saisen(s.saisen)
            self.shrine.pop(f"+{reward}")
            extra = "🎍 새해 복 많이 받으세요! 사흘 동안 새전 수입 2배" if season.is_new_year() else ""
            self.show_card(StampCard(s, day, reward, extra))
            log.info("출석 도장: 연속 %d일째 (+%d)", s.attend_streak, reward)
        if fresh or got is not None:
            self.save()

    def _daily_check(self) -> None:
        done, bonus = daily.check(self.state)
        if not done:
            return
        self.shrine.set_saisen(self.state.saisen)
        for i, task in enumerate(done):
            self.later(i * 1.8, lambda t=task: self._say_at_shrine(
                f"✅ 부탁 완료: {daily.text(t)}   새전 +{t['reward']:,}"))
            self.shrine.pop(f"+{task['reward']}")
            log.info("부탁 완료: %s", task["kind"])
        if bonus:
            def cheer():
                self._say_at_shrine(f"🎉 오늘의 부탁을 모두 들어줬다!  보너스 새전 +{bonus:,}")
                for p in self.pets:
                    p.react(True)
            self.later(len(done) * 1.8, cheer)
        self.save()

    # ── 계절·밤 ──
    def _refresh_season(self) -> None:
        night = season.is_night()
        if night != self._night:
            if night and self._night is not None and moon.is_full():     # 보름달 밤이 시작됨
                self.later(3.0, self._full_moon_night)
            self._night = night
            self.shrine.set_night(night)
            for d in self.decors.values():
                d.set_night(night)
            self._sync_torii()
        kind = season.fx_kind() if self.state.season_fx else ""
        self.fx.set_kind(kind)
        show = bool(kind) and not self.hidden_for_fullscreen
        if show != self.fx.isVisible():
            if show:
                self.fx.follow(self.shrine.pos_x, self.ground_under(self.shrine.pos_x).y)
            self.fx.setVisible(show)
        # 天候
        w = weather.current()
        wkind = w.key if self.state.season_fx and weather.WeatherFx.wants(w.key) else ""
        self.wfx.set_kind(wkind)
        show = bool(wkind) and not self.hidden_for_fullscreen
        if show != self.wfx.isVisible():
            if show:
                self.wfx.follow(self.shrine.pos_x, self.ground_under(self.shrine.pos_x).y)
            self.wfx.setVisible(show)
        sl = weather.slot()
        if sl != self.state.weather_slot:                   # 날씨가 바뀌면 알림
            self.state.weather_slot = sl
            self.later(6.0, lambda: self._say_at_shrine(f"{w.icon} 天候: {w.name}({w.kanji}) — {w.desc}"))
            log.info("날씨: %s", w.key)

    # ── 스펠카드 컷인 ──
    def cutin(self, pet: PetWindow) -> None:
        now = time.monotonic()
        if (not self.state.cutin or self.hidden_for_fullscreen or self.napping
                or now - self._cutin_at < CUTIN_GAP or pet not in self.pets):
            return
        self._cutin_at = now
        sprites = wardrobe.sprites_for(pet.ch.key, pet.skin)
        pic = None
        if sprites is not None:
            pic = sprites.images[sprites.sequence("skill")[-1]]
        g = self.ground_under(pet.pos_x)
        w = CutIn(pet.ch.key, pet.ch.name, pic, pet.pos_x, g.y, g.x1, g.x2)
        self.keep(w)
        w.show()

    def set_cutin(self, on: bool) -> None:
        self.state.cutin = on
        self.save()

    def set_season_fx(self, on: bool) -> None:
        self.state.season_fx = on
        self._refresh_season()
        log.info("계절 연출: %s", "켬" if on else "끔")
        self.save()

    # ── 신사 관리 창의 버튼들: 모양·크기·외출·도리이·부적 ──
    def on_action(self, name: str, value=None):
        handlers = {"look": self.set_look, "scale": self.set_scale, "out": lambda v: self.set_out(*v),
                    "torii": self.offer_torii, "pull": self.pull_omamori, "equip": self.equip_omamori,
                    "wpull": self.pull_wardrobe, "wear": lambda v: self.wear(*v), "wfx": lambda v: self.set_fx(*v),
                    "exchange": self.exchange_cloth, "shrine_skin": self.shrine_skin, "wbuy": self.buy_outfit,
                    "expedition": lambda v: self.send_expedition(*v), "title": self.set_title,
                    "festival": lambda _v: self.hold_festival()}
        return handlers[name](value)

    def set_look(self, stage: int) -> None:
        """신사 모양만 바꿈 (수입은 가장 높이 올린 단계 그대로)."""
        s = self.state
        s.shrine_look = 0 if stage >= s.shrine_level else max(1, stage)
        s.shrine_skin = ""                             # 단계 모양을 고르면 스킨은 벗음
        self.shrine.set_skin(None)
        self.shrine.set_level(s.look_stage)
        log.info("신사 모양: %d단계", s.look_stage)
        self.save()

    def shrine_skin(self, key: str) -> bool:
        """신사 스킨: 없으면 사서 입히고, 있으면 입히기 (입고 있는 걸 다시 누르면 원래 모양)."""
        s = self.state
        if key not in SHRINE_SKINS:
            return False
        name, price = SHRINE_SKINS[key]
        if key not in s.shrine_skins:
            if s.saisen < price:
                return False
            s.saisen -= price
            s.shrine_skins.append(key)
            s.shrine_skin = key
            self.shrine.set_saisen(s.saisen)
            self.shrine.pop(f"-{price:,}")
            self._say_at_shrine(f"🏯 {name} 완성!  (다시 누르면 원래 모양)")
            for p in self.pets:
                p.react(True)
            log.info("신사 스킨 구입: %s", key)
        else:
            s.shrine_skin = "" if s.shrine_skin == key else key
        self.shrine.set_skin(s.shrine_skin or None)
        if s.shrine_skin and not self.hidden_for_fullscreen:
            burst = PetalBurst(self.shrine.pos_x, self.shrine.y() + self.shrine.height())
            self.keep(burst)
            burst.show()
        self.save()
        return True

    def set_scale(self, k: float) -> None:
        self.state.size_scale = k
        self.shrine.set_level(self.shrine.level)
        for d in self.decors.values():
            d.rescale()
        for p in [*self.pets, *self.guests]:
            p.update()
        self._sync_torii()
        log.info("크기: %.2f", k)
        self.save()

    def set_out(self, key: str, out: bool) -> None:
        """친구를 작업표시줄에 내보내거나, 신사에서 쉬게 함."""
        s = self.state
        pet = next((p for p in self.pets if p.ch.key == key), None)
        if out:
            if key in s.resting:
                s.resting.remove(key)
            if pet is None and key in s.unlocked:
                self._drop_in(key)
        else:
            if key not in s.resting:
                s.resting.append(key)
            if pet is not None:
                if self.events.thief is pet:
                    self.events.cancel_thief()
                self.events.cancel_play()
                self.pets.remove(pet)
                pet.close()
                pet.deleteLater()
                self._say_at_shrine(f"{aff.josa(pet.ch.name, '은', '는')} 신사 안에서 쉬어요")
        self.save()

    def _drop_in(self, key: str) -> None:
        """하늘에서 신사 옆으로 뚝 (해금·다시 내보내기)."""
        pet = self._spawn(key)
        g = self.ground_under(self.shrine.pos_x)
        pet.pos_x = min(max(self.shrine.pos_x + random.uniform(-160, 160), g.x1 + 40), g.x2 - 40)
        pet.pos_y, pet.vx, pet.vy, pet.state, pet.on = max(self.top + 80, g.y - 600), 0.0, 0.0, "fall", None
        pet._place()
        if not self.hidden_for_fullscreen:
            pet.show()

    def _sync_torii(self) -> None:
        s = self.state
        name = torii.title(s)
        tip = f"센본토리이 {s.torii:,}개  ·  분당 새전 +{torii.income(s)}" + (f"  ·  「{name}」" if name else "")
        self.torii_row.setup(s.torii, self.scale, bool(self._night), tip)
        show = s.torii > 0 and s.show_torii and not self.hidden_for_fullscreen
        if show != self.torii_row.isVisible():
            if show:
                g = self.ground_under(self.shrine.pos_x)
                self.torii_row.place(self.shrine.x() + 10, self.shrine.x() + self.shrine.width() - 10, g.y, g.x1, g.x2)
            self.torii_row.setVisible(show)

    def offer_torii(self, k: int) -> list[str] | None:
        s = self.state
        before = s.saisen
        got = torii.offer(s, k)
        if got is None:
            return None
        self.shrine.set_saisen(s.saisen)
        self.shrine.pop(f"-{before - s.saisen:,}")
        self._sync_torii()
        log.info("도리이 %d개 봉납 → %d개", k, s.torii)
        self._say_at_shrine(f"⛩ 도리이 {k}개 봉납!  모두 {s.torii:,}개 · 분당 새전 +{torii.income(s)}")
        for i, name in enumerate(got):
            def cheer(name=name):
                self._say_at_shrine(f"🎉 「{name}」 — 도리이가 {s.torii:,}개가 됐다!")
                for p in self.pets:
                    p.react(True)
                if not self.hidden_for_fullscreen:
                    burst = PetalBurst(self.shrine.pos_x, self.shrine.y() + self.shrine.height())
                    self.keep(burst)
                    burst.show()
            self.later(1.6 + i * 2.0, cheer)
        self.save()
        return got

    def pull_omamori(self, n: int):
        s = self.state
        res = omamori.pull(s, n)
        if res is None:
            return None
        self.shrine.set_saisen(s.saisen)
        log.info("부적 뽑기 %d번: %s", n, [k for k, _ in res])
        if any(omamori.CHARMS[k].rarity == "SSR" for k, _ in res):
            for p in self.pets:
                p.react(True)
            if not self.hidden_for_fullscreen:
                burst = PetalBurst(self.shrine.pos_x, self.shrine.y() + self.shrine.height())
                self.keep(burst)
                burst.show()
        self.save()
        return res

    # ── 의상실 ──
    def pull_wardrobe(self, n: int):
        s = self.state
        res = wardrobe.pull(s, n)
        if res is None:
            return None
        self.shrine.set_saisen(s.saisen)
        log.info("의상실 뽑기 %d번: %s", n, [k for k, _ in res])
        if any(wardrobe.ITEMS[k].rarity == "SSR" for k, _ in res) and not self.hidden_for_fullscreen:
            burst = PetalBurst(self.shrine.pos_x, self.shrine.y() + self.shrine.height())
            self.keep(burst)
            burst.show()
            for p in self.pets:
                p.react(True)
        self.save()
        return res

    def wear(self, char: str, skin: str | None) -> bool:
        if not wardrobe.wear(self.state, char, skin):
            return False
        pet = next((p for p in self.pets if p.ch.key == char), None)
        if pet is not None:
            pet.skin = self.state.skins.get(char)
            pet.react(True)
            pet.update()
        self.save()
        return True

    def set_fx(self, char: str, fx: str | None) -> bool:
        if not wardrobe.set_effect(self.state, char, fx):
            return False
        pet = next((p for p in self.pets if p.ch.key == char), None)
        if pet is not None:
            pet.fx_kind = self.state.effects.get(char)
        self.save()
        return True

    # ── 원정 ──
    def send_expedition(self, key: str, place: str) -> bool:
        s = self.state
        if not expedition.send(s, key, place):
            return False
        p = expedition.PLACES[place]
        pet = next((x for x in self.pets if x.ch.key == key), None)
        if pet is not None:
            if self.events.thief is pet:
                self.events.cancel_thief()
            self.events.cancel_play()
            pet.scripted = True
            if pet.grounded:
                pet.act("wave", 1.4)
            say(f"{p.icon} {p.name}, 다녀올게!", pet.pos_x, pet.pos_y - 76, 2.4)

            def gone(pet=pet):
                if pet in self.pets:
                    self.pets.remove(pet)
                fade_window(pet, 0.0, 0.8, lambda: (pet.close(), pet.deleteLater()))
            self.later(1.5, gone)
        log.info("원정: %s → %s", key, place)
        self.save()
        return True

    def _check_expeditions(self) -> None:
        s = self.state
        done = expedition.finished(s)
        if not done:
            return
        for e in done:
            lines, prize = expedition.collect(s, e)
            key = e["char"]
            name = wardrobe.SHORT.get(key, CHARACTERS[key].name if key in CHARACTERS else key)
            p = expedition.PLACES[e["place"]]
            card = DiaryCard(f"🗺 원정 보고 — {p.icon} {p.name}", [ln.format(n=name) for ln in lines], prize)
            self.show_card(card)
            if key not in s.resting and all(x.ch.key != key for x in self.pets):
                self._drop_in(key)
            log.info("원정 귀환: %s (%s)", key, prize)
        self.shrine.set_saisen(s.saisen)
        self.save()
        self._check_achievements()

    # ── 업적 ──
    def _check_achievements(self) -> None:
        new = achievements.check(self.state)
        if not new:
            return
        self.shrine.set_saisen(self.state.saisen)
        if len(new) >= 3:                                  # 한꺼번에 많이 → 카드 한 장
            saisen = sum(a.reward[0] for a in new)
            cloth = sum(a.reward[1] for a in new)
            lines = [f"{a.icon} {a.name} — {a.desc}" for a in new[:8]]
            if len(new) > 8:
                lines.append(f"… 그리고 {len(new) - 8}개 더")
            self.show_card(DiaryCard(f"🏆 업적 {len(new)}개 달성!", lines,
                                     f"새전 +{saisen:,}" + (f"  ·  옷감 +{cloth}" if cloth else ""),
                                     "신사 관리 창 '부탁' 탭에서 칭호로 달 수 있어요"))
        else:
            for i, a in enumerate(new):
                self.later(i * 2.2, lambda a=a: self._say_at_shrine(
                    f"🏆 업적 달성: {a.name}  —  {achievements.reward_text(a)}"))
        for p in self.pets:
            p.react(True)
        log.info("업적: %s", [a.key for a in new])
        self.save()

    def set_title(self, key: str) -> bool:
        s = self.state
        if key and key not in s.achievements:
            return False
        s.title = "" if s.title == key else key
        self.save()
        return True

    # ── 낚시 ──
    def go_fishing(self) -> None:
        s = self.state
        if "pond" not in self.decors or self.hidden_for_fullscreen:
            return
        if getattr(self, "_fishing", None) is not None:
            return
        if not fishing.use_bait(s):
            self._say_at_shrine("🎣 오늘 미끼를 다 썼어요. 내일 또 낚시해요!")
            return
        pond = self.decors["pond"]
        g = self.ground_under(pond.pos_x)
        win = fishing.FishingWindow(pond.pos_x, g.y - pond.height() + 30, fishing.bait(s), self._fished)
        self._fishing = win
        win.destroyed.connect(lambda *_: setattr(self, "_fishing", None))
        win.show()
        self.save()

    def _fished(self, key: str | None, msg: str) -> None:
        s = self.state
        pond = self.decors.get("pond")
        x = pond.pos_x if pond is not None else self.shrine.pos_x
        y = (pond.y() if pond is not None else self.shrine.y()) - 120
        if key is None:
            self.save()
            return
        c = fishing.FISH[key]
        saisen, cloth, first = fishing.record(s, c)
        self.shrine.set_saisen(s.saisen)
        if saisen:
            self.shrine.pop(f"+{saisen:,}")
        prize = "  ".join(t for t in (f"새전 +{saisen:,}" if saisen else "", f"옷감 +{cloth}" if cloth else "") if t)
        say(f"🎣 {c.name}!" + (" (처음!)" if first else "") + (f"  {prize}" if prize else ""), x, y, 3.0)
        near = [p for p in self.pets if p.grounded and abs(p.pos_x - x) < 300]
        if near and c.kind != "junk":
            fan = random.choice(near)
            fan.react(True)
            self.later(0.8, lambda: self.events._say(fan, random.choice(["와, 큰 거다!", "대단해!", "오늘 저녁은 생선이다~"])))
        elif near:
            self.later(0.8, lambda: self.events._say(random.choice(near), random.choice(["…깡통이네.", "푸흡, 장화다!"])))
        log.info("낚시: %s", key)
        self._check_achievements()
        self.save()

    # ── 예대제 ──
    def hold_festival(self) -> bool:
        s = self.state
        price = festival.cost(s)
        if not festival.hold(s):
            return False
        self.shrine.set_saisen(s.saisen)
        self.shrine.pop(f"-{price:,}")
        self._say_at_shrine("🎆 예대제 개막!  2시간 동안 새전 수입 ×2, 손님이 몰려와요!")
        if not self.hidden_for_fullscreen:
            burst = PetalBurst(self.shrine.pos_x, self.shrine.y() + self.shrine.height())
            self.keep(burst)
            burst.show()
        self._refresh_festival()
        self.later(1.0, self._dance)
        log.info("예대제 개막 (%d)", price)
        self._check_achievements()
        self.save()
        return True

    def _refresh_festival(self) -> None:
        on = festival.active(self.state) and not self.hidden_for_fullscreen
        self.ffx.night = bool(self._night)
        if on != self.ffx.isVisible():
            if on:
                self.ffx.follow(self.shrine.pos_x, self.ground_under(self.shrine.pos_x).y)
            self.ffx.setVisible(on)

    def _dance(self) -> None:
        """본오도리: 다 같이 폴짝·손 흔들기."""
        dancers = [p for p in self.pets if p.grounded]
        for i, p in enumerate(dancers):
            self.later(i * 0.15, lambda p=p: p.grounded and p.act(random.choice(("happy", "wave")), 1.4))
        if dancers and not self.hidden_for_fullscreen:
            p = random.choice(dancers)
            say(random.choice(["♪ 왓쇼이~!", "♪ 축제다~!", "♪ 영차 영차!"]), p.pos_x, p.pos_y - 76, 2.2)

    def _festival_tick(self) -> None:
        s = self.state
        if festival.active(s):
            self._refresh_festival()
            self._dance()
            return
        self._refresh_festival()
        res = festival.finish(s)
        if res is None:
            return
        earned, tips = res
        self.shrine.set_saisen(s.saisen)
        self.show_card(DiaryCard("🎆 예대제 결산", [
            "참배객이 줄을 이었다! 친구들은 밤새 춤을 췄다.",
            f"축제 동안 모인 새전 {earned:,}"], f"참배객이 두고 간 새전 +{tips:,}",
            "24시간 뒤에 다시 열 수 있어요"))
        log.info("예대제 끝: 모인 새전 %d, 참배객 %d", earned, tips)
        self.save()

    # ── 붐빔 조절 ──
    def _eligible(self) -> list[str]:
        base = list(CHARACTERS) if os.environ.get("HOKORA_ALL") == "1" else self.state.unlocked
        away = expedition.away(self.state)
        return [k for k in base if k not in self.state.resting and k not in away and k not in self._room_in
                and k not in self._abducted]

    # ── 놀잇감 (새전으로 엶) ──
    def use_goods(self, key: str) -> None:
        if key not in self.state.goods:
            self.show_goods(key)
        elif key == "brush":
            self.start_drawing()
        elif key == "room":
            self.open_room()

    def show_goods(self, key: str) -> None:
        c = goods.GoodsCard(self, key)
        self.keep(c)
        c.show_near(QPoint(round(self.shrine.pos_x), round(self.shrine.y())))

    def buy_goods(self, key: str) -> bool:
        g, s = goods.GOODS[key], self.state
        if key in s.goods or s.saisen < g.price:
            return False
        s.saisen -= g.price
        s.goods.append(key)
        self.shrine.set_saisen(s.saisen)
        self._say_at_shrine(f"{g.icon} {aff.josa(g.name, '을', '를')} 손에 넣었다!")
        log.info("놀잇감 삼: %s", key)
        self.save()
        return True

    # ── 신사 안 들여다보기 ──
    def room_friends(self) -> list[str]:
        """신사 안에 있는 친구: 해금했지만 작업표시줄에 안 나와 있고 원정도 안 간 친구."""
        base = list(CHARACTERS) if os.environ.get("HOKORA_ALL") == "1" else self.state.unlocked
        out = {p.ch.key for p in self.pets}
        away = expedition.away(self.state)
        return [k for k in base if k in CHARACTERS and k not in out and k not in away and k not in self._abducted]

    def open_room(self) -> None:
        if self._room is not None:
            self._room.raise_()
            return
        invited: list[str] = []
        need = 2 - len(self.room_friends())
        if need > 0:                                     # 안이 비었으면 밖에 있던 친구가 잠깐 들어옴
            free = [p for p in self.pets if p.grounded and p.isVisible() and self.events.thief is not p]
            random.shuffle(free)
            for pet in free[:need]:
                self.pets.remove(pet)
                self._room_in.add(pet.ch.key)
                invited.append(pet.ch.key)
                fade_window(pet, 0.0, 0.5, lambda pet=pet: (pet.close(), pet.deleteLater()))
        self.state.room_visits += 1
        w = room.RoomWindow(self, invited)
        self._room = w
        self.keep(w)
        w.place_near(self.shrine.pos_x, self.shrine.y())
        w.show()
        w.raise_()
        log.info("신사 안 들여다보기: 안에 %s (잠깐 들어옴 %s)", self.room_friends(), invited)
        self.save()

    def room_closed(self) -> None:
        """신사 안 창을 닫음: 잠깐 들어갔던 친구는 다시 밖으로."""
        self._room = None
        back, self._room_in = sorted(self._room_in), set()
        elig = self._eligible()
        for k in back:
            if k in elig and not any(p.ch.key == k for p in self.pets):
                self._drop_in(k)
        if back:
            self._crowd_tick()

    def on_room_snack(self) -> None:
        self.state.snacks += 1

    # ── 누에의 UFO (eSheep 오마주) ──
    def _ufo_roll(self) -> None:
        if (self.ufo is not None or self.hidden_for_fullscreen or self.napping or self.visits.visit is not None
                or time.monotonic() - self._started < ufo.FIRST_AFTER):
            return
        if random.random() < ufo.CHANCE_PER_30S:
            self.summon_ufo()

    def summon_ufo(self) -> bool:
        if self.ufo is not None or self.hidden_for_fullscreen:
            return False
        free = [p for p in self.pets if p.grounded and p.isVisible() and self.events.thief is not p]
        if not free:
            return False
        self.ufo = ufo.Ufo(self, random.choice(free))
        self._restack()
        log.info("UFO 등장: %s 노림", self.ufo.pet.ch.key)
        return True

    def ufo_beam(self, pet: PetWindow) -> None:
        self.events._say(pet, random.choice(["으아아, 몸이 떠!", "뭐, 뭐야 이 빛은?!", "살려 줘~!"]), 2.5)

    def ufo_shot(self, u: ufo.Ufo, saved: bool) -> None:
        s = self.state
        reward = max(200, s.income_per_min * 15) * (3 if u.rainbow else 1)
        s.add_saisen(reward)
        s.ufo_shot += 1
        self.shrine.set_saisen(s.saisen)
        self.shrine.pop(f"+{reward}")
        self._say_at_shrine(f"🛸 UFO 격추!{'  무지개 UFO라 새전 ×3!' if u.rainbow else ''}  새전 +{reward:,}")
        if saved:
            self.later(1.4, lambda p=u.pet: p in self.pets and self.events._say(p, random.choice(ufo.LINES_SAVED)))
        ufo.nue_appears(self, u.x, u.y + 10)           # UFO 의 주인이 떨어짐
        log.info("UFO 격추 (%s): 새전 +%d", "구출" if saved else "오기 전", reward)
        self.check_unlocks()
        self.save()

    def ufo_rescued(self, u: ufo.Ufo) -> None:
        s = self.state
        reward = max(100, s.income_per_min * 6)
        s.add_saisen(reward)
        s.ufo_rescued += 1
        self.shrine.set_saisen(s.saisen)
        self._say_at_shrine(f"🛸 붙잡아서 구출!  새전 +{reward:,}")
        log.info("UFO 에서 잡아채 구출: %s", u.pet.ch.key)
        self.save()

    def ufo_abduct(self, pet: PetWindow) -> None:
        if pet in self.pets:
            self.pets.remove(pet)
        pet.hide()
        pet.close()
        pet.deleteLater()
        self._abducted[pet.ch.key] = time.time() + ufo.AWAY_TIME
        self.state.ufo_taken += 1
        self._say_at_shrine(f"🛸 {aff.josa(pet.ch.name, '이', '가')} UFO에 끌려갔다…!  (10분 뒤 돌아와요)")
        log.info("UFO 에 끌려감: %s", pet.ch.key)
        self.save()

    def _ufo_returns(self) -> None:
        """끌려간 친구가 선물을 들고 돌아옴."""
        now = time.time()
        for key, at in list(self._abducted.items()):
            if now < at:
                continue
            del self._abducted[key]
            if key not in self._eligible() or any(p.ch.key == key for p in self.pets):
                continue
            self._drop_in(key)
            s = self.state
            reward = max(300, s.income_per_min * 10)
            s.add_saisen(reward)
            s.cloth += 5
            self.shrine.set_saisen(s.saisen)
            pet = next(p for p in self.pets if p.ch.key == key)
            self.later(1.5, lambda p=pet, r=reward: p in self.pets and self.events._say(
                p, f"UFO에서 돌아왔어… 이거 선물! (새전 +{r:,} · 옷감 +5)", 4.0))
            log.info("UFO 에서 돌아옴: %s", key)

    # ── 니토리의 오이 시세 (동물의 숲 무 주식 오마주) ──
    def open_cucumber(self) -> None:
        w = cucumber.CucumberWindow(self)
        self.keep(w)
        w.show_near(QPoint(round(self.shrine.pos_x), round(self.shrine.y())))

    def on_cucumber(self, text: str) -> None:
        self.shrine.set_saisen(self.state.saisen)
        self._say_at_shrine(text)
        log.info("오이: %s", text)
        self.save()

    # ── 공물 (고양이 수집 오마주) ──
    def open_offering(self) -> None:
        w = offering.OfferingWindow(self)
        self.keep(w)
        w.show_near(QPoint(round(self.shrine.pos_x), round(self.shrine.y())))

    def place_offering(self, key: str, cucumbers: bool = False) -> bool:
        if not offering.place(self.state, key, cucumbers):
            return False
        o = offering.OFFERINGS[key]
        self.shrine.set_saisen(self.state.saisen)
        self._sync_offering()
        self._say_at_shrine(f"{o.icon} {aff.josa(o.name, '을', '를')} 공물로 올렸다!")
        log.info("공물: %s", key)
        self.save()
        return True

    def clear_offering(self) -> None:
        self.state.offering = ""
        self._sync_offering()
        self.save()

    def _sync_offering(self) -> None:
        s = self.state
        show = bool(s.offering) and not self.hidden_for_fullscreen
        self.offer_tray.set_offering(s.offering)
        if show:
            self.offer_tray.follow(self.shrine.pos_x, self.ground_under(self.shrine.pos_x).y, self.shrine.width())
        if show != self.offer_tray.isVisible():
            self.offer_tray.setVisible(show)
            if show:
                self._restack()

    def offering_seen(self, kind: str) -> None:
        """손님이 옴: 공물을 좋아하는 손님이면 조금 뒤 먹고 답례품을 두고 감."""
        if offering.wanted(self.state) == kind:
            self.later(offering.EAT_AFTER, lambda: self._offering_eaten(kind))

    def _offering_eaten(self, kind: str) -> None:
        s = self.state
        if offering.wanted(s) != kind:
            return
        key = s.offering
        o = offering.OFFERINGS[key]
        gift, saisen, cloth, first = offering.receive(s, kind)
        self._sync_offering()
        self.shrine.set_saisen(s.saisen)
        self.shrine.pop(f"+{saisen}")
        self._say_at_shrine(f"{o.icon} {offering.SHORT[kind]}: 「{o.name}」 잘 먹을게~!")
        self.show_card(offering.GiftCard(kind, key, gift, saisen, cloth, first))
        log.info("공물 먹음: %s → 답례품 %s", key, gift)
        self.check_unlocks()
        self.save()

    def set_max_out(self, n: int) -> None:
        self.state.max_out = max(0, int(n))
        self._crowd_tick()
        log.info("동시에 나와 있는 친구: %s", n or "전부")
        self.save()

    def _crowd_tick(self, rotate: bool = False) -> None:
        elig = self._eligible()
        cap = self.state.max_out or len(elig)
        now = time.monotonic()

        def free(p) -> bool:
            return (not p.scripted and p.state not in ("held", "fall", "jump") and self.events.thief is not p
                    and p.on is not None)

        def home(p) -> None:
            self.pets.remove(p)
            self._bench_since[p.ch.key] = now
            fade_window(p, 0.0, 0.6, lambda p=p: (p.close(), p.deleteLater()))

        def out() -> list:
            return [p for p in self.pets if p.ch.key in elig]
        if rotate and len(elig) > cap:                     # 오래 나와 있던 친구가 쉬러 들어가고
            cands = [p for p in out() if free(p)]
            if cands:
                home(min(cands, key=lambda p: self._out_since.get(p.ch.key, 0.0)))
        while len(out()) > cap:
            cands = [p for p in out() if free(p)]
            if not cands:
                break
            home(min(cands, key=lambda p: self._out_since.get(p.ch.key, 0.0)))
        shown = {p.ch.key for p in out()}
        benched = sorted((k for k in elig if k not in shown), key=lambda k: self._bench_since.get(k, 0.0))
        while len(shown) < cap and benched:                # 오래 쉰 친구부터 나옴
            k = benched.pop(0)
            self._drop_in(k)
            shown.add(k)

    # ── 시계 친구·PC 상태 반응 ──
    def _life_tick(self) -> None:
        if self.hidden_for_fullscreen or self.napping:
            return
        from datetime import datetime as _dt
        now = _dt.now()
        if self.state.clock_friend and now.minute == 0 and self._chimed != (now.date(), now.hour):
            self._chimed = (now.date(), now.hour)
            self._chime(now.hour)
        if self.state.pc_react:
            self._pc_n += 1
            self._pc_tick(recycle=self._pc_n % 30 == 1)        # 휴지통은 10분마다

    def _speaker(self, prefer: tuple[str, ...] = ()):
        free = [p for p in self.pets if p.grounded and p.isVisible()]
        for k in prefer:
            for p in free:
                if p.ch.key == k:
                    return p
        return random.choice(free) if free else None

    def _chime(self, hour: int) -> None:
        p = self._speaker(("remilia", "flandre") if hour == 0 else ())
        if p is None:
            return
        p.act("wave", 2.0)
        sign = lifesense.HourSign(p, lifesense.hour_text(hour))
        self.keep(sign)
        sign.show()
        self.later(0.6, lambda: say(lifesense.hour_line(hour, p.ch.key), p.pos_x, p.pos_y - 150, 3.5))
        log.info("시계 친구: %d시 (%s)", hour, p.ch.key)

    def _ok_to_say(self, what: str, every: float) -> bool:
        now = time.monotonic()
        if now - self._said.get(what, -1e9) < every:
            return False
        self._said[what] = now
        return True

    def _pc_tick(self, recycle: bool = False) -> None:
        pct, charging = winutil.battery()
        if pct is not None:
            if pct <= lifesense.BATTERY_LOW and not charging:
                if not self._batt_low or self._ok_to_say("battery", 20 * 60):
                    self._batt_low = True
                    self._said["battery"] = time.monotonic()
                    sleepy = [p for p in self.pets if p.grounded][:3]
                    for q in sleepy:
                        q.act("sit", 8)
                    p = self._speaker()
                    if p is not None:
                        self.events._say(p, lifesense.pick(lifesense.LOW_BATTERY, p=pct), 3.5)
            elif charging and self._batt_low:
                self._batt_low = False
                for q in self.pets:
                    q.react(True)
                p = self._speaker()
                if p is not None:
                    self.events._say(p, lifesense.pick(lifesense.CHARGING), 3.0)
            elif pct > lifesense.BATTERY_LOW + 10:
                self._batt_low = False
        cpu = self._cpu.sample()
        self._cpu_hot = self._cpu_hot + 1 if cpu is not None and cpu >= lifesense.CPU_HOT else 0
        if self._cpu_hot >= 3 and self._ok_to_say("cpu", 15 * 60):      # 1분쯤 계속 바쁨
            p = self._speaker()
            if p is not None:
                p.act("wave", 2.4)                                    # 부채질
                self.events._say(p, lifesense.pick(lifesense.CPU_HOT_LINES), 3.0)
        from datetime import datetime as _dt
        h = _dt.now().hour
        if 1 <= h <= 4 and winutil.idle_seconds() < 120 and self._ok_to_say("late", 6 * 3600):
            p = self._speaker(("reimu", "sakuya"))
            if p is not None:
                p.act("sit", 6)
                self.events._say(p, lifesense.pick(lifesense.LATE_LINES, h=h), 3.5)
        if recycle:
            info = winutil.recycle_bin()
            if lifesense.recycle_full(info) and self._ok_to_say("recycle", 3 * 3600):
                p = self._speaker(("reimu",))
                if p is not None:
                    if p.ch.key == "reimu":
                        p.act("skill", 4.0)                           # 빗자루질
                    n, size = info
                    self.events._say(p, f"🗑 {lifesense.pick(lifesense.RECYCLE_LINES)}  ({n:,}개 · {lifesense.fmt_bytes(size)})", 4.0)
                    log.info("휴지통 알림: %d개 %d바이트", n, size)

    def _full_moon_night(self) -> None:
        self._say_at_shrine("🌕 오늘은 보름달! 밤 동안 새전 수입 ×1.3")
        p = self._speaker(("remilia", "flandre"))
        if p is not None and p.ch.key in ("remilia", "flandre"):
            p.react(True)
            self.later(1.2, lambda: self.events._say(p, "보름달이야… 기분 좋은 밤이네."))

    def set_clock_friend(self, on: bool) -> None:
        self.state.clock_friend = on
        self.save()

    def set_pc_react(self, on: bool) -> None:
        self.state.pc_react = on
        self.save()

    def set_show_torii(self, on: bool) -> None:
        """센본토리이 줄을 보이거나 숨김. 숨겨도 분당 새전은 그대로."""
        self.state.show_torii = on
        self._sync_torii()
        log.info("센본토리이 %s", "보임" if on else "숨김")
        self.save()

    def set_fullscreen_show(self, on: bool) -> None:
        self.state.fullscreen_show = on
        self._watch()
        log.info("전체화면에서도 돌아다니기: %s", "켬" if on else "끔")
        self.save()

    # ── 손님 방울: 손님이 오면 Windows 알림 ──
    def buy_guest_bell(self) -> bool:
        s = self.state
        if s.guest_bell or s.saisen < BELL_PRICE:
            return False
        s.saisen -= BELL_PRICE
        s.guest_bell = s.guest_bell_on = True
        self.shrine.set_saisen(s.saisen)
        self._say_at_shrine("🔔 손님 방울을 달았다! 손님이 오면 딸랑~ 알려 줄게")
        log.info("손님 방울 삼")
        self.save()
        return True

    def set_guest_bell(self, on: bool) -> None:
        self.state.guest_bell_on = on
        self.save()

    def set_guest_bell_sound(self, on: bool) -> None:
        self.state.guest_bell_sound = on
        log.info("손님 방울 소리: %s", "켬" if on else "끔")
        self.save()

    def preview_bell(self) -> None:
        sound.play_suzu()

    def ring_bell(self, kind: str) -> None:
        s = self.state
        if not (s.guest_bell and s.guest_bell_on):
            return
        text = BELL_TEXT.get(kind, "손님이 찾아왔어요!")
        self.last_bell = text
        if self.tray is not None:
            self.tray.showMessage("🔔 딸랑딸랑~ 손님이 왔어요", text, self.app.windowIcon(), 6000)
        if s.guest_bell_sound and not self.hidden_for_fullscreen:   # 게임·영상 전체화면 중엔 소리 안 냄
            sound.play_suzu()
        self._say_at_shrine("🔔 딸랑딸랑~ 손님이다!")
        log.info("손님 방울: %s", kind)

    # ── 신사 명함 ──
    def make_card(self) -> None:
        img, path = card.make(self)
        photo.to_clipboard(img)
        self.state.cards += 1
        self.show_card(PhotoCard(img, path, "🪪 신사 명함을 만들었어요"))
        log.info("신사 명함: %s", path)
        self.save()

    # ── 처음 안내 ──
    def _tutorial_show(self) -> None:
        step = tutorial.current(self.state)
        if step is None:
            if self.tip is not None:
                self.tip.close()
                self.tip = None
            return
        if step[0] == "omikuji" and not can_draw(self.state):   # 오늘 이미 뽑았으면 건너뜀
            tutorial.advance(self.state, "omikuji")
            return self._tutorial_show()
        if self.tip is None:
            self.tip = tutorial.Tip(self._tutorial_skip)
        self.tip.set_text(step[1])
        self._tutorial_follow()
        if not self.hidden_for_fullscreen:
            self.tip.show()

    def _tutorial_follow(self) -> None:
        step = tutorial.current(self.state)
        if step is None or self.tip is None:
            return
        if step[2] == "pet" and self.pets:
            p = next((x for x in self.pets if x.ch.key == "reimu"), self.pets[0])
            self.tip.point_at(p.pos_x, p.pos_y - 72)
        else:
            self.tip.point_at(self.shrine.pos_x, self.shrine.y() + 24)

    def _tutorial_event(self, event: str) -> None:
        if tutorial.current(self.state) is None:
            return
        finished = tutorial.advance(self.state, event)
        if finished:
            if self.tip is not None:
                self.tip.close()
                self.tip = None
            self.shrine.set_saisen(self.state.saisen)
            self.later(1.0, lambda: self._say_at_shrine(
                f"🎉 안내 끝! 새전 +{tutorial.REWARD}  —  새전을 모아 신사를 키우면 새 친구가 찾아와요 (도감 탭)"))
            self.save()
        elif tutorial.current(self.state) is not None:
            self.later(0.8, self._tutorial_show)

    def _tutorial_skip(self) -> None:
        self.state.tutorial = tutorial.DONE
        if self.tip is not None:
            self.tip.close()
            self.tip = None
        self.save()

    def restart_tutorial(self) -> None:
        self.state.tutorial = 0
        self._tutorial_show()

    # ── 설정 창 ──
    def open_settings(self) -> None:
        w = SettingsWindow(self)
        self.keep(w)
        w.show_near(QPoint(round(self.shrine.pos_x), round(self.shrine.y())))

    def set_autostart(self, on: bool) -> None:
        winutil.set_autostart(on, ENTRY_SCRIPT)

    def open_data_dir(self) -> None:
        try:
            os.startfile(str(self.store.path.parent))
        except (OSError, AttributeError):
            log.exception("데이터 폴더 열기 실패")

    def restore_backup(self, path) -> None:
        if not self.store.restore(path):
            QMessageBox.warning(None, "Hokora", "백업을 되돌리지 못했어요. 로그를 확인해 주세요.")
            return
        log.info("백업 되돌림: %s → 다시 시작", path.name)
        self._restart()

    def _restart(self) -> None:
        if getattr(sys, "frozen", False):
            QProcess.startDetached(sys.executable, ["--restarted"])
        else:
            QProcess.startDetached(sys.executable, [str(ENTRY_SCRIPT), "--restarted"])
        self.app.quit()

    def buy_outfit(self, item_id: str) -> bool:
        """기간 한정 의상을 (기간이 아닐 때) 새전으로."""
        before = self.state.saisen
        if not wardrobe.buy_with_saisen(self.state, item_id):
            return False
        self.shrine.set_saisen(self.state.saisen)
        self.shrine.pop(f"-{before - self.state.saisen:,}")
        self._say_at_shrine(f"👘 {wardrobe.ITEMS[item_id].name} 의상을 샀다!")
        log.info("기간 한정 의상 구입: %s", item_id)
        self.save()
        return True

    def exchange_cloth(self, item_id: str) -> bool:
        ok = wardrobe.exchange(self.state, item_id)
        if ok:
            log.info("옷감 교환: %s", item_id)
            self.save()
        return ok

    def equip_omamori(self, key: str) -> bool:
        ok = omamori.toggle_equip(self.state, key)
        if ok:
            self.save()
        return ok

    # ── 사진 찍기 ──
    def take_photo(self) -> None:
        """다들 신사 양옆에 줄을 서서 손을 흔들면 찰칵."""
        if self.hidden_for_fullscreen:
            return
        self.events.cancel_thief()
        self.events.cancel_play()
        self._say_at_shrine("다들 모여~ 사진 찍자!")
        g = self.ground_under(self.shrine.pos_x)
        half = self.shrine.width() / 2 - 6
        lineup = [p for p in self.pets if not p.scripted and p.state not in ("held", "sleep")]
        for i, p in enumerate(lineup):                   # 신사 오른쪽·왼쪽 번갈아 한 줄로
            side = 1 if i % 2 == 0 else -1
            x = self.shrine.pos_x + side * (half + 30 + (i // 2) * 52)
            p.pos_x = min(max(x, g.x1 + 30), g.x2 - 30)
            p.pos_y, p.vx, p.vy, p.state, p.on = g.y - 70, 0.0, 0.0, "fall", None
            p._to_cursor = p._follow = False
            p.facing = -side
            p._place()

        def pose():
            self._say_at_shrine("자, 찍는다~ 하나, 둘…")
            for p in lineup:
                if p.on is not None and p.state not in ("held", "fall", "jump"):
                    p.act("wave", 2.4)
        self.later(1.0, pose)
        self.later(2.2, self._shoot)

    def _shoot(self) -> None:
        got = photo.take(self)
        if got is None:
            return
        img, path = got
        photo.to_clipboard(img)
        self.state.photos += 1
        flash = Flash(self.shrine.pos_x, self.ground_under(self.shrine.pos_x).y - 70)
        self.keep(flash)
        flash.show()
        self.show_card(PhotoCard(img, path))
        log.info("사진: %s", path)
        daily.bump(self.state, "photo")
        self._daily_check()
        self.save()

    def _check_nap(self) -> None:
        """자리를 비우면 다들 그 자리에서 낮잠, 돌아오면 깨어나 반긴다."""
        idle = winutil.idle_seconds()
        if not self.napping and idle >= NAP_AFTER:
            self.napping = True
            self.events.cancel_play()
            self.visits.cancel()
            if self.ufo is not None:
                self.ufo.cancel()
                self.ufo = None
            self._nap_start = time.time() - idle          # 실제로 자리를 비운 시각
            self._nap_total = self.state.saisen_total
            self.events.cancel_thief()
            log.info("자리 비움 %.0f초 → 낮잠", idle)
        elif self.napping and idle < 3:
            self.napping = False
            log.info("돌아옴 → 깨어남")
            away = time.time() - self._nap_start
            if away >= MIN_AWAY:
                QTimer.singleShot(1800, lambda: self._show_diary(
                    away, self._nap_start, self.state.saisen_total - self._nap_total, offline=False))
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

    def _show_diary(self, seconds: float, start: float, earned: int, offline: bool) -> None:
        if self.hidden_for_fullscreen:
            return
        self.shrine.set_saisen(self.state.saisen)
        card = away_card(self.state, seconds, start, earned, offline)
        self.show_card(card)

    def show_card(self, card) -> None:
        """카드(일기·출석·신문·사진)는 겹치지 않게 하나가 닫히면 다음 것을."""
        if self.hidden_for_fullscreen:
            card.deleteLater()
            return
        self._card_queue.append(card)
        card.destroyed.connect(lambda *_, c=card: self._card_done(c))
        if len(self._card_queue) == 1:
            card.show_above(self.shrine.pos_x, self.shrine.y() + 20)

    def _card_done(self, card) -> None:
        head = self._card_queue and self._card_queue[0] is card
        if card in self._card_queue:
            self._card_queue.remove(card)
        if head and self._card_queue:
            nxt = self._card_queue[0]
            QTimer.singleShot(500, lambda: nxt in self._card_queue and nxt.show_above(
                self.shrine.pos_x, self.shrine.y() + 20))

    # ── 친해지기: 말 걸기·선물 ──
    def on_pet_menu(self, pet: PetWindow, global_pos: QPoint) -> None:
        self._tutorial_event("menu")
        s, key = self.state, pet.ch.key
        menu = QMenu()
        menu.setStyleSheet(MENU_STYLE)
        if pet in self.guests:                     # 손님: 말 걸기 (+ 스이카는 술 대접)
            head = menu.addAction(f"{pet.ch.name}   (손님)")
            head.setEnabled(False)
            self.visits.fill_menu(pet, menu)
            menu.addSeparator()
            self._fill_menu(menu)
            menu.exec(global_pos)
            return
        head = menu.addAction(f"{pet.ch.name}   {aff.hearts(s, key)}")
        head.setEnabled(False)
        menu.addAction("💬 말 걸기", lambda: self.talk_to(pet))
        menu.addAction("🏠 신사에서 쉬게 하기", lambda: self.set_out(key, False))
        trip = menu.addMenu("🗺 원정 보내기")
        trip.setStyleSheet(MENU_STYLE)
        why = expedition.can_send(s, key)
        for pk, pl in expedition.PLACES.items():
            r = expedition.reward_for(s, key, pk)
            fit = "  ★적성" if key in pl.fits else ""
            act = trip.addAction(f"{pl.icon} {pl.name}  ({pl.hours:g}시간 · 새전 {r['saisen']:,}){fit}",
                                 lambda pk=pk: self.send_expedition(key, pk))
            act.setEnabled(not why)
        if why:
            trip.addSeparator()
            note = trip.addAction(why)
            note.setEnabled(False)
        mine = [i for i in s.wardrobe if i.startswith(f"{key}:")]
        fxs = [i for i in s.wardrobe if i.startswith("fx:")]
        if mine:
            clothes = menu.addMenu("👘 옷 갈아입기")
            clothes.setStyleSheet(MENU_STYLE)
            for skin, name in [(None, "기본 옷")] + [(i.split(":")[1], wardrobe.ITEMS[i].name) for i in mine]:
                act = clothes.addAction(name, lambda skin=skin: self.wear(key, skin))
                act.setCheckable(True)
                act.setChecked(s.skins.get(key) == skin)
        if fxs:
            effects = menu.addMenu("✨ 이펙트")
            effects.setStyleSheet(MENU_STYLE)
            for fx, name in [(None, "없음")] + [(i.split(":")[1], wardrobe.ITEMS[i].name) for i in fxs]:
                act = effects.addAction(name, lambda fx=fx: self.set_fx(key, fx))
                act.setCheckable(True)
                act.setChecked(s.effects.get(key) == fx)
        gifts = menu.addMenu("🎁 선물하기")
        gifts.setStyleSheet(MENU_STYLE)
        known = aff.level(s, key) >= 2                      # 친해지면 좋아하는 선물을 알게 됨
        for gk, (name, icon, price) in aff.GIFTS.items():
            fav = "  ♥ 좋아함" if known and gk in aff.FAVORITES.get(key, ()) else ""
            a = gifts.addAction(f"{icon} {name}  (새전 {price}){fav}", lambda gk=gk: self.give_gift(pet, gk))
            a.setEnabled(s.saisen >= price)
        menu.addSeparator()
        self._fill_menu(menu)
        menu.exec(global_pos)

    def _add_affection(self, pet: PetWindow, amount: int) -> None:
        if aff.add(self.state, pet.ch.key, amount):
            lv = aff.level(self.state, pet.ch.key)
            say(f"♥ {aff.josa(pet.ch.name, '과', '와')} 더 친해졌다!  {aff.hearts(self.state, pet.ch.key)}",
                pet.pos_x, pet.pos_y - 76, 3.5)
            pet.hearts.extend([[0.0, pet.width() / 2 + dx, 40] for dx in (-12, 0, 12)])
            log.info("호감도: %s Lv.%d", pet.ch.key, lv)

    def talk_to(self, pet: PetWindow) -> None:
        line, gained = aff.talk(self.state, pet.ch.key)
        pet.facing = 1 if self.cursor.x() > pet.pos_x else -1
        if pet.grounded:
            pet.act("wave", 1.6)
        say(line, pet.pos_x, pet.pos_y - 76, 3.5)
        if gained:
            gained += int(omamori.bonus(self.state, "affection"))   # 인연 부적
            self.later(1.2, lambda: self._add_affection(pet, gained))
            daily.bump(self.state, "talk")             # 그날 처음 말 건 친구만
            self._daily_check()
        self.save()

    def give_gift(self, pet: PetWindow, gift_key: str) -> None:
        ok, gained, fav = aff.gift(self.state, pet.ch.key, gift_key)
        if not ok:
            return
        name, icon, _ = aff.GIFTS[gift_key]
        self.shrine.set_saisen(self.state.saisen)
        pet.react(True)
        line = random.choice([f"{icon} {name}! 제일 좋아해!", f"{icon} 와아, {aff.josa(name, '이다', '다')}!"]) if fav else \
            random.choice([f"{icon} 고마워!", f"{icon} 잘 먹을게~"])
        say(line, pet.pos_x, pet.pos_y - 76, 3.0)
        self._add_affection(pet, gained + int(omamori.bonus(self.state, "affection")))
        daily.bump(self.state, "gift")
        self._daily_check()
        self.save()

    # ── 참배 ──
    def pray(self, key: str) -> None:
        if not buy_wish(self.state, key, can_draw(self.state)):
            return
        w = WISHES[key]
        log.info("참배: %s", key)
        daily.bump(self.state, "pray")
        self.shrine.set_saisen(self.state.saisen)
        if key == "snack":
            self.gather()
            self.later(1.6, lambda: [p.react(True) for p in self.pets])
            self._say_at_shrine("간식 시간이다~!")
        elif key == "omikuji":
            self._say_at_shrine("소원을 빌었다. 오미쿠지를 한 번 더 뽑을 수 있어요!")
        else:
            self._say_at_shrine(f"{w.icon} {w.name}!  {w.desc}")
        self._daily_check()
        self.save()

    # ── 신사 꾸미기 ──
    def set_show_decor(self, on: bool) -> None:
        """장식을 보이거나 숨김. 숨겨도 놓아 둔 장식의 새전 보너스는 그대로."""
        self.state.show_decor = on
        for k, win in self.decors.items():
            win.setVisible(on and not self.hidden_for_fullscreen and k != self.visits.hidden_decor)
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
            win.set_night(bool(self._night))
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
        w = DecorWindow.width_for(key) * self.scale
        g = self.ground_under(self.shrine.pos_x)
        taken = [(self.shrine.pos_x - self.shrine.width() / 2, self.shrine.pos_x + self.shrine.width() / 2)]
        if self.torii_row.isVisible():
            taken.append((self.torii_row.x(), self.torii_row.x() + self.torii_row.width()))
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
        self._tutorial_event("omikuji")
        result = draw_omikuji(self.state)
        log.info("오미쿠지: %s (+%d)", result.fortune.rank, result.reward)
        self.shrine.set_saisen(self.state.saisen)
        self.shrine.pop(f"+{result.reward}")
        for pet in self.pets:
            pet.react(result.fortune.good)
        slip = FortuneSlip(result)
        slip.show_above(self.shrine.pos_x, self.shrine.y() + 20)
        daily.bump(self.state, "omikuji")
        self.later(2.0, self._daily_check)
        self.save()
        self.check_unlocks()

    def upgrade(self) -> None:
        if not self.state.upgrade_shrine():
            return
        s = self.state
        self.shrine.set_level(s.look_stage)
        self.shrine.set_saisen(s.saisen)
        self.on_shrine_moved(self.shrine.pos_x)
        log.info("신사 업그레이드 → %s", s.stage_name)
        self._say_at_shrine(f"{s.stage_name}로 커졌다!  분당 새전 {s.income_per_min}")
        if not self.hidden_for_fullscreen:                    # 벚꽃잎 흩날림
            burst = PetalBurst(self.shrine.pos_x, self.shrine.y() + self.shrine.height())
            self.keep(burst)
            burst.show()
        for pet in self.pets:
            pet.react(True)
        self.save()
        self.check_unlocks()

    def upgrade_box(self) -> None:
        if not self.state.upgrade_box():
            return
        cap_h, rate, _ = SAISEN_BOX[self.state.box_level]
        log.info("새전함 → Lv.%d", self.state.box_level)
        self.shrine.set_saisen(self.state.saisen)
        self._say_at_shrine(f"새전함 Lv.{self.state.box_level}!  꺼져 있어도 최대 {cap_h}시간·{int(rate * 100)}% 모아요")
        self.save()

    def check_unlocks(self) -> None:
        """조건을 채운 캐릭터가 있으면 하늘에서 신사 옆으로 떨어뜨리며 등장."""
        for key in newly_unlocked(self.state):
            self.state.unlocked.append(key)
            log.info("해금: %s", key)
            if all(p.ch.key != key for p in self.pets):
                self._drop_in(key)
            if not self.hidden_for_fullscreen:
                self._say_at_shrine(UNLOCKS[key].arrive_line)
            self.save()

    def on_context_menu(self, global_pos: QPoint) -> None:
        self._tutorial_event("menu")
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
        menu.addAction("📸 사진 찍기", self.take_photo)
        menu.addAction("🪪 신사 명함 만들기", self.make_card)
        for key in ("brush", "room"):
            g = goods.GOODS[key]
            text = g.use if key in s.goods else f"🔒 {g.use.split(' ', 1)[1]}  (새전 {g.price:,})"
            menu.addAction(text, lambda key=key: self.use_goods(key))
        if self.ink:
            menu.addAction("🧽 그린 길 지우기", self.clear_ink)
        menu.addAction("🍙 공물 올리기" + (f"  ({offering.OFFERINGS[s.offering].icon} 올려 둠)"
                                          if s.offering in offering.OFFERINGS else ""), self.open_offering)
        if s.guest_visits.get("nitori") or os.environ.get("HOKORA_ALL") == "1":
            menu.addAction("🥒 오이 시세" + (f"  (오이 {s.cuke_have:,}개)" if s.cuke_have else ""), self.open_cucumber)
        else:
            locked = menu.addAction("🥒 오이 시세 — 니토리를 만나면 열려요")
            locked.setEnabled(False)
        if "pond" in self.decors:
            menu.addAction(f"🎣 낚시하기  (미끼 {fishing.bait(s)}개)", self.go_fishing)
        if can_draw(s):
            menu.addAction("오늘의 오미쿠지 뽑기", self.omikuji)
        menu.addAction("모두 불러오기", self.gather)
        menu.addSeparator()
        menu.addAction("⚙ 설정", self.open_settings)
        menu.addAction("종료", self.quit)

    def gather(self) -> None:
        """화면 밖이나 구석에 간 캐릭터를 신사 옆으로."""
        self.events.cancel_thief()
        self.events.cancel_play()
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
        self.state.last_seen = time.time()
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
    if "--restarted" in sys.argv:                       # 백업 되돌리기로 다시 켜짐: 앞의 것이 끝나길 잠깐 기다림
        time.sleep(1.5)
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
