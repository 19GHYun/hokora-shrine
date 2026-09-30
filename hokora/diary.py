# -*- coding: utf-8 -*-
"""자리 비운 동안의 새전(새전함)과 신사 일기, 신사가 커질 때 흩날리는 벚꽃잎."""
from __future__ import annotations

import math
import random
import time
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .state import SAISEN_BOX, GameState

MIN_AWAY = 10 * 60        # 이보다 짧게 비우면 일기는 쓰지 않음


def offline_income(s: GameState, seconds: float) -> int:
    """꺼져 있던 동안 새전함에 쌓인 새전 (새전함 단계만큼만, 최대 시간까지)."""
    cap_h, rate, _ = SAISEN_BOX[s.box_level]
    return int(s.income_per_min * min(seconds, cap_h * 3600) / 60 * rate)


def _hm(seconds: float) -> str:
    h, m = int(seconds // 3600), int(seconds % 3600 // 60)
    return f"{h}시간 {m}분" if h else f"{m}분"


def _night_overlap(start: float, end: float) -> bool:
    """start~end 사이에 밤(20시~5시)이 끼어 있었는지."""
    t = start
    while t < end:
        if not 5 <= datetime.fromtimestamp(t).hour < 20:
            return True
        t += 1800
    return False


def diary_lines(s: GameState, seconds: float, start: float, rng: random.Random | None = None) -> list[str]:
    """비운 시간에 어울리는 소소한 일들 (만난 친구들로만, 최대 5줄)."""
    rng = rng or random.Random()
    hours = max(seconds / 3600, 0.2)

    def n(per_hour: float) -> int:
        return max(1, int(rng.uniform(0.6, 1.4) * per_hour * hours))

    pool = {
        "reimu": [f"레이무가 마당을 {n(1.5)}번 쓸었다.", f"레이무가 새전함을 {n(2)}번 들여다봤다.",
                  "레이무가 툇마루에서 차를 마시며 졸았다."],
        "marisa": [f"마리사가 새전함 근처를 {n(1)}번 기웃거렸다.", "마리사가 버섯을 잔뜩 따 왔다."],
        "cirno": [f"치르노가 얼음을 {n(3)}번 던졌다.", "치르노가 개구리를 얼리려다 도망쳤다."],
        "sakuya": ["사쿠야가 시간을 멈추고 신사를 반짝반짝 닦아 두었다.", "사쿠야가 몰래 홍차를 끓여 두고 갔다."],
        "sanae": [f"사나에가 기적을 {n(1)}번 일으켰다.", "사나에가 레이무에게 포교 이야기를 늘어놓았다."],
        "remilia": ["레밀리아가 양산을 쓰고 신사를 둘러봤다."],
        "flandre": ["플랑드르가 뭔가를 부쉈다… 다행히 신사는 멀쩡하다.", "플랑드르가 언니를 졸졸 따라다녔다."],
    }
    if "remilia" in s.unlocked and _night_overlap(start, start + seconds):
        pool["remilia"].append("레밀리아가 밤새 신사 지붕 위에서 달을 봤다.")
    lines = [rng.choice(pool[k]) for k in s.unlocked if k in pool]
    rng.shuffle(lines)
    if hours >= 3 and "reimu" in s.unlocked:
        lines.append("모두 해가 질 때까지 푹 잤다.")
    return lines[:5]


class DiaryCard(QWidget):
    """신사 일기 카드. 누르면 닫히고, 가만히 두면 30초 뒤 저절로 닫힌다."""

    W = 330

    def __init__(self, title: str, lines: list[str], footer: str, sub: str = ""):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setCursor(Qt.PointingHandCursor)
        self.title, self.lines, self.footer, self.sub = title, lines, footer, sub
        self.f_sub = QFont("Malgun Gothic", 8)
        self.f_title = QFont("Malgun Gothic", 12)
        self.f_title.setBold(True)
        self.f_body = QFont("Malgun Gothic", 10)
        self.f_foot = QFont("Malgun Gothic", 11)
        self.f_foot.setBold(True)
        fm = QFontMetricsF(self.f_body)
        body_h = sum(fm.boundingRect(QRectF(0, 0, self.W - 56, 999), Qt.TextWordWrap, "· " + ln).height() + 4
                     for ln in lines)
        self.setFixedSize(self.W, int(66 + body_h + (40 if footer else 12) + (18 if sub else 0)))
        QTimer.singleShot(30_000, self.close)

    def show_above(self, cx: float, bottom: float) -> None:
        self.move(round(cx - self.width() / 2), round(bottom - self.height() - 8))
        self.show()

    def mousePressEvent(self, _e) -> None:
        self.close()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        p.setPen(QPen(QColor(200, 16, 46, 120), 1.2))
        p.setBrush(QColor(255, 250, 244, 250))
        p.drawPath(path)
        p.save()
        p.setClipPath(path)
        p.fillRect(QRectF(r.left(), r.top(), r.width(), 4), QColor("#C8102E"))
        p.restore()
        p.setFont(self.f_title)
        p.setPen(QColor("#B3122C"))
        p.drawText(QRectF(18, 14, self.W - 36, 24), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        p.setPen(QPen(QColor(200, 16, 46, 60), 1))
        p.drawLine(QPointF(18, 44), QPointF(self.W - 18, 44))
        p.setFont(self.f_body)
        p.setPen(QColor("#3A2A2E"))
        fm = QFontMetricsF(self.f_body)
        y = 54.0
        for ln in self.lines:
            rect = fm.boundingRect(QRectF(0, 0, self.W - 56, 999), Qt.TextWordWrap, "· " + ln)
            p.drawText(QRectF(24, y, self.W - 48, rect.height() + 2), Qt.TextWordWrap, "· " + ln)
            y += rect.height() + 4
        if self.footer:
            p.setFont(self.f_foot)
            p.setPen(QColor("#B8860B"))
            p.drawText(QRectF(18, y + 6, self.W - 36, 24), Qt.AlignCenter, self.footer)
        if self.sub:
            p.setFont(self.f_sub)
            p.setPen(QColor("#8C7479"))
            p.drawText(QRectF(18, y + 30, self.W - 36, 16), Qt.AlignCenter, self.sub)
        p.end()


class PetalBurst(QWidget):
    """신사가 커질 때: 신사 위로 벚꽃잎이 몇 초 동안 흩날림 (클릭은 통과)."""

    def __init__(self, cx: float, ground: float, width: float = 520, height: float = 420, seconds: float = 5.0):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(int(width), int(height))
        self.move(round(cx - width / 2), round(ground - height))
        self.start = time.monotonic()
        self.seconds = seconds
        rng = random.Random()
        # (나타나는 시각, 시작 x, 떨어지는 속도, 흔들림 폭, 흔들림 위상, 크기, 회전 속도)
        self.petals = [(rng.uniform(0, seconds * 0.6), rng.uniform(0, width), rng.uniform(55, 110),
                        rng.uniform(10, 30), rng.uniform(0, 6.28), rng.uniform(5, 9), rng.uniform(-3, 3))
                       for _ in range(46)]
        self.timer = QTimer(self, timeout=self._tick, interval=33)
        self.timer.start()

    def _tick(self) -> None:
        if time.monotonic() - self.start > self.seconds + 3:
            self.close()
        else:
            self.update()

    def paintEvent(self, _e) -> None:
        t = time.monotonic() - self.start
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        for born, x0, speed, sway, phase, size, spin in self.petals:
            age = t - born
            if age < 0:
                continue
            y = -10 + age * speed
            if y > self.height():
                continue
            x = x0 + math.sin(age * 1.8 + phase) * sway
            fade = max(0.0, min(1.0, (self.height() - y) / 60))
            p.save()
            p.translate(x, y)
            p.rotate(math.degrees(age * spin))
            petal = QPainterPath()
            petal.moveTo(0, -size)
            petal.cubicTo(size * 0.9, -size * 0.6, size * 0.6, size * 0.8, 0, size * 0.55)
            petal.cubicTo(-size * 0.6, size * 0.8, -size * 0.9, -size * 0.6, 0, -size)
            p.setBrush(QColor(255, 183, 206, int(235 * fade)))
            p.drawPath(petal)
            p.restore()
        p.end()


def away_card(s: GameState, seconds: float, start: float, earned: int, offline: bool) -> DiaryCard:
    title = f"📔 신사 일기 — {_hm(seconds)} 동안"
    lines = diary_lines(s, seconds, start) or ["모두 얌전히 신사를 지켰다."]
    sub = ""
    if offline:
        cap_h, rate, _ = SAISEN_BOX[s.box_level]
        footer = f"새전함에 새전 +{earned:,}"
        sub = f"새전함 Lv.{s.box_level} · 최대 {cap_h}시간 · 수입의 {int(rate * 100)}%"
    else:
        footer = f"그동안 모은 새전 +{earned:,}" if earned else ""
    return DiaryCard(title, lines, footer, sub)
