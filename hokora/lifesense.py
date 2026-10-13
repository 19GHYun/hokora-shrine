# -*- coding: utf-8 -*-
"""생활 속 친구: 시계 친구(정각 팻말)와 PC 상태 반응(배터리·CPU·늦은 밤·휴지통).

PC 상태는 읽기만 하고 아무것도 바꾸지 않는다 (휴지통도 알려 주기만).
"""
from __future__ import annotations

import random
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import winutil

BATTERY_LOW = 20
CPU_HOT = 85.0
RECYCLE_ITEMS = 200
RECYCLE_BYTES = 2 * 1024 ** 3
HOUR_LINES = {
    0: "자정이야! 이제 자야지~", 1: "새벽 1시… 아직 안 자?", 6: "6시, 좋은 아침~", 7: "7시! 일어날 시간이야~",
    8: "8시, 오늘도 힘내자!", 9: "9시! 시작해 볼까?", 12: "12시! 점심 먹자~", 13: "1시, 배부르니 졸리다…",
    15: "3시, 간식 시간이야~", 18: "6시! 퇴근 시간이다~", 19: "7시, 저녁 먹었어?", 21: "9시, 오늘 하루 수고했어",
    22: "10시야. 슬슬 쉬자", 23: "11시, 내일을 위해 자자~",
}
CHAR_HOUR = {  # 이 친구가 알려 주면 이 말로
    ("remilia", 0): "자정이야… 밤은 지금부터지.", ("flandre", 0): "자정! 놀 시간이다~!",
    ("cirno", 12): "12시! 빙수 먹자!", ("sakuya", 15): "3시, 홍차 시간이에요.", ("marisa", 18): "6시다제! 퇴근이다제!",
    ("reimu", 15): "3시, 차 한잔 하자~", ("youmu", 12): "12시, 유유코 님 점심 차려 드려야…",
}


def hour_text(h: int) -> str:
    """팻말 글: 자정 / 정오 / 오전 9시 / 오후 3시."""
    if h == 0:
        return "자정"
    if h == 12:
        return "정오"
    return f"오전 {h}시" if h < 12 else f"오후 {h - 12}시"


def hour_line(h: int, key: str) -> str:
    return CHAR_HOUR.get((key, h)) or HOUR_LINES.get(h) or f"{h % 12 or 12}시야~"


class HourSign(QWidget):
    """친구 머리 위로 드는 나무 팻말 ("3시"). 친구를 따라다니다가 몇 초 뒤 사라짐. 클릭은 통과."""

    W, H = 92, 74

    def __init__(self, pet, text: str, seconds: float = 6.5):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFixedSize(self.W, self.H)
        self.pet, self.text = pet, text
        self.until = time.monotonic() + seconds
        self.timer = QTimer(self, timeout=self._tick, interval=40)
        self.timer.start()
        self._tick()

    def _tick(self) -> None:
        if time.monotonic() > self.until or not self.pet.isVisible():
            self.close()
            return
        k = getattr(self.pet.world, "scale", 1.0)
        self.move(round(self.pet.pos_x - self.W / 2 + 14 * self.pet.facing),
                  round(self.pet.pos_y - 68 * k - self.H + 14))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(90, 60, 36), 1.4))
        p.setBrush(QColor(150, 104, 62))
        p.drawRect(QRectF(self.W / 2 - 3, 40, 6, self.H - 42))          # 막대
        board = QRectF(6, 4, self.W - 12, 40)
        g = QLinearGradient(0, board.top(), 0, board.bottom())
        g.setColorAt(0, QColor("#F4DDB0"))
        g.setColorAt(1, QColor("#DDBA82"))
        p.setBrush(g)
        p.setPen(QPen(QColor(110, 72, 40), 2))
        p.drawRoundedRect(board, 6, 6)
        f = QFont("Malgun Gothic", 12 if len(self.text) > 3 else 15)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#7A3B1C"))
        p.drawText(board, Qt.AlignCenter, self.text)
        p.end()


class CpuMeter:
    """CPU 사용률: 부를 때마다 지난번과의 차이로 계산 (처음엔 None)."""

    def __init__(self):
        self.last = winutil.cpu_times()

    def sample(self) -> float | None:
        now = winutil.cpu_times()
        if now is None or self.last is None:
            self.last = now
            return None
        (i0, t0), (i1, t1) = self.last, now
        self.last = now
        busy = (t1 - t0) - (i1 - i0)
        return max(0.0, min(100.0, 100 * busy / max(1, t1 - t0)))


def recycle_full(info: tuple[int, int] | None) -> bool:
    return info is not None and (info[0] >= RECYCLE_ITEMS or info[1] >= RECYCLE_BYTES)


def fmt_bytes(n: int) -> str:
    return f"{n / 1024 ** 3:.1f}GB" if n >= 1024 ** 3 else f"{n / 1024 ** 2:.0f}MB"


LOW_BATTERY = ["배터리가 얼마 없어… 졸려…", "배고파… 충전기 꽂아 줘~", "배터리 {p}%… 눈이 감긴다…"]
CHARGING = ["충전이다! 기운 난다~!", "밥이다~! 고마워!", "살았다… 충전 최고!"]
CPU_HOT_LINES = ["컴퓨터가 뜨거워! 부채질~", "으아, 열기가 올라온다!", "컴퓨터가 열심히 일하고 있나 봐!"]
LATE_LINES = ["벌써 {h}시야… 이제 자자", "{h}시라니! 내일 졸려~", "늦었어… 같이 자러 가자"]
RECYCLE_LINES = ["휴지통이 꽉 찼어! 청소하자~", "휴지통이 넘치겠어! 비워 주세요~"]


def pick(lines: list[str], **kw) -> str:
    return random.choice(lines).format(**kw)
