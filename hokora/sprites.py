# -*- coding: utf-8 -*-
"""그림 파일로 된 캐릭터 (tools/import_sheet.py 가 만든 hokora/sprites/<키>/).

그림은 자세만 담고, 움직임(걸을 때 통통, 숨쉬기, 매달려 흔들기)은 여기서 코드로 얹는다.
폴더가 없는 캐릭터는 render.py 의 코드 그림을 그대로 쓴다.
"""
from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

log = logging.getLogger("Hokora.sprites")
SPRITE_DIR = Path(__file__).resolve().parent / "sprites"
DISPLAY_H = 70.0     # 서 있는 자세가 화면에서 차지하는 높이 (논리 픽셀)
PAD = 8.0            # 흔들림·통통 튀기가 잘리지 않게 여유

# 동작 → 쓸 그림 이름 앞부분 (없으면 다음 후보로)
KIND_FRAMES = {
    "idle": ["idle"],
    "walk": ["walk", "idle"],
    "sit": ["sit", "idle"],
    "happy": ["happy", "idle"],
    "held": ["held", "fall", "idle"],
    "fall": ["fall", "held", "idle"],
    "sleep": ["sleep", "sit", "idle"],
}
WALK_STEP = math.pi / 9.0   # render.py 의 걷기(sin 9t) 반 주기 = 한 발짝
SIT_SWAP = 4.0              # 앉아서 두리번거리는 간격(초)


class ImageSprites:
    def __init__(self, folder: Path):
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        self.anchor = QPointF(*manifest["anchor"])
        self.facing = int(manifest.get("facing", 1))
        self.scale = DISPLAY_H / float(manifest["standing_height"])
        cw, ch = manifest["canvas"]
        self.canvas = (cw, ch)
        self.images: dict[str, QImage] = {}
        for name in manifest["frames"]:
            img = QImage(str(folder / f"{name}.png"))
            if img.isNull():
                raise ValueError(f"그림 없음: {folder / name}.png")
            self.images[name] = img

    def _frames_for(self, kind: str) -> list[str]:
        for prefix in KIND_FRAMES.get(kind, ["idle"]):
            names = sorted(n for n in self.images if n == prefix or n.startswith(prefix + "_"))
            if prefix == "idle":
                names = ["idle"] if "idle" in self.images else names[:1]
            if names:
                return names
        return [next(iter(self.images))]

    def render(self, kind: str, t: float, facing: int, blink: bool, dpr: float) -> tuple[QPixmap, QPointF]:
        """(그림, 발 위치) — 발 위치는 그림 안의 논리 좌표."""
        names = self._frames_for(kind)
        if kind == "walk":
            name = names[int(t / WALK_STEP) % len(names)]
        elif kind == "sit":
            name = names[int(t / SIT_SWAP) % len(names)]
        else:
            name = names[0]
        if blink and kind == "idle" and "blink" in self.images:
            name = "blink"
        img = self.images[name]

        cw, ch = self.canvas[0] * self.scale, self.canvas[1] * self.scale
        w, h = cw + PAD * 2, ch + PAD * 2
        pm = QPixmap(round(w * dpr), round(h * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        ax, ay = PAD + self.anchor.x() * self.scale, PAD + self.anchor.y() * self.scale

        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if kind not in ("held", "fall"):  # 그림자
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 40))
            p.drawEllipse(QRectF(ax - 20, ay - 3.5, 40, 7))
        # 코드로 얹는 움직임
        dy, angle = 0.0, 0.0
        if kind == "walk":
            dy = -abs(math.sin(t * 9.0)) * 1.8
        elif kind == "idle":
            dy = math.sin(t * 2.2) * 0.5
        elif kind == "happy":
            dy = -abs(math.sin(t * 12.0)) * 3.0
        elif kind == "held":
            angle = math.sin(t * 10.0) * 6.0
        elif kind == "sleep":
            dy = math.sin(t * 1.2) * 0.6
        p.translate(ax, ay + dy)
        if angle:  # 머리 쪽을 잡고 있으니 머리 근처를 축으로 흔들기
            pivot = -ch * 0.75
            p.translate(0, pivot)
            p.rotate(angle)
            p.translate(0, -pivot)
        if facing != self.facing:
            p.scale(-1, 1)
        p.drawImage(QRectF(-self.anchor.x() * self.scale, -self.anchor.y() * self.scale, cw, ch), img)
        p.end()
        return pm, QPointF(ax, ay)


_loaded: dict[str, ImageSprites | None] = {}


def image_sprites(key: str) -> ImageSprites | None:
    """그림 폴더가 있으면 불러오고, 없거나 HOKORA_CODE_ART=1 이면 None (코드 그림 사용)."""
    if key not in _loaded:
        folder = SPRITE_DIR / key
        sprites = None
        if os.environ.get("HOKORA_CODE_ART") != "1" and (folder / "manifest.json").exists():
            try:
                sprites = ImageSprites(folder)
                log.info("그림 캐릭터: %s (%d장)", key, len(sprites.images))
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                log.exception("그림 불러오기 실패 — 코드 그림으로: %s", key)
        _loaded[key] = sprites
    return _loaded[key]
