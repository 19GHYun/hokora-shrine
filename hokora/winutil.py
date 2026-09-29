# -*- coding: utf-8 -*-
"""Windows 전용 도우미. 다른 OS 에서는 조용히 아무것도 안 한다."""
from __future__ import annotations

import ctypes
import logging
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("Hokora.win")
IS_WIN = sys.platform == "win32"

_HWND_TOPMOST = -1
_SWP_NOSIZE, _SWP_NOMOVE, _SWP_NOACTIVATE = 0x1, 0x2, 0x10


def set_app_user_model_id(app_id: str) -> None:
    if IS_WIN:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except (AttributeError, OSError):
            log.warning("AppUserModelID 설정 실패", exc_info=True)


def keep_topmost(hwnd: int) -> None:
    """작업표시줄을 누르면 작업표시줄이 위로 올라오므로 가끔 다시 맨 위로."""
    if IS_WIN:
        ctypes.windll.user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(_HWND_TOPMOST), 0, 0, 0, 0,
                                          _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE)


def fullscreen_app_running() -> bool:
    """전체화면 게임·영상·발표 중이면 True (Windows 가 알림을 멈추는 조건과 같음)."""
    if not IS_WIN:
        return False
    state = ctypes.c_int(0)
    try:
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
            return False
    except (AttributeError, OSError):
        return False
    # 2 = QUNS_BUSY(전체화면 앱), 3 = QUNS_RUNNING_D3D_FULL_SCREEN, 4 = QUNS_PRESENTATION_MODE
    return state.value in (2, 3, 4)


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def idle_seconds() -> float:
    """키보드·마우스를 마지막으로 쓴 뒤 지난 시간(초)."""
    if not IS_WIN:
        return 0.0
    info = _LastInputInfo()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    now = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
    return ((now - info.dwTime) & 0xFFFFFFFF) / 1000.0     # 49일마다 한 바퀴 도는 값이라 뺄셈을 32비트로


# ── 창 위를 걸어 다니기: 열려 있는 창들의 윗변 중 보이는 부분 = 발판 ──
@dataclass
class Platform:
    hwnd: int
    x1: float          # 발판(윗변 중 가려지지 않은 구간) 왼쪽·오른쪽 끝
    x2: float
    y: float           # 윗변 높이
    win_left: float    # 창 전체의 왼쪽 끝 — 창을 끌어 옮기면 캐릭터도 같이 옮기려고


_SKIP_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW",
                 "Windows.UI.Core.CoreWindow", "NotifyIconOverflowWindow"}
_DWMWA_EXTENDED_FRAME_BOUNDS, _DWMWA_CLOAKED = 9, 14
_WS_EX_TOOLWINDOW = 0x80


@dataclass
class Area:
    """모니터 하나. geo·avail 은 Qt 논리 좌표 (왼, 위, 오른, 아래 — 오른·아래는 끝 다음 칸),
    phys 는 Windows 물리 픽셀 좌표. 모니터마다 배율이 달라 창 위치를 바꿀 때 모니터별로 계산해야 한다."""
    geo: tuple[float, float, float, float]
    avail: tuple[float, float, float, float]
    dpr: float
    phys: tuple[int, int, int, int]

    def contains_phys(self, px: float, py: float) -> bool:
        return self.phys[0] <= px < self.phys[2] and self.phys[1] <= py < self.phys[3]

    def to_logical(self, px: float, py: float) -> tuple[float, float]:
        return self.geo[0] + (px - self.phys[0]) / self.dpr, self.geo[1] + (py - self.phys[1]) / self.dpr


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def monitor_rects() -> list[tuple[int, int, int, int]]:
    """연결된 모니터들의 물리 픽셀 영역."""
    if not IS_WIN:
        return []
    rects: list[tuple[int, int, int, int]] = []
    user32 = ctypes.windll.user32

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    def collect(hmon, _hdc, _rect, _lp):
        info = _MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(ctypes.c_void_p(hmon), ctypes.byref(info)):
            r = info.rcMonitor
            rects.append((r.left, r.top, r.right, r.bottom))
        return 1

    user32.EnumDisplayMonitors(None, None, collect, 0)
    return rects


