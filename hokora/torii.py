# -*- coding: utf-8 -*-
"""센본토리이 (천 개의 도리이) — 후시미 이나리 신사처럼 도리이를 하나씩 봉납한다.

- 봉납할 때마다 값이 조금씩 오른다 (300, 330, 360 …). 끝없이 새전을 쓸 곳.
- 도리이 2개마다 분당 새전 +1.
- 10·50·100·300·1000개에 칭호.
- 화면엔 최근 몇 개만 신사 옆에 줄지어 서 있다 (다 세우면 작업표시줄이 꽉 차니까).
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from . import omamori
from .shrine import _torii
from .state import GameState

COST_BASE, COST_STEP = 300, 30
MILESTONES = {10: "참배길", 50: "붉은 터널", 100: "도리이 숲", 300: "이나리의 길", 1000: "센본토리이"}
SHOWN = 12                     # 화면에 세워 두는 도리이 수
TW, TH, GAP = 34.0, 50.0, 15.0  # 도리이 하나 크기와 간격 (보통 크기 기준)
GROUND_MARGIN = 2


def cost(s: GameState, n: int | None = None) -> int:
    """n번째(0부터) 도리이 값. 봉납 부적이 있으면 깎아 줌."""
    n = s.torii if n is None else n
    c = (COST_BASE + COST_STEP * n) * (1 - omamori.bonus(s, "torii"))
    return max(10, int(round(c / 10)) * 10)


def cost_many(s: GameState, k: int) -> int:
    return sum(cost(s, s.torii + i) for i in range(k))


def income(s: GameState) -> int:
    return s.torii // 2


def title(s: GameState) -> str:
    got = [name for n, name in MILESTONES.items() if s.torii >= n]
    return got[-1] if got else ""


def next_milestone(s: GameState) -> tuple[int, str] | None:
    return next(((n, name) for n, name in MILESTONES.items() if s.torii < n), None)


def offer(s: GameState, k: int) -> list[str] | None:
    """도리이 k개 봉납. 새전이 모자라면 None, 아니면 새로 얻은 칭호들."""
    total = cost_many(s, k)
    if s.saisen < total:
        return None
    s.saisen -= total
    before = s.torii
    s.torii += k
    return [name for n, name in MILESTONES.items() if before < n <= s.torii]


class ToriiRow(QWidget):
    """신사 옆에 줄지어 선 도리이들. 누르면 신사 관리 창."""

    def __init__(self, host):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setCursor(Qt.PointingHandCursor)
        self.host = host
        self.count = 0
        self.k = 1.0
        self.night = False
        self._pos = None

    @property
    def shown(self) -> int:
        return min(self.count, SHOWN)

    def setup(self, count: int, k: float, night: bool, tip: str) -> None:
        if (count, k, night) != (self.count, self.k, self.night):
            self.count, self.k, self.night = count, k, night
            n = max(1, self.shown)
            self.setFixedSize(round((TW + GAP * (n - 1)) * k + 4), round(TH * k) + GROUND_MARGIN)
            self._pos = None
            self.update()
        self.setToolTip(tip)

    def place(self, shrine_left: float, shrine_right: float, ground: float, x1: float, x2: float) -> None:
        """신사 왼쪽에 자리가 있으면 왼쪽, 없으면 오른쪽에 붙어 섬."""
        w = self.width()
        x = shrine_left - w + 6 if shrine_left - x1 >= w else shrine_right - 6
        pos = (round(x), round(ground - self.height() + GROUND_MARGIN))
        if pos != self._pos:
            self._pos = pos
            self.move(*pos)

    def paintEvent(self, _e) -> None:
        if not self.count:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        k = self.k
        ground = self.height() - GROUND_MARGIN
        p.scale(k, k)
        for i in range(self.shown):                     # 먼 것부터 그려서 앞의 것이 겹쳐 보이게
            _torii(p, 2 + i * GAP, ground / k, TW, TH)
        if self.night:
            p.resetTransform()
            p.setCompositionMode(QPainter.CompositionMode_SourceAtop)
            p.fillRect(QRectF(self.rect()), QColor(28, 36, 96, 95))
        p.end()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.host.on_shrine_clicked()
        elif e.button() == Qt.RightButton:
            self.host.on_context_menu(e.globalPosition().toPoint())
