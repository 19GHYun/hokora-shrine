# -*- coding: utf-8 -*-
"""연말 결산 (연말 결산 앱들 오마주): 한 해 동안 신사에서 있었던 일을 카드 몇 장으로 넘겨 본다.

- 해마다 처음 켤 때의 기록(year_base)을 남겨 두고, 지금 기록과의 차이가 '올해'.
  해가 바뀌면 지난해 결산(year_last)을 만들어 두고 새로 센다.
- 12월엔 올해 지금까지, 1월엔 지난해 것을 메뉴에서 볼 수 있다. 12월 20일부터 한 번 저절로 보여 주고,
  12월에 못 봤으면 1월에 처음 켤 때 지난해 것을 보여 준다.
- 마지막 장에서 한 장짜리 그림(1200×675)으로 저장 + 클립보드.
HOKORA_TODAY=YYYY-MM-DD 로 날짜를 바꿔 시험할 수 있다 (이 모듈과 newyear.py 의 행사 날짜만).
"""
from __future__ import annotations

import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .state import GameState

AUTO_FROM = 20            # 12월 이날부터 한 번 저절로
SLIDE_SECONDS = 7.0       # 가만히 두면 다음 장으로

# 숫자 카드에 나오는 것 (나오는 차례대로, 올해 0 이면 뺌): 키 → (그림 문자, 이름, 단위)
STATS: dict[str, tuple[str, str, str]] = {
    "omikuji": ("🎋", "뽑은 오미쿠지", "번"),
    "guests": ("🎐", "다녀간 손님", "번"),
    "daily": ("📜", "들어준 부탁", "개"),
    "attend": ("📅", "출석한 날", "일"),
    "letters": ("💌", "받은 편지", "통"),
    "incidents": ("⚔", "해결한 이변", "번"),
    "fish": ("🎣", "낚은 물고기", "마리"),
    "expedition": ("🗺", "다녀온 원정", "번"),
    "thief": ("💰", "붙잡은 새전 도둑", "번"),
    "fireworks": ("🎆", "쏘아 올린 불꽃", "번"),
    "festivals": ("🏮", "연 예대제", "번"),
    "sengu": ("🏯", "식년천궁", "번"),
    "torii": ("⛩", "세운 도리이", "개"),
    "photos": ("📸", "찍은 사진", "장"),
    "dodge": ("🎯", "탄막 버티기", "번"),
    "race": ("🏁", "요정 달리기", "번"),
    "janken": ("✊", "가위바위보", "판"),
    "hide": ("🙈", "숨바꼭질로 찾음", "번"),
    "ufo": ("🛸", "UFO 격추", "번"),
    "gifts": ("🎁", "준 선물", "개"),
    "clean": ("🧹", "치운 먼지", "개"),
}


def today() -> date:
    forced = os.environ.get("HOKORA_TODAY", "")
    if forced:
        try:
            return date.fromisoformat(forced)
        except ValueError:
            pass
    return date.today()