def window_platforms(areas: list[Area], min_len: float = 60.0) -> list[Platform]:
    """화면에 보이는 일반 창들의 윗변을 발판으로. 좌표는 Qt 논리 픽셀.

    최대화 창처럼 윗변이 모니터 맨 위에 붙은 창, 작은 창, 도구 창, 이 프로그램의 창은 제외.
    윗변이 다른 창에 가려진 부분도 제외. 창이 있는 모니터의 배율로 좌표를 바꾼다.
    """
    if not IS_WIN or not areas:
        return []
    user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
    my_pid = os.getpid()
    windows: list[tuple[int, tuple[float, float, float, float], bool, Area]] = []  # 위쪽 창부터 (z 순서)

    @ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)
    def collect(hwnd, _lp):
        try:
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return 1
            cloaked = ctypes.c_int(0)
            dwm.DwmGetWindowAttribute(hwnd, _DWMWA_CLOAKED, ctypes.byref(cloaked), 4)
            if cloaked.value:
                return 1
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == my_pid:
                return 1
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            if cls.value in _SKIP_CLASSES:
                return 1
            r = wintypes.RECT()
            if dwm.DwmGetWindowAttribute(hwnd, _DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)):
                user32.GetWindowRect(hwnd, ctypes.byref(r))
            if r.right - r.left < 4 or r.bottom - r.top < 4:
                return 1
            # 창 윗변 가운데가 있는 모니터 기준으로 좌표 변환
            cx, cy = (r.left + r.right) / 2, r.top + 1
            area = next((a for a in areas if a.contains_phys(cx, cy)), None)
            if area is None:
                return 1
            l, t = area.to_logical(r.left, r.top)
            rr, b = area.to_logical(r.right, r.bottom)
            ex = user32.GetWindowLongW(hwnd, -20)
            # 발판이 될 수 있는 창: 제목이 있는 보통 크기의 일반 창
            standable = (not ex & _WS_EX_TOOLWINDOW and user32.GetWindowTextLengthW(hwnd) > 0
                         and rr - l >= 120 and b - t >= 80)
            windows.append((int(hwnd), (l, t, rr, b), standable, area))
        except OSError:
            pass
        return 1

    user32.EnumWindows(collect, 0)

    platforms: list[Platform] = []
    for i, (hwnd, (l, t, r, b), standable, area) in enumerate(windows):
        al, at, ar, ab = area.avail
        if not standable or t <= at + 40 or t >= ab - 40:   # 최대화 창·화면 밖·바닥에 붙은 창
            continue
        segments = [(max(l, al), min(r, ar))]
        for _, (ol, ot, orr, ob), _, _ in windows[:i]:     # 이 창보다 위에 있는 창들이 가린 부분 빼기
            if ot <= t <= ob:
                segments = [part for s1, s2 in segments
                            for part in ((s1, min(s2, ol)), (max(s1, orr), s2)) if part[1] - part[0] > 0]
        platforms += [Platform(hwnd, s1, s2, t, l) for s1, s2 in segments if s2 - s1 >= min_len]
    return platforms


# ── Windows 시작 시 자동 실행 (HKCU Run) ──
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE = "Hokora"
AUTOSTART_ARG = "--autostart"


def autostart_command(script: Path) -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {AUTOSTART_ARG}'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return f'"{pythonw if pythonw.exists() else exe}" "{script}" {AUTOSTART_ARG}'


def get_autostart() -> str | None:
    if not IS_WIN:
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            return winreg.QueryValueEx(k, _RUN_VALUE)[0]
    except FileNotFoundError:
        return None
    except OSError:
        log.warning("자동 실행 설정 읽기 실패", exc_info=True)
        return None


def set_autostart(enabled: bool, script: Path) -> bool:
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, _RUN_VALUE, 0, winreg.REG_SZ, autostart_command(script))
            else:
                try:
                    winreg.DeleteValue(k, _RUN_VALUE)
                except FileNotFoundError:
                    pass
        log.info("자동 실행 %s", "등록" if enabled else "해제")
        return True
    except OSError:
        log.exception("자동 실행 설정 실패")
        return False
