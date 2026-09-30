# -*- coding: utf-8 -*-
"""오늘의 부탁과 출석 도장.

- 출석 도장: 하루에 한 번(그날 처음 켰을 때, 켜 둔 채 날짜가 바뀌어도) 도장을 찍고 새전을 받는다.
  이어서 찍으면 연속 출석, 7일째엔 큰 선물(새전 + 오미쿠지 한 번 더). 하루라도 빠지면 1일째부터.
- 오늘의 부탁: 날마다 레이무가 부탁 3개를 한다 (쓰다듬기 N번, 말 걸기, 선물 등). 들어주면 새전,
  셋 다 들어주면 보너스. 날짜로 정해지므로 껐다 켜도 같은 부탁.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .state import GameState

# 부탁 종류 → (아이콘, 글, 목표 범위). 목표가 None 이면 신사 수입에 맞춰 정함
TASKS = {
    "pat": ("🤚", "친구를 {n}번 쓰다듬기", (20, 40)),
    "talk": ("💬", "친구 {n}명에게 말 걸기", (2, 3)),
    "gift": ("🎁", "선물 {n}번 하기", (1, 2)),
    "omikuji": ("🔮", "오미쿠지 뽑기", (1, 1)),
    "pray": ("🙏", "참배하기", (1, 1)),
    "throw": ("🤾", "친구를 {n}번 던지기", (3, 6)),
    "photo": ("📸", "사진 한 장 찍기", (1, 1)),
    "earn": ("💰", "새전 {n} 모으기", None),
    "time": ("⏳", "{n}분 함께 지내기", (30, 60)),
}
STAMP_REWARD = [10, 10, 15, 15, 20, 25, 60]   # 연속 N일째 → 분당 수입 × 이만큼
MIN_REWARD = 20


def today() -> str:
    return date.today().isoformat()


def _reward(s: GameState, times: float) -> int:
    return max(MIN_REWARD, int(round(s.income_per_min * times / 10)) * 10)


def new_day(s: GameState) -> bool:
    """날짜가 바뀌었으면 오늘의 부탁 3개를 새로 정함."""
    t = today()
    if s.daily_date == t:
        return False
    rng = random.Random(t)                                  # 같은 날엔 같은 부탁
    kinds = rng.sample(sorted(TASKS), 3)
    tasks = []
    for kind in kinds:
        rng_goal = TASKS[kind][2]
        if kind == "earn":
            goal = max(50, int(round(s.income_per_min * 45 / 10)) * 10)
        elif kind == "time":
            goal = rng.randint(3, 6) * 10
        else:
            goal = rng.randint(*rng_goal)
        if kind == "talk":
            goal = min(goal, len(s.unlocked))
        tasks.append({"kind": kind, "goal": goal, "count": 0, "reward": _reward(s, 12), "done": False})
    s.daily_date, s.daily_tasks = t, tasks
    s.daily_base_total, s.daily_base_runtime = s.saisen_total, s.runtime_sec
    return True


def stamp(s: GameState) -> tuple[int, int] | None:
    """오늘 출석 도장 → (이번 주기의 며칠째 1~7, 받은 새전). 이미 찍었으면 None."""
    t = date.today()
    if s.attend_last == t.isoformat():
        return None
    yesterday = (t - timedelta(days=1)).isoformat()
    s.attend_streak = s.attend_streak + 1 if s.attend_last == yesterday else 1
    s.attend_last = t.isoformat()
    s.attend_days += 1
    day = cycle_day(s)
    reward = _reward(s, STAMP_REWARD[day - 1])
    s.add_saisen(reward)
    if day == 7:
        s.omikuji_extra += 1
    return day, reward


def cycle_day(s: GameState) -> int:
    """7일 도장판에서 지금 며칠째인지 (도장이 없으면 0)."""
    return (s.attend_streak - 1) % 7 + 1 if s.attend_streak else 0


def count(s: GameState, task: dict) -> int:
    kind = task["kind"]
    if kind == "earn":
        return max(0, s.saisen_total - s.daily_base_total)
    if kind == "time":
        return int(max(0.0, s.runtime_sec - s.daily_base_runtime) // 60)
    return task["count"]


def bump(s: GameState, kind: str, n: int = 1) -> None:
    for task in s.daily_tasks:
        if task["kind"] == kind and not task["done"]:
            task["count"] += n


def check(s: GameState) -> tuple[list[dict], int]:
    """새로 들어준 부탁들(보상은 여기서 줌)과, 셋 다 들어줬을 때의 보너스(아니면 0)."""
    done_now = []
    for task in s.daily_tasks:
        if not task["done"] and count(s, task) >= task["goal"]:
            task["done"] = True
            s.add_saisen(task["reward"])
            s.daily_done += 1
            done_now.append(task)
    bonus = 0
    if done_now and all(t["done"] for t in s.daily_tasks):
        bonus = all_bonus(s)
        s.add_saisen(bonus)
    return done_now, bonus


def all_bonus(s: GameState) -> int:
    return _reward(s, 20)


def text(task: dict) -> str:
    return TASKS[task["kind"]][1].format(n=f"{task['goal']:,}")


def icon(task: dict) -> str:
    return TASKS[task["kind"]][0]


# ── 도장판 그리기 (카드와 신사 관리 창에서 같이 씀) ──
def draw_stamps(p: QPainter, rect: QRectF, filled: int, fresh: bool = False) -> None:
    """7칸 도장판. filled 칸까지 빨간 도장, 7번째 칸은 선물 표시. fresh 면 마지막 도장을 조금 크게."""
    n = 7
    gap = 6.0
    d = min(rect.height(), (rect.width() - gap * (n - 1)) / n)
    x0 = rect.left() + (rect.width() - (d * n + gap * (n - 1))) / 2
    f = QFont("Malgun Gothic", max(6, int(d * 0.24)))
    f.setBold(True)
    p.setFont(f)
    for i in range(n):
        c = QRectF(x0 + i * (d + gap), rect.top() + (rect.height() - d) / 2, d, d)
        p.setPen(QPen(QColor(200, 16, 46, 90), 1.2, Qt.DashLine))
        p.setBrush(QColor(255, 255, 255, 200))
        p.drawEllipse(c)
        if i < filled:
            s = c.adjusted(3, 3, -3, -3)
            if fresh and i == filled - 1:
                s = c.adjusted(1, 1, -1, -1)
            p.setPen(QPen(QColor("#C8102E"), 1.6))
            p.setBrush(QColor(200, 16, 46, 40))
            p.drawEllipse(s)
            p.setPen(QColor("#C8102E"))
            p.drawText(s, Qt.AlignCenter, "참")
        else:
            p.setPen(QColor(140, 116, 121))
            p.drawText(c, Qt.AlignCenter, "🎁" if i == n - 1 else f"{i + 1}")


class StampCard(QWidget):
    """출석 도장 카드 (그날 처음): 도장판 + 오늘의 부탁. 누르면 닫히고 30초 뒤 저절로 닫힌다."""

    W = 340

    def __init__(self, s: GameState, day: int, reward: int, extra: str = ""):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setCursor(Qt.PointingHandCursor)
        self.day, self.reward, self.streak, self.extra = day, reward, s.attend_streak, extra
        self.tasks = [(icon(t), text(t), t["reward"]) for t in s.daily_tasks]
        self.f_title = QFont("Malgun Gothic", 12)
        self.f_title.setBold(True)
        self.f_body = QFont("Malgun Gothic", 10)
        self.f_small = QFont("Malgun Gothic", 8)
        self.f_foot = QFont("Malgun Gothic", 11)
        self.f_foot.setBold(True)
        self.setFixedSize(self.W, 214 + 24 * len(self.tasks) + (20 if extra else 0))

    def show_above(self, cx: float, bottom: float) -> None:
        self.move(round(cx - self.width() / 2), round(bottom - self.height() - 8))
        self.show()
        QTimer.singleShot(30_000, self.close)

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
        p.drawText(QRectF(18, 14, self.W - 36, 24), Qt.AlignLeft | Qt.AlignVCenter,
                   f"💮 출석 도장 — {self.streak}일째")
        draw_stamps(p, QRectF(16, 48, self.W - 32, 40), self.day, fresh=True)
        p.setFont(self.f_small)
        p.setPen(QColor("#8C7479"))
        left = 7 - self.day
        p.drawText(QRectF(18, 94, self.W - 36, 16), Qt.AlignCenter,
                   "오늘은 큰 선물! 오미쿠지도 한 번 더" if left == 0 else f"{left}일 더 오면 큰 선물 (새전 + 오미쿠지 한 번 더)")
        p.setFont(self.f_foot)
        p.setPen(QColor("#B8860B"))
        p.drawText(QRectF(18, 112, self.W - 36, 24), Qt.AlignCenter, f"새전 +{self.reward:,}")
        y = 144.0
        if self.extra:
            p.setFont(self.f_body)
            p.setPen(QColor("#C8102E"))
            p.drawText(QRectF(18, y, self.W - 36, 20), Qt.AlignCenter, self.extra)
            y += 20
        p.setPen(QPen(QColor(200, 16, 46, 60), 1))
        p.drawLine(QPointF(18, y + 4), QPointF(self.W - 18, y + 4))
        p.setFont(self.f_body)
        p.setPen(QColor("#B3122C"))
        p.drawText(QRectF(18, y + 10, self.W - 36, 20), Qt.AlignLeft | Qt.AlignVCenter, "레이무의 오늘의 부탁")
        y += 34
        for ic, tx, rw in self.tasks:
            p.setPen(QColor("#3A2A2E"))
            p.drawText(QRectF(24, y, self.W - 110, 22), Qt.AlignLeft | Qt.AlignVCenter, f"{ic}  {tx}")
            p.setPen(QColor("#B8860B"))
            p.drawText(QRectF(self.W - 100, y, 80, 22), Qt.AlignRight | Qt.AlignVCenter, f"+{rw:,}")
            y += 24
        p.setFont(self.f_small)
        p.setPen(QColor("#8C7479"))
        p.drawText(QRectF(18, y + 6, self.W - 36, 16), Qt.AlignCenter, "셋 다 들어주면 보너스 · 신사 관리 창 '부탁' 탭에서 확인")
        p.end()
