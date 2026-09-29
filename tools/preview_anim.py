# -*- coding: utf-8 -*-
"""
캐릭터 움직임을 크게 틀어 보는 창 (그림 떨림·부드러움 확인용).

  python tools/preview_anim.py reimu                     지금 그림
  python tools/preview_anim.py reimu build/reimu_v1      지금 그림(위) vs 예전 그림(아래) 비교

동작별로 게임과 같은 속도·순서로 반복 재생한다. 쓰다듬기(happy)는 1.5초마다 다시 폴짝.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QFont, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from hokora.pet import FRAMES, ONE_SHOT  # noqa: E402
from hokora.sprites import ImageSprites  # noqa: E402

KINDS = ["idle", "walk", "happy", "held", "sit"]
ZOOM = 3.0
CELL_W, CELL_H = 90, 100          # 논리 픽셀 (확대 전)
HAPPY_REPEAT = 1.5


class Preview(QWidget):
    def __init__(self, rows: list[tuple[str, ImageSprites]]):
        super().__init__()
        self.rows = rows
        self.start = time.monotonic()
        self.blink_until = 0.0
        self.setWindowTitle("Hokora 움직임 미리보기")
        self.setFixedSize(int(40 + len(KINDS) * CELL_W * ZOOM), int(len(rows) * (CELL_H * ZOOM + 30) + 20))
        QTimer(self, timeout=self.update, interval=33).start()

    def paintEvent(self, _e) -> None:
        t = time.monotonic() - self.start
        if t > self.blink_until + 3.0:          # 3초마다 한 번 깜빡
            self.blink_until = t + 0.14
        blink = t < self.blink_until
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#AFC6E4"))
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setFont(QFont("Malgun Gothic", 11))
        for r, (label, sprites) in enumerate(self.rows):
            y0 = 20 + r * (CELL_H * ZOOM + 30)
            p.setPen(QColor("#2B1D21"))
            p.drawText(QRectF(10, y0 - 18, 400, 18), Qt.AlignLeft, label)
            p.fillRect(QRectF(0, y0 + (CELL_H - 12) * ZOOM, self.width(), 12 * ZOOM), QColor("#1F1F24"))
            for c, kind in enumerate(KINDS):
                n, loop = FRAMES[kind]
                if kind in ONE_SHOT:
                    local = t % HAPPY_REPEAT
                    frame = min(n - 1, int(local / loop * n))
                else:
                    frame = int((t % loop) / loop * n)
                pm, anchor = sprites.render(kind, frame / n, frame * loop / n, 1, blink and kind == "idle", ZOOM)
                foot = QPointF(20 + (c + 0.5) * CELL_W * ZOOM, y0 + (CELL_H - 12) * ZOOM)
                p.save()
                p.translate(foot)
                p.scale(ZOOM, ZOOM)
                p.drawPixmap(-anchor, pm)
                p.restore()
                p.setPen(QColor("#EEEEEE"))
                p.drawText(QRectF(foot.x() - 60, foot.y() + 4, 120, 20), Qt.AlignCenter, kind)
        p.end()


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    app = QApplication(sys.argv)  # noqa: F841
    rows = [(f"지금: {sys.argv[1]}", ImageSprites(ROOT / "hokora" / "sprites" / sys.argv[1]))]
    for extra in sys.argv[2:]:
        folder = Path(extra)
        rows.append((f"비교: {folder}", ImageSprites(folder if folder.is_absolute() else ROOT / folder)))
    w = Preview(rows)
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
