# -*- coding: utf-8 -*-
"""Windows 전용 도우미. 다른 OS 에서는 조용히 아무것도 안 한다."""
from __future__ import annotations

import ctypes
import logging
import sys
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
