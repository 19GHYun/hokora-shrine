# -*- coding: utf-8 -*-
"""
AI로 뽑은 초록 배경 스프라이트 시트 → 게임용 캐릭터 그림.

  python tools/import_sheet.py 시트.png reimu --names idle,blink,walk_0,walk_1,sit,...
  python tools/import_sheet.py 시트.png reimu            (이름 없이: 번호가 붙은 미리보기만)

하는 일
  1. 초록 배경(#00FF00 근처)과 워터마크를 투명하게, 가장자리의 초록 번짐 제거
  2. 초록 사이에 떨어져 있는 캐릭터를 하나씩 찾아 읽는 순서(위→아래, 왼→오)로 번호 매기기
     (격자에 딱 맞출 필요 없음)
  3. 모든 프레임을 같은 비율로 줄이고, 같은 크기의 캔버스에 발 위치를 맞춰 저장
     → hokora/sprites/<캐릭터>/<이름>.png + manifest.json
  4. 번호가 붙은 미리보기: hokora/sprites/<캐릭터>/_preview.png

프레임 이름 규칙: idle, blink, walk_0.., sit, happy, held, fall, sleep  (뒤에 _1, _2 로 변형 추가 가능)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter

ROOT = Path(__file__).resolve().parent.parent
SPRITES = ROOT / "hokora" / "sprites"
STANDING_PX = 200      # 저장할 때 서 있는 자세(idle)의 높이
PAD = 6
GRID = 4               # 캐릭터 찾기는 1/4 크기 격자로 (속도)
_qt_app = None


def chroma_key(src: QImage) -> QImage:
    """초록 배경을 투명하게. 캐릭터 안의 초록(사쿠야 리본 등)은 남긴다.

    1. 그림 가장자리에서 이어진 '초록 계열' 픽셀만 배경으로 (윤곽선 안쪽의 초록 옷·리본은 닿지 않음)
    2. 윤곽선에 갇힌 배경 틈(팔과 몸 사이 등)은 배경색과 거의 같은 '순수한 초록'만 추가로 배경 처리
    3. 배경 바로 옆 픽셀만 초록 번짐을 눌러줌 (안쪽 초록 색은 건드리지 않음)
    """
    src = src.convertToFormat(QImage.Format_ARGB32)
    w, h = src.width(), src.height()
    n = w * h
    data = bytearray(bytes(src.constBits()))  # BGRA
    spill = bytearray(n)       # 초록이 r·b 보다 얼마나 센지 (0~255)
    loose = bytearray(n)       # 배경이거나 배경과 섞인 가장자리일 수 있음
    bg = bytearray(n)
    for k in range(n):
        i = k * 4
        b, g, r = data[i], data[i + 1], data[i + 2]
        m = r if r > b else b
        s = g - m
        if s > 0:
            spill[k] = s
            if g > 100 and s > 60:
                loose[k] = 1
                if g > 170 and r < 110 and b < 110 and s > 120:
                    bg[k] = 1          # 순수한 배경색 → 갇힌 틈이어도 배경
    # 1. 가장자리에서 flood fill
    q = deque(k for k in list(range(w)) + list(range(n - w, n)) + list(range(0, n, w)) + list(range(w - 1, n, w))
              if loose[k])
    for k in q:
        bg[k] = 3
    while q:
        k = q.popleft()
        x = k % w
        for nk in (k - w, k + w, k - 1 if x else -1, k + 1 if x < w - 1 else -1):
            if 0 <= nk < n and loose[nk] and not (bg[nk] & 2):
                bg[nk] = 3             # 1 = 배경, 2 = 방문함
                q.append(nk)
    # 2·3. 배경은 투명하게, 배경 바로 옆은 초록 번짐만 제거
    for k in range(n):
        s = spill[k]
        if bg[k]:
            i = k * 4
            m = max(data[i], data[i + 2])
            data[i + 3] = max(0, 255 - min(255, s * 3))
            data[i + 1] = m
        elif s > 20:
            x = k % w
            if ((k >= w and bg[k - w]) or (k + w < n and bg[k + w])
                    or (x and bg[k - 1]) or (x < w - 1 and bg[k + 1])):
                i = k * 4
                data[i + 1] = max(data[i], data[i + 2]) + 20
    return QImage(bytes(data), w, h, QImage.Format_ARGB32).copy()


def find_blobs(img: QImage, expected: int | None = None):
    """불투명한 덩어리(캐릭터)들을 읽는 순서로.

    돌려주는 값: ([(경계 상자 (x0, y0, x1, y1), 라벨)...], 격자 라벨 배열, 격자 폭)
    라벨 배열은 GRID 크기 칸마다 어느 캐릭터 것인지(0 = 배경) — 옆 캐릭터가 상자에 삐져 들어온 부분을 지울 때 씀.
    """
    w, h = img.width(), img.height()
    gw, gh = (w + GRID - 1) // GRID, (h + GRID - 1) // GRID
    data = bytes(img.constBits())
    stride = img.bytesPerLine()
    solid = bytearray(gw * gh)
    for gy in range(gh):
        y = min(h - 1, gy * GRID + GRID // 2)
        row = y * stride
        for gx in range(gw):
            x = min(w - 1, gx * GRID + GRID // 2)
            if data[row + x * 4 + 3] > 60:
                solid[gy * gw + gx] = 1
    labels = [0] * (gw * gh)
    comps = []  # [x0, y0, x1, y1, 넓이, 라벨]
    for start in range(gw * gh):
        if not solid[start] or labels[start]:
            continue
        lab = len(comps) + 1
        q = deque([start])
        labels[start] = lab
        x0 = y0 = 10 ** 9
        x1 = y1 = area = 0
        while q:
            c = q.popleft()
            cy, cx = divmod(c, gw)
            area += 1
            x0, x1, y0, y1 = min(x0, cx), max(x1, cx), min(y0, cy), max(y1, cy)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < gw and 0 <= ny < gh:
                    n = ny * gw + nx
                    if solid[n] and not labels[n]:
                        labels[n] = lab
                        q.append(n)
        comps.append([x0, y0, x1, y1, area, lab])
    if not comps:
        return [], labels, gw
    # 작은 조각(떨어진 손끝·먼지)은 가장 가까운 큰 덩어리에 합치기
    big = max(c[4] for c in comps)
    main = [c for c in comps if c[4] >= big * 0.05]
    remap = {}
    for c in comps:
        if c in main:
            continue
        cx, cy = (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
        tgt = min(main, key=lambda m: max(0, m[0] - cx, cx - m[2]) + max(0, m[1] - cy, cy - m[3]))
        tgt[0], tgt[1] = min(tgt[0], c[0]), min(tgt[1], c[1])
        tgt[2], tgt[3] = max(tgt[2], c[2]), max(tgt[3], c[3])
        remap[c[5]] = tgt[5]
    if remap:
        labels = [remap.get(v, v) for v in labels]
    if expected:
        _split_touching(main, labels, gw, expected, next_label=max(c[5] for c in comps) + 1)
    blobs = [((c[0] * GRID, c[1] * GRID, min(w, (c[2] + 1) * GRID), min(h, (c[3] + 1) * GRID)), c[5])
             for c in main]
    # 읽는 순서: 줄(가운데 y가 비슷한 것끼리) → 줄 안에서 왼쪽부터
    cy_of = lambda b: (b[0][1] + b[0][3]) / 2  # noqa: E731
    med_h = sorted(b[0][3] - b[0][1] for b in blobs)[len(blobs) // 2]
    blobs.sort(key=cy_of)
    rows, row = [], [blobs[0]]
    for b in blobs[1:]:
        if cy_of(b) - cy_of(row[0]) > med_h * 0.5:
            rows.append(row)
            row = [b]
        else:
            row.append(b)
    rows.append(row)
    return [b for r in rows for b in sorted(r, key=lambda b: b[0][0])], labels, gw


def _split_touching(main: list, labels: list, gw: int, expected: int, next_label: int) -> None:
    """캐릭터끼리 닿아서(모자 챙 등) 한 덩어리로 잡혔을 때: 기대 개수가 될 때까지
    유난히 넓은 덩어리를 가운데 30~70% 구간에서 가장 가는 세로줄로 잘라 둘로 나눈다."""
    while len(main) < expected:
        widths = sorted(c[2] - c[0] + 1 for c in main)
        med_w = widths[len(widths) // 2]
        wide = max(main, key=lambda c: c[2] - c[0])
        x0, y0, x1, y1, _, lab = wide
        if x1 - x0 + 1 < med_w * 1.5:
            print("붙은 캐릭터를 더 나눌 수 없습니다 (유난히 넓은 덩어리 없음)")
            return
        span = x1 - x0

        def thickness(x: int) -> int:
            return sum(1 for y in range(y0, y1 + 1) if labels[y * gw + x] == lab)

        cut = min(range(x0 + span * 3 // 10, x0 + span * 7 // 10 + 1), key=thickness)
        parts = {lab: [10 ** 9, 10 ** 9, -1, -1, 0], next_label: [10 ** 9, 10 ** 9, -1, -1, 0]}
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                k = y * gw + x
                if labels[k] != lab:
                    continue
                if x >= cut:
                    labels[k] = next_label
                b = parts[labels[k]]
                b[0], b[1], b[2], b[3] = min(b[0], x), min(b[1], y), max(b[2], x), max(b[3], y)
                b[4] += 1
        main.remove(wide)
        main.extend([*b, key] for key, b in parts.items())
        print(f"붙어 있던 캐릭터를 나눔 (세로줄 x={cut * GRID})")
        next_label += 1


def tight(img: QImage, blob, labels, gw) -> tuple[QImage, float]:
    """상자 안에서 이 캐릭터 픽셀만 남겨(옆 캐릭터 조각은 지움) 딱 맞게 자르고,
    몸 무게중심 x(잘린 그림 기준)를 돌려준다."""
    (x0, y0, x1, y1), lab = blob
    crop = img.copy(x0, y0, x1 - x0, y1 - y0).convertToFormat(QImage.Format_ARGB32)
    w, h = crop.width(), crop.height()
    stride = crop.bytesPerLine()
    data = bytearray(bytes(crop.constBits()))
    gh = len(labels) // gw

    def owner_other(px: int, py: int) -> bool:
        """이 픽셀 주변 칸에 다른 캐릭터만 있고 이 캐릭터는 없으면 True."""
        gx, gy = (x0 + px) // GRID, (y0 + py) // GRID
        mine = other = False
        for ny in (gy - 1, gy, gy + 1):
            if 0 <= ny < gh:
                base = ny * gw
                for nx in (gx - 1, gx, gx + 1):
                    if 0 <= nx < gw:
                        v = labels[base + nx]
                        if v == lab:
                            mine = True
                        elif v:
                            other = True
        return other and not mine

    minx, miny, maxx, maxy = w, h, -1, -1
    sx = sa = 0
    for y in range(h):
        row = y * stride
        for x in range(w):
            i = row + x * 4 + 3
            a = data[i]
            if not a:
                continue
            if owner_other(x, y):
                data[i] = 0
                continue
            if a > 60:
                minx, maxx, miny, maxy = min(minx, x), max(maxx, x), min(miny, y), max(maxy, y)
                sx += x * a
                sa += a
    clean = QImage(bytes(data), w, h, stride, QImage.Format_ARGB32).copy()
    out = clean.copy(minx, miny, maxx - minx + 1, maxy - miny + 1)
    return out, (sx / max(1, sa)) - minx


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sheet", type=Path)
    ap.add_argument("character", help="캐릭터 키 (reimu, marisa, ...)")
    ap.add_argument("--names", help="찾은 순서대로 붙일 프레임 이름, 쉼표로 구분")
    args = ap.parse_args()
    global _qt_app  # QImage 스케일링·글꼴에 필요, 끝날 때까지 살아 있어야 함
    _qt_app = QGuiApplication.instance() or QGuiApplication(sys.argv)

    src = QImage(str(args.sheet))
    if src.isNull():
        print(f"그림을 읽지 못했습니다: {args.sheet}")
        return 1
    keyed = chroma_key(src)
    wanted = [n.strip() for n in args.names.split(",")] if args.names else None
    blobs, labels, gw = find_blobs(keyed, expected=len(wanted) if wanted else None)
    print(f"캐릭터 {len(blobs)}개 찾음")
    names = wanted or [f"frame_{i + 1}" for i in range(len(blobs))]
    if len(names) != len(blobs):
        print(f"이름 {len(names)}개와 찾은 캐릭터 {len(blobs)}개의 수가 다릅니다. 미리보기를 보고 다시 지정하세요.")
        names = [f"frame_{i + 1}" for i in range(len(blobs))]
        args.names = None

    frames = [tight(keyed, b, labels, gw) for b in blobs]
    ref = names.index("idle") if "idle" in names else 0
    scale = STANDING_PX / frames[ref][0].height()
    # 모든 프레임에 같은 캔버스: 발(아래) = 바닥선, 몸 무게중심 = 가운데
    left = max(cx * scale for img, cx in frames)
    right = max((img.width() - cx) * scale for img, cx in frames)
    half = int(max(left, right)) + PAD
    canvas_w, canvas_h = half * 2, int(max(img.height() * scale for img, _ in frames)) + PAD * 2
    anchor = (half, canvas_h - PAD)

    out_dir = SPRITES / args.character
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):
        old.unlink()
    for (img, cx), name in zip(frames, names):
        canvas = QImage(canvas_w, canvas_h, QImage.Format_ARGB32_Premultiplied)
        canvas.fill(Qt.transparent)
        p = QPainter(canvas)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        tw, th = img.width() * scale, img.height() * scale
        p.drawImage(QRectF(anchor[0] - cx * scale, anchor[1] - th, tw, th), img)
        p.end()
        canvas.save(str(out_dir / f"{name}.png"))
    if args.names:
        manifest = {"canvas": [canvas_w, canvas_h], "anchor": list(anchor), "standing_height": STANDING_PX,
                    "facing": 1, "frames": names, "source": args.sheet.name}
        (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # 번호 붙은 미리보기 (바닥선 확인용)
    cols = min(6, len(frames))
    rows = (len(frames) + cols - 1) // cols
    cell_w, cell_h = canvas_w + 10, canvas_h + 28
    prev = QImage(cell_w * cols, cell_h * rows, QImage.Format_ARGB32)
    prev.fill(QColor("#EDE6EA"))
    p = QPainter(prev)
    p.setFont(QFont("Malgun Gothic", 10))
    for i, name in enumerate(names):
        x, y = (i % cols) * cell_w + 5, (i // cols) * cell_h + 4
        p.setPen(QColor(200, 16, 46, 120))
        p.drawLine(QPointF(x, y + anchor[1]), QPointF(x + canvas_w, y + anchor[1]))       # 바닥선
        p.drawLine(QPointF(x + anchor[0], y), QPointF(x + anchor[0], y + canvas_h))       # 가운데
        p.drawImage(x, y, QImage(str(out_dir / f"{name}.png")))
        p.setPen(QColor("#2B1D21"))
        p.drawText(QRectF(x, y + canvas_h + 2, canvas_w, 20), Qt.AlignCenter, f"{i + 1}. {name}")
    p.end()
    prev.save(str(out_dir / "_preview.png"))
    print(f"저장: {out_dir}")
    if not args.names:
        print("미리보기(_preview.png)를 보고 --names 로 이름을 붙여 다시 실행하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