def counters(s: GameState) -> dict[str, int]:
    """지금까지의 누적 기록."""
    return {
        "saisen": s.saisen_total, "pats": s.pats, "minutes": int(s.runtime_sec // 60),
        "omikuji": s.omikuji_count, "guests": sum(s.guest_visits.values()), "thief": s.thief_caught,
        "fish": s.fish_caught, "expedition": s.expedition_done, "daily": s.daily_done,
        "incidents": sum(s.incidents_solved.values()), "letters": sum(len(v) for v in s.letters.values()),
        "photos": s.photos, "fireworks": s.fireworks, "sengu": s.sengu, "festivals": s.festivals,
        "attend": s.attend_days, "dodge": s.dodge_clears, "race": s.race_count, "janken": s.janken_games,
        "hide": s.hide_found, "ufo": s.ufo_shot, "gifts": s.gifts_given, "torii": s.torii, "clean": s.clean_spots,
    }


def snapshot(s: GameState, year: int, since: str) -> dict:
    return {"year": year, "since": since, "v": counters(s), "guests": dict(s.guest_visits),
            "aff": dict(s.affection)}


def _created(s: GameState, d: date) -> str:
    try:
        return min(datetime.fromisoformat(s.created).date(), d).isoformat()
    except (TypeError, ValueError):
        return d.isoformat()


def ensure_base(s: GameState, d: date | None = None) -> None:
    """올해 시작 기록이 없으면 만든다. 처음엔 모든 기록이 0 에서 시작했으므로 0 을 기준으로 (처음 만난 날부터)."""
    d = d or today()
    if not isinstance(s.year_base, dict) or not isinstance(s.year_base.get("year"), int):
        s.year_base = {"year": d.year, "since": _created(s, d), "v": {}, "guests": {}, "aff": {}}


def rollover(s: GameState, d: date | None = None) -> bool:
    """해가 바뀌었으면 지난해 결산을 만들어 두고 올해 기록을 새로 시작 (바뀌었으면 True)."""
    d = d or today()
    ensure_base(s, d)
    base = s.year_base
    if base["year"] >= d.year:
        return False
    s.year_last = summarize(s, base, date(base["year"], 12, 31))
    s.year_base = snapshot(s, d.year, date(d.year, 1, 1).isoformat())
    return True


def summarize(s: GameState, base: dict, until: date) -> dict:
    now = counters(s)
    v0 = base.get("v", {})
    diff = {k: max(0, n - int(v0.get(k, 0))) for k, n in now.items()}
    aff0 = base.get("aff", {})
    friends = [k for k in s.unlocked]
    best, best_gain = "", 0
    if friends:
        best = max(friends, key=lambda k: (s.affection.get(k, 0) - aff0.get(k, 0), s.affection.get(k, 0)))
        best_gain = max(0, s.affection.get(best, 0) - aff0.get(best, 0))
    g0 = base.get("guests", {})
    gains = {k: n - g0.get(k, 0) for k, n in s.guest_visits.items()}
    guest = max(gains, key=lambda k: gains[k]) if gains and max(gains.values()) > 0 else ""
    since = base.get("since") or date(base["year"], 1, 1).isoformat()
    try:
        days = max(1, (until - date.fromisoformat(since)).days + 1)
    except ValueError:
        days = 1
    from . import sengu
    return {"year": base["year"], "since": since, "until": until.isoformat(), "days": days, "v": diff,
            "best": best, "best_gain": best_gain, "guest": guest, "guest_n": gains.get(guest, 0),
            "friends": len(s.unlocked), "stage": s.stage_name, "gen": sengu.generation(s)}


def current(s: GameState, d: date | None = None) -> dict | None:
    """지금 볼 수 있는 결산 (12월: 올해 지금까지, 1월: 지난해). 그 밖의 달은 None."""
    d = d or today()
    if d.month == 12:
        ensure_base(s, d)
        if s.year_base["year"] == d.year:
            return summarize(s, s.year_base, d)
    if d.month == 1 and isinstance(s.year_last, dict) and s.year_last.get("year") == d.year - 1:
        return s.year_last
    return None


def auto_due(s: GameState, d: date | None = None) -> bool:
    """저절로 한 번 보여 줄 때인지."""
    d = d or today()
    data = current(s, d)
    if data is None or s.wrapped_seen >= data["year"]:
        return False
    return d.month == 1 or d.day >= AUTO_FROM


def top_stats(data: dict, n: int) -> list[tuple[str, str, str, int]]:
    """(그림 문자, 이름, 단위, 올해 수) — 0 은 빼고 STATS 차례대로 n 개."""
    v = data.get("v", {})
    return [(icon, name, unit, v[k]) for k, (icon, name, unit) in STATS.items() if v.get(k, 0) > 0][:n]


def _range(data: dict) -> str:
    try:
        a, b = date.fromisoformat(data["since"]), date.fromisoformat(data["until"])
        return f"{a.year}. {a.month}. {a.day}. ~ {b.month}. {b.day}."
    except (KeyError, ValueError):
        return ""


def _hours(data: dict) -> str:
    m = data["v"].get("minutes", 0)
    return f"{m // 60:,}시간" if m >= 60 else f"{m}분"


def _hearts(level: int) -> str:
    from .affection import MAX_HEARTS
    return "♥" * level + "♡" * (MAX_HEARTS - level)


# ── 한 장씩 넘겨 보는 카드 ──
SLIDES = ("intro", "saisen", "friend", "guest", "numbers", "end")
PALETTE = {   # 장마다 (위, 아래) 바탕색, 글자색
    "intro": ("#B3122C", "#E0475E", "#FFFFFF"),
    "saisen": ("#C8901A", "#F2C94C", "#3A2A0E"),
    "friend": ("#E86A92", "#F8B7C9", "#FFFFFF"),
    "guest": ("#27306B", "#4C5AA8", "#FFFFFF"),
    "numbers": ("#FFF5E6", "#FBE3E7", "#3A2A2E"),
    "end": ("#8E0F25", "#C8102E", "#FFFFFF"),
}


class WrappedCard(QWidget):
    """결산 카드. 누르면 다음 장, 오른쪽 클릭이나 ✕ 는 닫기. 마지막 장의 단추로 그림 저장."""

    W, H = 360, 500

    def __init__(self, s: GameState, data: dict, on_save: Callable[[dict], None]):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.W, self.H)
        self.s, self.data, self.on_save = s, data, on_save
        self.i = 0
        self.saved = False
        self.shown_at = time.monotonic()
        self.slide_at = self.shown_at
        self.timer = QTimer(self, timeout=self._tick, interval=50)
        self.save_rect = QRectF(40, self.H - 132, self.W - 80, 46)
        self.close_rect = QRectF(self.W - 40, 14, 26, 26)
        self._pics: dict[tuple[str, int], object] = {}

    @property
    def slide(self) -> str:
        return SLIDES[self.i]

    def show_above(self, cx: float, bottom: float) -> None:
        self.move(round(cx - self.width() / 2), round(bottom - self.height() - 8))
        self.show()
        self.shown_at = self.slide_at = time.monotonic()
        self.timer.start()

    def next(self) -> None:
        if self.i < len(SLIDES) - 1:
            self.i += 1
            self.slide_at = time.monotonic()
            self.update()

    def _tick(self) -> None:
        now = time.monotonic()
        if self.slide != "end" and now - self.slide_at >= SLIDE_SECONDS:
            self.next()
        if now - self.slide_at > 180:                   # 마지막 장에서 오래 두면 닫힘
            self.close()
            return
        self.update()

    def mousePressEvent(self, e) -> None:
        pos = e.position()
        if e.button() == Qt.RightButton or self.close_rect.contains(pos):
            self.close()
        elif self.slide == "end":
            if self.save_rect.contains(pos) and not self.saved:
                self.saved = True
                self.on_save(self.data)
                self.update()
            elif not self.save_rect.contains(pos):
                self.close()
        else:
            self.next()

    def _pic(self, key: str, size: int):
        if (key, size) not in self._pics:
            from .panel import portrait
            self._pics[(key, size)] = portrait(key, size, False, self.s.skins.get(key))
        return self._pics[(key, size)]

    # ── 그리기 ──
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        top, bottom, ink = PALETTE[self.slide]
        path = QPainterPath()
        path.addRoundedRect(r, 18, 18)
        g = QLinearGradient(0, 0, self.W * 0.3, self.H)
        g.setColorAt(0, QColor(top))
        g.setColorAt(1, QColor(bottom))
        p.setPen(QPen(QColor(0, 0, 0, 40), 1))
        p.setBrush(g)
        p.drawPath(path)
        p.save()
        p.setClipPath(path)
        self._pattern(p)
        p.restore()
        self._progress(p, ink)
        u = min(1.0, (time.monotonic() - self.slide_at) / 0.45)        # 장이 바뀔 때 살짝 떠오름
        p.save()
        p.translate(0, (1 - u) * 18)
        p.setOpacity(u)
        getattr(self, "_" + self.slide)(p, QColor(ink))
        p.restore()
        p.setPen(QPen(QColor(ink), 1.6))                                # ✕
        c = self.close_rect.center()
        p.drawLine(QPointF(c.x() - 6, c.y() - 6), QPointF(c.x() + 6, c.y() + 6))
        p.drawLine(QPointF(c.x() + 6, c.y() - 6), QPointF(c.x() - 6, c.y() + 6))
        p.end()

    def _pattern(self, p: QPainter) -> None:
        p.setPen(Qt.NoPen)
        for i in range(9):
            p.setBrush(QColor(255, 255, 255, 16 if i % 2 else 10))
            rad = 40 + (i * 37) % 70
            p.drawEllipse(QPointF((i * 131 + self.i * 53) % self.W, (i * 89 + self.i * 31) % self.H), rad, rad)

    def _progress(self, p: QPainter, ink: str) -> None:
        n = len(SLIDES)
        gap, x0, w = 5.0, 18.0, (self.W - 36 - 5.0 * (n - 1) - 34) / n
        for k in range(n):
            rect = QRectF(x0 + k * (w + gap), 20, w, 4)
            col = QColor(ink)
            col.setAlpha(70)
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(rect, 2, 2)
            fill = 1.0 if k < self.i else (min(1.0, (time.monotonic() - self.slide_at) / SLIDE_SECONDS)
                                           if k == self.i and self.slide != "end" else 1.0 if k == self.i else 0.0)
            if fill:
                col.setAlpha(230)
                p.setBrush(col)
                p.drawRoundedRect(QRectF(rect.x(), rect.y(), rect.width() * fill, 4), 2, 2)

    def _text(self, p: QPainter, rect: QRectF, text: str, size: int, color: QColor, bold: bool = False,
              align=Qt.AlignHCenter | Qt.AlignVCenter) -> None:
        f = QFont("Malgun Gothic")
        f.setPixelSize(size)
        f.setBold(bold)
        p.setFont(f)
        p.setPen(color)
        p.drawText(rect, align | Qt.TextWordWrap, text)

    def _intro(self, p: QPainter, ink: QColor) -> None:
        d = self.data
        self._text(p, QRectF(0, 56, self.W, 24), "HOKORA · 올해의 신사", 15, ink, True)
        self._text(p, QRectF(0, 86, self.W, 110), str(d["year"]), 92, ink, True)
        self._text(p, QRectF(0, 196, self.W, 30), "한 해 동안 고마웠어요!", 20, ink, True)
        self._text(p, QRectF(0, 230, self.W, 22), _range(d), 13, ink)
        self._text(p, QRectF(24, 268, self.W - 48, 50),
                   f"함께한 날 {d['days']}일  ·  켜 둔 시간 {_hours(d)}", 15, ink, True)
        keys = [k for k in self.s.unlocked][:9]
        size = 52 if len(keys) <= 6 else 40
        gap = min(size + 6.0, (self.W - 40) / max(1, len(keys)))
        x0 = self.W / 2 - gap * len(keys) / 2
        for i, k in enumerate(keys):
            p.drawPixmap(QRectF(x0 + i * gap + (gap - size) / 2, 340, size, size).toRect(), self._pic(k, size))
        self._text(p, QRectF(0, self.H - 56, self.W, 20), "눌러서 넘기기  ·  오른쪽 클릭으로 닫기", 11, ink)

    def _saisen(self, p: QPainter, ink: QColor) -> None:
        v = self.data["v"]
        self._text(p, QRectF(0, 70, self.W, 28), "올해 모은 새전", 20, ink, True)
        n = f"{v.get('saisen', 0):,}"
        self._text(p, QRectF(10, 110, self.W - 20, 90), n, 54 if len(n) <= 9 else 40 if len(n) <= 13 else 30, ink, True)
        lines = [f"🐾 쓰다듬기 {v.get('pats', 0):,}번", f"🎋 오미쿠지 {v.get('omikuji', 0):,}번",
                 f"⛩ 도리이 {v.get('torii', 0):,}개 세움"]
        if v.get("sengu"):
            lines.append(f"🏯 식년천궁 {v['sengu']}번 — 지금 {self.data['gen']}대째")
        for i, ln in enumerate(lines):
            self._text(p, QRectF(30, 236 + i * 40, self.W - 60, 32), ln, 17, ink, True)

    def _friend(self, p: QPainter, ink: QColor) -> None:
        d = self.data
        self._text(p, QRectF(0, 64, self.W, 28), "올해 가장 친해진 친구", 20, ink, True)
        key = d.get("best") or "reimu"
        from .affection import level
        from .render import CHARACTERS
        pm = self._pic(key, 170)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 70))
        p.drawEllipse(QPointF(self.W / 2, 200), 96, 96)
        p.drawPixmap(QRectF(self.W / 2 - 85, 115, 170, 170).toRect(), pm)
        name = CHARACTERS[key].name if key in CHARACTERS else key
        self._text(p, QRectF(0, 300, self.W, 36), name, 26, ink, True)
        self._text(p, QRectF(0, 338, self.W, 30), _hearts(level(self.s, key)), 22, ink, True)
        gain = d.get("best_gain", 0)
        self._text(p, QRectF(24, 380, self.W - 48, 50),
                   f"올해 호감도 +{gain}" if gain else "늘 곁에 있어 줬어요", 16, ink)

    def _guest(self, p: QPainter, ink: QColor) -> None:
        d = self.data
        self._text(p, QRectF(0, 64, self.W, 28), "가장 자주 온 손님", 20, ink, True)
        key = d.get("guest")
        if not key:
            self._text(p, QRectF(30, 150, self.W - 60, 120), "올해는 손님이 아직 없었어요.\n내년엔 공물을 올려 볼까요?", 18, ink, True)
            return
        from .render import short_name
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 50))
        p.drawEllipse(QPointF(self.W / 2, 200), 96, 96)
        p.drawPixmap(QRectF(self.W / 2 - 85, 115, 170, 170).toRect(), self._pic(key, 170))
        self._text(p, QRectF(0, 300, self.W, 36), short_name(key), 26, ink, True)
        self._text(p, QRectF(0, 340, self.W, 30), f"{d.get('guest_n', 0)}번 다녀갔어요", 19, ink, True)
        self._text(p, QRectF(24, 384, self.W - 48, 44),
                   f"손님은 모두 {d['v'].get('guests', 0):,}번 왔어요", 15, ink)

    def _numbers(self, p: QPainter, ink: QColor) -> None:
        self._text(p, QRectF(0, 56, self.W, 28), "숫자로 보는 올해", 20, ink, True)
        items = top_stats(self.data, 8)
        if not items:
            self._text(p, QRectF(30, 160, self.W - 60, 80), "올해는 조용히 쉬어 간 해였어요", 17, ink, True)
            return
        for i, (icon, name, unit, n) in enumerate(items):
            cx, cy = 22 + (i % 2) * 162, 100 + (i // 2) * 88
            cell = QRectF(cx, cy, 154, 78)
            p.setPen(QPen(QColor(200, 16, 46, 50), 1.2))
            p.setBrush(QColor(255, 255, 255, 210))
            p.drawRoundedRect(cell, 12, 12)
            self._text(p, cell.adjusted(10, 6, -8, -44), f"{icon} {name}", 12, QColor("#8C7479"), False,
                       Qt.AlignLeft | Qt.AlignVCenter)
            self._text(p, cell.adjusted(10, 30, -8, -6), f"{n:,}{unit}", 22, ink, True, Qt.AlignLeft | Qt.AlignVCenter)

    def _end(self, p: QPainter, ink: QColor) -> None:
        d = self.data
        self._text(p, QRectF(0, 70, self.W, 30), f"{d['year']}년도 고마웠어요", 24, ink, True)
        self._text(p, QRectF(30, 116, self.W - 60, 120),
                   f"{d['stage']} · {d['gen']}대째\n친구 {d['friends']}명과 함께\n내년에도 잘 부탁해요!", 18, ink, True)
        from .shrine import _torii
        p.save()
        _torii(p, self.W / 2 - 34, 316, 68, 72)
        p.restore()
        p.setPen(QPen(QColor(255, 255, 255, 220), 1.5))
        p.setBrush(QColor(255, 255, 255, 235) if not self.saved else QColor(255, 255, 255, 120))
        p.drawRoundedRect(self.save_rect, 14, 14)
        self._text(p, self.save_rect, "✓ 저장했어요 (클립보드에도)" if self.saved else "🖼  그림으로 저장하기", 16,
                   QColor("#B3122C"), True)
        self._text(p, QRectF(0, self.H - 70, self.W, 20), "다른 곳을 누르면 닫혀요", 11, ink)


# ── 한 장짜리 그림 ──
W, H = 1200, 675


def make_image(s: GameState, data: dict, shrine_img: QImage | None = None) -> QImage:
    from .panel import portrait
    from .render import CHARACTERS, short_name
    from .affection import level
    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    bg = QLinearGradient(0, 0, W, H)
    bg.setColorAt(0, QColor("#FFF8EC"))
    bg.setColorAt(1, QColor("#FBE3E7"))
    p.fillRect(QRectF(0, 0, W, H), bg)
    left = QLinearGradient(0, 0, 0, H)                        # 왼쪽 빨간 띠
    left.setColorAt(0, QColor("#B3122C"))
    left.setColorAt(1, QColor("#E0475E"))
    p.setPen(Qt.NoPen)
    p.setBrush(left)
    p.drawRoundedRect(QRectF(30, 30, 380, H - 60), 26, 26)
    p.setPen(QPen(QColor("#C8102E"), 4))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(18, 18, W - 36, H - 36), 26, 26)

    def text(rect: QRectF, t: str, size: int, color: str, bold: bool = False,
             align=Qt.AlignLeft | Qt.AlignVCenter) -> None:
        f = QFont("Malgun Gothic")
        f.setPixelSize(size)
        f.setBold(bold)
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(rect, align, t)

    center = Qt.AlignHCenter | Qt.AlignVCenter
    text(QRectF(30, 58, 380, 26), "HOKORA · 올해의 신사", 18, "#FFFFFF", True, center)
    text(QRectF(30, 84, 380, 110), str(data["year"]), 96, "#FFFFFF", True, center)
    text(QRectF(30, 190, 380, 24), _range(data), 15, "#FFE9EC", False, center)
    text(QRectF(30, 218, 380, 26), f"함께한 날 {data['days']}일 · 켜 둔 시간 {_hours(data)}", 16, "#FFFFFF", True, center)
    best = data.get("best") or "reimu"
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 60))
    p.drawEllipse(QPointF(130, 360), 74, 74)
    p.drawPixmap(QRectF(64, 294, 132, 132).toRect(), portrait(best, 132, False, s.skins.get(best)))
    text(QRectF(214, 300, 190, 22), "가장 친해진 친구", 14, "#FFE9EC")
    text(QRectF(214, 324, 190, 34), CHARACTERS[best].name if best in CHARACTERS else best, 22, "#FFFFFF", True)
    text(QRectF(214, 360, 190, 26), _hearts(level(s, best)), 18, "#FFFFFF")
    guest = data.get("guest")
    if guest:
        p.setBrush(QColor(255, 255, 255, 60))
        p.drawEllipse(QPointF(130, 520), 60, 60)
        p.drawPixmap(QRectF(76, 466, 108, 108).toRect(), portrait(guest, 108, False))
        text(QRectF(214, 480, 190, 22), "가장 자주 온 손님", 14, "#FFE9EC")
        text(QRectF(214, 504, 190, 34), short_name(guest), 22, "#FFFFFF", True)
        text(QRectF(214, 538, 190, 24), f"{data.get('guest_n', 0)}번 다녀감", 16, "#FFFFFF")

    x0 = 450
    text(QRectF(x0, 56, 700, 26), "올해 모은 새전", 18, "#8C7479", True)
    n = f"{data['v'].get('saisen', 0):,}"
    text(QRectF(x0, 82, 720, 76), n, 60 if len(n) <= 13 else 44, "#B3122C", True)
    text(QRectF(x0, 158, 720, 26), f"{data['stage']} · {data['gen']}대째  ·  친구 {data['friends']}명  ·  "
         f"쓰다듬기 {data['v'].get('pats', 0):,}번", 16, "#3A2A2E", True)
    for i, (icon, name, unit, val) in enumerate(top_stats(data, 9)):
        cx, cy = x0 + (i % 3) * 238, 206 + (i // 3) * 104
        cell = QRectF(cx, cy, 226, 92)
        p.setPen(QPen(QColor(200, 16, 46, 50), 1.2))
        p.setBrush(QColor(255, 255, 255, 210))
        p.drawRoundedRect(cell, 14, 14)
        text(cell.adjusted(16, 8, -10, -50), f"{icon} {name}", 15, "#8C7479")
        text(cell.adjusted(16, 38, -10, -8), f"{val:,}{unit}", 26, "#3A2A2E", True)
    if shrine_img is not None and not shrine_img.isNull():            # 오른쪽 아래 작은 신사
        k = min(150 / max(1, shrine_img.width()), 110 / max(1, shrine_img.height()))
        sw, sh = shrine_img.width() * k, shrine_img.height() * k
        p.drawImage(QRectF(W - 60 - sw, H - 70 - sh, sw, sh), shrine_img)
    text(QRectF(x0, H - 62, 720, 22), "Hokora — 작업표시줄 위의 나만의 신사 · 東方Project二次創作", 12, "#8C7479")
    p.end()
    return img


def save_image(s: GameState, data: dict, folder: Path, shrine_img: QImage | None = None) -> tuple[QImage, Path]:
    img = make_image(s, data, shrine_img)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"hokora_{data['year']}_결산_{datetime.now():%m%d_%H%M%S}.png"
    img.save(str(path))
    return img, path
