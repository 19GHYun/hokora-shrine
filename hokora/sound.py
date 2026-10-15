# -*- coding: utf-8 -*-
"""소리: 손님 방울의 "딸랑딸랑" (신사 방울 스즈 소리를 코드로 합성).

소리 파일은 처음 한 번 만들어 데이터 폴더(sounds/suzu.wav)에 두고, Windows 기본 소리 재생(winsound)으로
비동기 재생한다. HOKORA_MUTE=1 이면 아무 소리도 내지 않는다 (시험용).
"""
from __future__ import annotations

import logging
import math
import os
import random
import wave
from array import array
from pathlib import Path

try:                                  # Windows 기본 소리 재생 (맨 위에서 불러야 exe 에도 확실히 들어감)
    import winsound
except ImportError:
    winsound = None

log = logging.getLogger("Hokora.sound")
RATE = 22050
LENGTH = 1.5                      # 초
STRIKES = (0.0, 0.10, 0.36, 0.47)  # 딸랑 · 딸랑 (두 번씩 두 묶음)
PARTIALS = ((1.0, 1.0), (2.76, 0.55), (5.40, 0.30), (8.93, 0.16))   # 종소리 배음 (비율, 세기)
BASE_HZ = 2250.0
PEAK = 0.42                       # 최대 음량 (0~1)
_path: Path | None = None


def suzu_samples(seed: int = 7) -> array:
    """방울 소리 (16비트 모노)."""
    rng = random.Random(seed)
    n = int(RATE * LENGTH)
    buf = [0.0] * n
    for k, t0 in enumerate(STRIKES):
        f0 = BASE_HZ * (1 + rng.uniform(-0.04, 0.04))
        amp = 1.0 if k % 2 == 0 else 0.75
        start = int(t0 * RATE)
        for i in range(start, min(n, start + int(RATE * 0.004))):     # 부딪히는 순간의 짤랑
            buf[i] += amp * 0.25 * rng.uniform(-1, 1)
        for ratio, a in PARTIALS:
            f = f0 * ratio
            if f >= RATE / 2:
                continue
            w = 2 * math.pi * f / RATE
            decay = 5.0 + ratio * 3.5                                    # 높은 배음일수록 빨리 사라짐
            for j in range(n - start):
                e = math.exp(-decay * j / RATE)
                if e < 0.002:
                    break
                buf[start + j] += amp * a * e * math.sin(w * j)
    peak = max(abs(x) for x in buf) or 1.0
    k = PEAK * 32767 / peak
    return array("h", (int(x * k) for x in buf))


def suzu_path() -> Path:
    """방울 소리 파일 (없으면 만듦)."""
    global _path
    if _path is not None and _path.exists():
        return _path
    from .state import DATA_DIR
    path = DATA_DIR / "sounds" / "suzu.wav"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(suzu_samples().tobytes())
    _path = path
    return path


def play_suzu() -> bool:
    """방울 소리를 비동기로 (끝날 때까지 기다리지 않음). 냈으면 True."""
    if os.environ.get("HOKORA_MUTE") == "1" or winsound is None:
        return False
    try:
        winsound.PlaySound(str(suzu_path()), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        return True
    except (OSError, RuntimeError):
        log.warning("방울 소리 재생 실패", exc_info=True)
        return False
