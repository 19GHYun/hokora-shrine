# -*- coding: utf-8 -*-
"""Hokora 본체: 캐릭터·신사 창을 띄우고 시간·새전·저장을 관리한다."""
from __future__ import annotations

import getpass
import logging
import os
import random
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QObject, QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import __version__, winutil
from .pet import PetWindow
from .render import CHARACTERS, Pose, draw_character
from .shrine import ShrineWindow
from .state import APP_NAME, LOG_DIR, PAT_REWARD, SaveStore

log = logging.getLogger("Hokora")
ENTRY_SCRIPT = Path(sys.argv[0]).resolve()
INSTANCE_SERVER = f"{APP_NAME}-{getpass.getuser()}"
FPS_BUSY = 30            # 던지거나 잡고 있을 때
FPS_CALM = 15            # 평소 (걷기·가만히) — CPU 를 아끼려고
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
        # 리본 끝(설계 y≈-10)부터 턱(y≈78)까지가 아이콘을 채우게: 88 단위 = size
        scale = size / 88
        draw_character(p, CHARACTERS["reimu"], Pose(kind="idle", t=0.3),
                       QRectF((size - 100 * scale) / 2, 10 * scale, 100 * scale, 120 * scale))
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
        self.shrine = ShrineWindow(self, self.left + self.state.shrine_x * (self.right - self.left),
                                   self.state.shrine_level)
        self.shrine.set_saisen(self.state.saisen)
        keys = list(CHARACTERS) if os.environ.get("HOKORA_ALL") == "1" else self.state.unlocked
        for key in keys:
            self._spawn(key)

        self.clock = QElapsedTimer()
        self.clock.start()
        self.tick_timer = QTimer(self, timeout=self._tick, interval=1000 // FPS_CALM)
        self.income_timer = QTimer(self, timeout=self._income, interval=INCOME_EVERY * 1000)
        self.save_timer = QTimer(self, timeout=self.save, interval=SAVE_EVERY * 1000)
        self.watch_timer = QTimer(self, timeout=self._watch, interval=1500)

        screen = app.primaryScreen()
        screen.availableGeometryChanged.connect(self._on_screen_changed)
        self.tray = self._make_tray()

    # ── 화면 ──
    def _update_bounds(self) -> None:
        g = self.app.primaryScreen().availableGeometry()
        self.left, self.right = float(g.left()), float(g.right() + 1)
        self.top = float(g.top())
        self.ground_y = float(g.bottom() + 1)   # 작업표시줄 윗변

    def _on_screen_changed(self, *_):
        self._update_bounds()
        self.shrine.pos_x = min(max(self.shrine.pos_x, self.left + 60), self.right - 60)
        self.shrine._place()
        log.info("화면 영역 변경 → 바닥 y=%s", self.ground_y)

    def _spawn(self, key: str) -> None:
        x = random.uniform(self.left + 80, self.right - 80)
        pet = PetWindow(CHARACTERS[key], self, x)
        self.pets.append(pet)

    def windows(self):
        return [self.shrine, *self.pets]

    def start(self) -> None:
        for w in self.windows():
            w.show()
        self.tick_timer.start()
        self.income_timer.start()
        self.save_timer.start()
        self.watch_timer.start()
        log.info("시작 — 캐릭터 %d, 신사 %s", len(self.pets), self.state.stage_name)

    # ── 시간 ──
    def _tick(self) -> None:
        dt = min(self.clock.restart() / 1000.0, 0.1)   # 잠자기·절전에서 깨어나도 순간이동 안 하게
        if self.hidden_for_fullscreen:
            return
        self.state.runtime_sec += dt
        for pet in self.pets:
            pet.step(dt)
        self.shrine.step(dt)
        fps = FPS_BUSY if any(p.busy for p in self.pets) else FPS_CALM
        if self.tick_timer.interval() != 1000 // fps:
            self.tick_timer.setInterval(1000 // fps)

    def _income(self) -> None:
        s = self.state
        s.income_carry += s.income_per_min * INCOME_EVERY / 60
        gained = int(s.income_carry)
        if gained:
            s.income_carry -= gained
            s.add_saisen(gained)
            self.shrine.set_saisen(s.saisen)
            if not self.hidden_for_fullscreen:
                self.shrine.pop(f"+{gained}")

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

    # ── 상호작용 (PetWindow / ShrineWindow 가 부름) ──
    def on_pat(self, pet: PetWindow) -> None:
        if pet.pat():
            self.state.pats += 1
            self.state.add_saisen(PAT_REWARD)
            self.shrine.set_saisen(self.state.saisen)
            self.shrine.pop(f"+{PAT_REWARD}")

    def on_shrine_moved(self, x: float) -> None:
        self.state.shrine_x = (x - self.left) / max(1.0, self.right - self.left)

    def on_shrine_clicked(self, global_pos: QPoint) -> None:
        self.on_context_menu(global_pos)

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
        menu.addAction("모두 불러오기", self.gather)
        if winutil.IS_WIN:
            a = QAction("Windows 시작 시 자동 실행", menu, checkable=True)
            a.setChecked(winutil.get_autostart() is not None)
            a.toggled.connect(lambda on: winutil.set_autostart(on, ENTRY_SCRIPT))
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction("종료", self.quit)

    def gather(self) -> None:
        """화면 밖이나 구석에 간 캐릭터를 신사 옆으로."""
        for pet in self.pets:
            pet.pos_x = min(max(self.shrine.pos_x + random.uniform(-120, 120), self.left + 40), self.right - 40)
            pet.pos_y, pet.vx, pet.vy, pet.state = self.ground_y - 200, 0.0, 0.0, "fall"
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
