# -*- coding: utf-8 -*-
"""그림 파일로 된 캐릭터 (tools/import_sheet.py 가 만든 hokora/sprites/<키>/).

그림 이름 규칙
  <동작>          한 장짜리 (예: fall)
  <동작>_0, _1 …  여러 장 → 차례로 재생 (예: walk_0 ~ walk_5)
  <동작>, <동작>_1 (0번 없이)  예전 방식: 여러 자세를 번갈아 (예: sit, sit_1)
  blink           서 있을 때 눈 깜빡임
동작: idle, walk, sit, happy, held, fall, sleep

그림이 한두 장뿐이면 움직임(걸을 때 통통, 숨쉬기, 폴짝)을 코드로 얹고,
그림이 직접 움직임을 담고 있으면(여러 장) 코드 효과를 줄인다.
폴더가 없는 캐릭터는 render.py 의 코드 그림을 그대로 쓴다.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

log = logging.getLogger("Hokora.sprites")
SPRITE_DIR = Path(__file__).resolve().parent / "sprites"
DISPLAY_H = 70.0     # 서 있는 자세가 화면에서 차지하는 높이 (논리 픽셀)
PAD = 8.0            # 흔들림·통통 튀기가 잘리지 않게 여유

# 동작 → 그림이 없을 때 대신 쓸 동작
FALLBACK = {
    "idle": [],
    "walk": ["idle"],
    "sit": ["idle"],
    "happy": ["idle"],
    "held": ["fall", "idle"],
    "fall": ["held", "idle"],
    "sleep": ["sit", "idle"],
    "startled": ["caught", "held", "fall", "idle"],
    "wave": ["happy", "idle"],
    "skill": ["idle"],
    "run": ["walk", "idle"],
    "caught": ["held", "fall", "idle"],
}


class ImageSprites:
    def __init__(self, folder: Path):
        m = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if isinstance(m.get("frames"), dict):          # 새 형식: 그림마다 발 위치
            anchors = m["frames"]
        else:                                           # 예전 형식: 모든 그림이 같은 캔버스
            anchors = {n: m["anchor"] for n in m["frames"]}
        self.facing = int(m.get("facing", 1))
        self.walk_cycles = max(1, int(m.get("walk_cycles", 1)))   # 걷기 그림 한 벌에 걸음 한 바퀴가 몇 번 들어 있는지
        self.scale = DISPLAY_H / float(m["standing_height"])
        self.images: dict[str, tuple[QImage, QPointF]] = {}
        for name, (ax, ay) in anchors.items():
            img = QImage(str(folder / f"{name}.png"))
            if img.isNull():
                raise ValueError(f"그림 없음: {folder / name}.png")
            self.images[name] = (img, QPointF(ax, ay))
        self._seq_cache: dict[str, list[str]] = {}

    def sequence(self, kind: str) -> list[str]:
        """이 동작에 쓸 그림 이름들 (재생 순서)."""
        if kind not in self._seq_cache:
            seq: list[str] = []
            for k in [kind, *FALLBACK.get(kind, ["idle"])]:
                numbered = sorted((n for n in self.images if re.fullmatch(rf"{k}_\d+", n)),
                                  key=lambda n: int(n.rsplit("_", 1)[1]))
                if numbered and (f"{k}_0" in self.images or k not in self.images):   # walk_0, walk_1 … 차례로 (0번이 빠져도)
                    seq = numbered
                elif k in self.images:                  # 한 장 (+ 예전 방식 변형 _1, _2)
                    seq = [k] + (numbered if k != "idle" else [])
                if seq:
                    break
            self._seq_cache[kind] = seq or [next(iter(self.images))]
        return self._seq_cache[kind]

    def pick(self, kind: str, phase: float, t: float, blink: bool) -> tuple[str, float, float, bool]:
        """이 순간 쓸 (그림 이름, 위아래 흔들림, 기울기, 그림자 여부).
        phase 는 이 동작 한 바퀴 중 어디쯤인지(0~1), t 는 초 단위 시간."""
        if kind == "jump":                   # 점프: 쓰다듬기 동작 중 가장 높이 뛴 장면 한 장
            seq = self.sequence("happy")
            name = seq[min(len(seq) - 1, int(len(seq) * 0.6))]
        else:
            seq = self.sequence(kind)
            name = seq[min(len(seq) - 1, int(phase * len(seq)))]
        if blink and kind == "idle" and "blink" in self.images:
            name = "blink"
        animated = len(seq) >= 3            # 그림이 움직임을 직접 담고 있음
        # 코드로 얹는 움직임 (그림이 움직임을 담고 있으면 약하게 / 생략)
        dy, angle = 0.0, 0.0
        if kind == "walk" and not animated:
            dy = -abs(math.sin(t * 9.0)) * 1.8
        elif kind == "idle" and not animated:
            dy = math.sin(t * 2.2) * 0.5
        elif kind == "happy" and not animated:
            dy = -abs(math.sin(t * 12.0)) * 3.0
        elif kind == "held":
            angle = math.sin(t * 10.0) * (2.5 if animated else 6.0)
        elif kind == "sleep" and not animated:
            dy = math.sin(t * 1.2) * 0.6
        elif kind == "run":
            dy = -abs(math.sin(t * 15.7)) * 2.0
        # 반 픽셀·1도 단위로 맞춰서 같은 모습은 한 번만 그리게
        return name, round(dy * 2) / 2, float(round(angle)), kind not in ("held", "fall", "jump")

    def draw(self, name: str, dy: float, angle: float, shadow: bool, facing: int,
             dpr: float) -> tuple[QPixmap, QPointF]:
        """(그림, 발 위치)."""
        img, anchor = self.images[name]
        s = self.scale
        w, h = img.width() * s + PAD * 2, img.height() * s + PAD * 2
        pm = QPixmap(round(w * dpr), round(h * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        ax, ay = PAD + anchor.x() * s, PAD + anchor.y() * s

        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if shadow:                           # 그림자 (공중에서는 없음)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 40))
            p.drawEllipse(QRectF(ax - 20, ay - 3.5, 40, 7))
        p.translate(ax, ay + dy)
        if angle:  # 머리 쪽을 잡고 있으니 머리 근처를 축으로 흔들기
            pivot = -DISPLAY_H * 0.75
            p.translate(0, pivot)
            p.rotate(angle)
            p.translate(0, -pivot)
        if facing != self.facing:
            p.scale(-1, 1)
        p.drawImage(QRectF(-anchor.x() * s, -anchor.y() * s, img.width() * s, img.height() * s), img)
        p.end()
        return pm, QPointF(ax, ay)

    def render(self, kind: str, phase: float, t: float, facing: int, blink: bool,
               dpr: float) -> tuple[QPixmap, QPointF]:
        """pick + draw (미리보기 도구용)."""
        return self.draw(*self.pick(kind, phase, t, blink), facing, dpr)


_loaded: dict[str, ImageSprites | None] = {}


def image_sprites(key: str, folder: Path | None = None) -> ImageSprites | None:
    """그림 폴더가 있으면 불러오고, 없거나 HOKORA_CODE_ART=1 이면 None (코드 그림 사용)."""
    cache_key = str(folder) if folder else key
    if cache_key not in _loaded:
        folder = folder or SPRITE_DIR / key
        sprites = None
        if os.environ.get("HOKORA_CODE_ART") != "1" and (folder / "manifest.json").exists():
            try:
                sprites = ImageSprites(folder)
                log.info("그림 캐릭터: %s (%d장)", key, len(sprites.images))
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                log.exception("그림 불러오기 실패 — 코드 그림으로: %s", key)
        _loaded[cache_key] = sprites
    return _loaded[cache_key]
