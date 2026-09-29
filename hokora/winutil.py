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


def window_platforms(dpr: float, area: tuple[float, float, float, float],
                     min_len: float = 60.0) -> list[Platform]:
    """화면에 보이는 일반 창들의 윗변을 발판으로. 좌표는 Qt 논리 픽셀.

    area = (왼쪽, 위, 오른쪽, 아래) 작업 영역. 최대화 창처럼 윗변이 화면 맨 위에 붙은 창,
    작은 창, 도구 창, 이 프로그램의 창은 제외. 윗변이 다른 창에 가려진 부분도 제외.
    """
    if not IS_WIN:
        return []
    user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
    my_pid = os.getpid()
    left, top, right, bottom = area
    windows: list[tuple[int, tuple[float, float, float, float], bool]] = []  # 위쪽 창부터 (z 순서)

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def collect(hwnd, _lp):
        try:
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            cloaked = ctypes.c_int(0)
            dwm.DwmGetWindowAttribute(hwnd, _DWMWA_CLOAKED, ctypes.byref(cloaked), 4)
            if cloaked.value:
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == my_pid:
                return True
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            if cls.value in _SKIP_CLASSES:
                return True
            r = wintypes.RECT()
            if dwm.DwmGetWindowAttribute(hwnd, _DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)):
                user32.GetWindowRect(hwnd, ctypes.byref(r))
            rect = (r.left / dpr, r.top / dpr, r.right / dpr, r.bottom / dpr)
            if rect[2] - rect[0] < 4 or rect[3] - rect[1] < 4:
                return True
            ex = user32.GetWindowLongW(hwnd, -20)
            # 발판이 될 수 있는 창: 제목이 있는 보통 크기의 일반 창
            standable = (not ex & _WS_EX_TOOLWINDOW and user32.GetWindowTextLengthW(hwnd) > 0
                         and rect[2] - rect[0] >= 120 and rect[3] - rect[1] >= 80)
            windows.append((int(hwnd), rect, standable))
        except OSError:
            pass
        return True

    user32.EnumWindows(collect, 0)

    platforms: list[Platform] = []
    for i, (hwnd, (l, t, r, b), standable) in enumerate(windows):
        if not standable or t <= top + 40 or t >= bottom - 40:   # 최대화 창·화면 밖·바닥에 붙은 창
            continue
        segments = [(max(l, left), min(r, right))]
        for _, (ol, ot, orr, ob), _ in windows[:i]:              # 이 창보다 위에 있는 창들이 가린 부분 빼기
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
