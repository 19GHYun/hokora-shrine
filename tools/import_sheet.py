# -*- coding: utf-8 -*-
"""
AI로 뽑은 초록 배경 스프라이트 시트 → 게임용 캐릭터 그림.

  python tools/import_sheet.py 시트.png reimu --names idle,blink,walk_0,walk_1,sit,...
  python tools/import_sheet.py 시트.png reimu            (이름 없이: 번호가 붙은 미리보기만)
  python tools/import_sheet.py 걷기.png reimu --append --names walk_0,walk_1,...   (기존 그림에 추가)
  이름 자리에 - 를 쓰면 그 장면은 버림 (예: happy_0,-,happy_1)
  python tools/import_sheet.py 생활.png reimu --preset life    (표준 세트 시트: 이름 자동, 기존 그림에 추가)

하는 일
  1. 초록 배경(#00FF00 근처)과 워터마크를 투명하게, 가장자리의 초록 번짐 제거
  2. 초록 사이에 떨어져 있는 캐릭터를 하나씩 찾아 읽는 순서(위→아래, 왼→오)로 번호 매기기
     (격자에 딱 맞출 필요 없음)
  3. 모든 프레임을 같은 비율로 줄이고, 같은 크기의 캔버스에 발 위치를 맞춰 저장
     → hokora/sprites/<캐릭터>/<이름>.png + manifest.json
  4. 번호가 붙은 미리보기: hokora/sprites/<캐릭터>/_preview.png

프레임 이름 규칙: <동작> 한 장, 또는 <동작>_0, <동작>_1 … 여러 장(차례로 재생)
  동작: idle, walk, sit, happy, held, fall, sleep  + 눈 깜빡임 blink
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

# 표준 세트 (README 의 Gemini 프롬프트와 같은 순서). 캐릭터당 시트 3장.
PRESETS = {
    "move": ["idle_0", "idle_1", "blink", "walk_0", "walk_1", "walk_2", "walk_3", "walk_4", "walk_5"],
    "react": ["sit_0", "sit_1", "fall", "happy_0", "happy_1", "happy_2", "happy_3", "held_0", "held_1", "held_2"],
    "life": ["sleep_0", "sleep_1", "wave_0", "wave_1", "skill_0", "skill_1", "run_0", "run_1", "caught"],
    "walk": [],            # 장수 자유: 찾은 만큼 walk_0, walk_1 … (8·12·16장 등)
}
REPLACE_PREFIX = {"walk": "walk_"}     # 이 프리셋은 같은 동작의 옛 그림을 먼저 지움


def key_color(img: QImage) -> str:
    """배경색 자동 판별: 그림 테두리 픽셀 평균이 초록이면 "green", 자홍(마젠타)이면 "magenta"."""
    w, h = img.width(), img.height()
    pts = [(x, y) for x in range(0, w, max(1, w // 40)) for y in (0, h - 1)]
    pts += [(x, y) for y in range(0, h, max(1, h // 40)) for x in (0, w - 1)]
    r = g = b = 0
    for x, y in pts:
        c = img.pixel(x, y)
        r, g, b = r + ((c >> 16) & 255), g + ((c >> 8) & 255), b + (c & 255)
    return "magenta" if min(r, b) > g else "green"


def chroma_key(src: QImage, key: str | None = None) -> QImage:
    """초록(또는 자홍) 배경을 투명하게. 캐릭터 안의 같은 계열 색(사쿠야의 초록 리본 등)은 남긴다.

    1. 그림 가장자리에서 이어진 '배경 계열' 픽셀만 배경으로 (윤곽선 안쪽의 옷·리본은 닿지 않음)
    2. 윤곽선에 갇힌 배경 틈(팔과 몸 사이 등)은 배경색과 거의 같은 '순수한 배경색'만 추가로 배경 처리
    3. 배경 바로 옆 픽셀만 색 번짐을 눌러줌 (안쪽 색은 건드리지 않음)
    초록 머리(사나에)·초록 옷(요우무) 캐릭터는 자홍 배경(#FF00FF)으로 뽑으면 된다.
    """
    src = src.convertToFormat(QImage.Format_ARGB32)
    key = key or key_color(src)
    magenta = key == "magenta"
    w, h = src.width(), src.height()
    n = w * h
    data = bytearray(bytes(src.constBits()))  # BGRA
    spill = bytearray(n)       # 배경색 성분이 나머지보다 얼마나 센지 (0~255)
    loose = bytearray(n)       # 배경이거나 배경과 섞인 가장자리일 수 있음
    bg = bytearray(n)
    for k in range(n):
        i = k * 4
        b, g, r = data[i], data[i + 1], data[i + 2]
        if magenta:                # 자홍: r·b 가 함께 세고 g 가 약함
            on, off = (r if r < b else b), g
            pure = r > 170 and b > 170 and g < 110
        else:                      # 초록: g 가 세고 r·b 가 약함
            on, off = g, (r if r > b else b)
            pure = g > 170 and r < 110 and b < 110
        sv = on - off
        if sv > 0:
            spill[k] = sv
            if on > 100 and sv > 60:
                loose[k] = 1
                if pure and sv > 120:
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

    def despill(i: int, amount: int) -> None:
        """배경색 성분만 amount 만큼 빼기."""
        if amount <= 0:
            return
        if magenta:
            data[i] -= min(amount, data[i])            # b
            data[i + 2] -= min(amount, data[i + 2])    # r
        else:
            data[i + 1] -= min(amount, data[i + 1])    # g

    # 2·3. 배경은 투명하게, 배경 바로 옆은 색 번짐만 제거
    for k in range(n):
        sv = spill[k]
        if bg[k]:
            i = k * 4
            data[i + 3] = max(0, 255 - min(255, sv * 3))
            despill(i, sv)
        elif sv > 20:
            x = k % w
            if ((k >= w and bg[k - w]) or (k + w < n and bg[k + w])
                    or (x and bg[k - 1]) or (x < w - 1 and bg[k + 1])):
                despill(k * 4, sv - 20)
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
    # 칸 구분선처럼 아주 가늘고 긴 것은 캐릭터가 아님 (라벨은 남겨 두어 잘라낼 때 지워지게)
    lines = [c for c in comps if (c[2] - c[0] + 1) <= 3 or (c[3] - c[1] + 1) > 8 * (c[2] - c[0] + 1)]
    if lines:
        print(f"선 {len(lines)}개는 캐릭터가 아니라서 무시")
        comps = [c for c in comps if c not in lines]
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


def _valleys(profile: list[int], parts: int) -> list[int]:
    """profile(줄마다 불투명 칸 수)에서 parts 등분 근처의 가장 빈 줄을 경계로 (양끝 포함)."""
    n = len(profile)
    cuts = [0]
    for i in range(1, parts):
        guess = n * i // parts
        lo, hi = max(cuts[-1] + 1, guess - n // (parts * 3)), min(n - 1, guess + n // (parts * 3))
        cuts.append(min(range(lo, hi + 1), key=lambda k: (profile[k], abs(k - guess))))
    return cuts + [n]


def grid_blobs(img: QImage, rows: int, cols: int):
    """캐릭터끼리 붙어 있어 덩어리로 못 나눌 때: rows×cols 칸으로 나눈다.
    칸 경계는 똑같이 나누지 않고 줄·칸 사이에서 가장 빈 곳으로 잡고, 칸마다 가장 큰 덩어리만 남긴다
    (경계를 넘어온 옆 캐릭터 조각은 '다른 것'으로 표시해서 tight() 가 지운다)."""
    w, h = img.width(), img.height()
    gw, gh = (w + GRID - 1) // GRID, (h + GRID - 1) // GRID
    data = bytes(img.constBits())
    stride = img.bytesPerLine()
    solid = bytearray(gw * gh)
    for gy in range(gh):
        y = min(h - 1, gy * GRID + GRID // 2)
        for gx in range(gw):
            x = min(w - 1, gx * GRID + GRID // 2)
            solid[gy * gw + gx] = data[y * stride + x * 4 + 3] > 60
    row_cuts = _valleys([sum(solid[gy * gw:(gy + 1) * gw]) for gy in range(gh)], rows)
    labels = [0] * (gw * gh)
    blobs = []
    lab = 0
    for r in range(rows):
        ya, yb = row_cuts[r], row_cuts[r + 1]
        col_cuts = _valleys([sum(solid[gy * gw + gx] for gy in range(ya, yb)) for gx in range(gw)], cols)
        for c in range(cols):
            xa, xb = col_cuts[c], col_cuts[c + 1]
            lab += 1
            # 칸 안의 덩어리들 → 가장 큰 것(과 그 10% 이상인 것)만 이 캐릭터
            comps, seen = [], set()
            for gy in range(ya, yb):
                for gx in range(xa, xb):
                    k = gy * gw + gx
                    if not solid[k] or k in seen:
                        continue
                    comp, q = [], deque([k])
                    seen.add(k)
                    while q:
                        cur = q.popleft()
                        comp.append(cur)
                        cy, cx = divmod(cur, gw)
                        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                            nx, ny = cx + dx, cy + dy
                            nk = ny * gw + nx
                            if xa <= nx < xb and ya <= ny < yb and solid[nk] and nk not in seen:
                                seen.add(nk)
                                q.append(nk)
                    comps.append(comp)
            if not comps:
                continue
            big = max(len(cp) for cp in comps)
            box = [gw, gh, -1, -1]
            for comp in comps:
                mine = len(comp) >= big * 0.1
                for k in comp:
                    labels[k] = lab if mine else -1
                    if mine:
                        cy, cx = divmod(k, gw)
                        box = [min(box[0], cx), min(box[1], cy), max(box[2], cx), max(box[3], cy)]
            blobs.append(((box[0] * GRID, box[1] * GRID, min(w, (box[2] + 1) * GRID), min(h, (box[3] + 1) * GRID)), lab))
    return blobs, labels, gw


def tight(img: QImage, blob, labels, gw) -> tuple[QImage, float, int]:
    """상자 안에서 이 캐릭터 픽셀만 남겨(옆 캐릭터 조각은 지움) 딱 맞게 자르고,
    머리 무게중심 x(잘린 그림 기준)를 돌려준다."""
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
    # 기준 x = 머리(윗부분) 무게중심. 몸 전체로 잡으면 다리를 내밀 때마다 중심이 앞으로 가서
    # 걸을 때 몸이 앞뒤로 흔들려 보인다. 머리는 걸어도 거의 제자리라 이쪽이 자연스럽다.
    band0, band1 = miny + int((maxy - miny) * 0.12), miny + int((maxy - miny) * 0.55)
    sx = sa = 0
    for y in range(band0, band1 + 1):
        row = y * stride
        for x in range(minx, maxx + 1):
            a = data[row + x * 4 + 3]
            if a > 60:
                sx += x * a
                sa += a
    clean = QImage(bytes(data), w, h, stride, QImage.Format_ARGB32).copy()
    out = clean.copy(minx, miny, maxx - minx + 1, maxy - miny + 1)
    return out, (sx / max(1, sa)) - minx, y0 + maxy   # 마지막: 시트에서 발(맨 아래)의 y


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sheet", type=Path)
    ap.add_argument("character", help="캐릭터 키 (reimu, marisa, ...)")
    ap.add_argument("--names", help="찾은 순서대로 붙일 프레임 이름, 쉼표로 구분")
    ap.add_argument("--preset", choices=sorted(PRESETS),
                    help="표준 세트 시트의 이름을 자동으로 (move / react / life / walk). --append 도 자동으로 켜짐")
    ap.add_argument("--grid", help="행x열 (예: 3x4). 캐릭터끼리 붙어 있으면 칸으로 똑같이 잘라서 나눔")
    ap.add_argument("--append", action="store_true",
                    help="기존 그림을 지우지 않고 추가 (같은 이름은 덮어씀) — 시트 여러 장을 합칠 때")
    args = ap.parse_args()
    global _qt_app  # QImage 스케일링·글꼴에 필요, 끝날 때까지 살아 있어야 함
    _qt_app = QGuiApplication.instance() or QGuiApplication(sys.argv)

    src = QImage(str(args.sheet))
    if src.isNull():
        print(f"그림을 읽지 못했습니다: {args.sheet}")
        return 1
    keyed = chroma_key(src)
    if args.preset:
        args.names = args.names or ",".join(PRESETS[args.preset])
        args.append = True
    wanted = [n.strip() for n in args.names.split(",")] if args.names else None
    if args.grid:
        rows, cols = (int(v) for v in args.grid.lower().split("x"))
        blobs, labels, gw = grid_blobs(keyed, rows, cols)
    else:
        blobs, labels, gw = find_blobs(keyed, expected=len(wanted) if wanted else None)
    print(f"캐릭터 {len(blobs)}개 찾음")
    if args.preset and not PRESETS[args.preset]:          # 장수 자유 프리셋
        wanted = [f"{REPLACE_PREFIX[args.preset]}{i}" for i in range(len(blobs))]
        args.names = ",".join(wanted)
    names = wanted or [f"frame_{i + 1}" for i in range(len(blobs))]
    if len(names) != len(blobs):
        print(f"이름 {len(names)}개와 찾은 캐릭터 {len(blobs)}개의 수가 다릅니다. 미리보기를 보고 다시 지정하세요.")
        names = [f"frame_{i + 1}" for i in range(len(blobs))]
        args.names = None

    frames = [tight(keyed, b, labels, gw) for b in blobs]
    lifts = _lifts(frames, names)          # 점프 높이는 빼는 장면까지 포함한 같은 줄 기준으로
    keep = [i for i, n in enumerate(names) if n != "-"]   # 이름이 - 인 장면은 버림
    if len(keep) != len(names):
        print(f"{len(names) - len(keep)}개 장면은 빼고 저장")
    frames, names, lifts = [frames[i] for i in keep], [names[i] for i in keep], [lifts[i] for i in keep]
    for name, lift in zip(names, lifts):
        if lift:
            print(f"  {name}: 바닥에서 {lift / frames[0][0].height() * 100:.0f}% 떠 있음 (점프 유지)")
    # 걷기 그림 중 AI가 유난히 크게/작게 그린 장면은 중앙값 ±3% 안으로 (걸을 때 몸이 커졌다 작아지는 것 방지,
    # 몸이 살짝 오르내리는 정도의 차이는 남김)
    fix = [1.0] * len(frames)
    walk_h = sorted(frames[i][0].height() for i, n in enumerate(names) if n.startswith("walk"))
    if walk_h:
        med = walk_h[len(walk_h) // 2]
        for i, n in enumerate(names):
            h = frames[i][0].height()
            if n.startswith("walk") and not med * 0.97 <= h <= med * 1.03:
                fix[i] = min(max(h, med * 0.97), med * 1.03) / h
                print(f"  {n}: 다른 걷기 장면보다 {(h / med - 1) * 100:+.0f}% 커서 맞춤")
    # 크기 기준: 서 있는 그림(idle / idle_0). 없으면(걷기 시트) 걷기 중앙값이 서 있는 키의 98.5%가 되게
    ref = next((names.index(n) for n in ("idle", "idle_0") if n in names), None)
    if ref is not None:
        scale = STANDING_PX / frames[ref][0].height()
    elif walk_h:
        scale = STANDING_PX * 0.985 / walk_h[len(walk_h) // 2]
    else:
        scale = STANDING_PX / max(img.height() for img, _, _ in frames)

    out_dir = SPRITES / args.character
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    anchors: dict[str, list[float]] = {}
    sources: list[str] = []
    if args.append and manifest_path.exists():
        anchors, sources = _load_anchors(manifest_path)
        prefix = REPLACE_PREFIX.get(args.preset or "")
        if prefix:
            for old in [n for n in anchors if n.startswith(prefix)]:
                anchors.pop(old)
                (out_dir / f"{old}.png").unlink(missing_ok=True)
    else:
        for old in out_dir.glob("*.png"):
            old.unlink()

    # 그림마다 딱 맞는 캔버스 + 발 위치(몸 무게중심 x, 바닥 y)를 따로 저장
    for (img, cx, _), name, lift, f in zip(frames, names, lifts, fix):
        sc = scale * f
        tw, th = img.width() * sc, img.height() * sc
        lift *= scale                                         # 점프 높이 (바닥선 위로)
        ax = int(max(cx * sc, tw - cx * sc)) + PAD            # 무게중심 좌우로 같은 폭
        canvas = QImage(ax * 2, int(th + lift) + PAD * 2, QImage.Format_ARGB32_Premultiplied)
        canvas.fill(Qt.transparent)
        p = QPainter(canvas)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        ay = canvas.height() - PAD
        p.drawImage(QRectF(ax - cx * sc, ay - lift - th, tw, th), img)
        p.end()
        canvas.save(str(out_dir / f"{name}.png"))
        anchors[name] = [ax, ay]
    walk_cycles = _count_walk_cycles(out_dir, anchors) if args.preset == "walk" else None
    if walk_cycles is None and manifest_path.exists():
        walk_cycles = json.loads(manifest_path.read_text(encoding="utf-8")).get("walk_cycles")
    if args.names:
        sources.append(args.sheet.name)
        manifest = {"version": 2, "standing_height": STANDING_PX, "facing": 1,
                    "frames": anchors, "sources": sources}
        if walk_cycles:
            manifest["walk_cycles"] = walk_cycles
            print(f"  걷기 한 벌에 걸음 {walk_cycles}바퀴")
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    _save_preview(out_dir, names, anchors)
    print(f"저장: {out_dir}")
    if not args.names:
        print("미리보기(_preview.png)를 보고 --names 로 이름을 붙여 다시 실행하세요.")
    return 0


def _lifts(frames, names) -> list[float]:
    """같은 줄에서 다른 그림보다 발이 떠 있는 만큼(점프). 시트 픽셀 단위.

    AI가 바닥선을 완벽히 맞추진 못하므로 키의 4% 미만 차이는 무시하고(떨림 방지),
    원래 공중에 있는 자세(held, fall)는 제외한다."""
    bottoms = [b for _, _, b in frames]
    heights = [img.height() for img, _, _ in frames]
    med_h = sorted(heights)[len(heights) // 2]
    lifts = []
    for i, name in enumerate(names):
        if name.startswith(("held", "fall")):
            lifts.append(0.0)
            continue
        # 같은 줄 = 발 위치가 키의 절반 이내로 비슷한 그림들 (위아래 줄은 키만큼 떨어져 있음)
        row = [b for b in bottoms if abs(b - bottoms[i]) < med_h * 0.5]
        lift = max(row) - bottoms[i]
        lifts.append(float(lift) if lift >= med_h * 0.04 else 0.0)
    return lifts


def _count_walk_cycles(out_dir: Path, anchors: dict) -> int:
    """걷기 그림들의 발 벌림(발 근처 가로 폭)을 보고, 발을 크게 벌린 장면 묶음 수 = 발짝 수.
    두 발짝이 걸음 한 바퀴. AI 가 한 벌을 부탁했는데 두 벌을 그려 오는 일이 있어서 센다."""
    walks = sorted((n for n in anchors if n.startswith("walk_")), key=lambda n: int(n[5:]))
    spreads = []
    for n in walks:
        img = QImage(str(out_dir / f"{n}.png")).convertToFormat(QImage.Format_ARGB32)
        ay, w = int(anchors[n][1]), img.width()
        xs = [x for y in range(max(0, ay - 22), ay) for x in range(w) if (img.pixel(x, y) >> 24) > 100]
        spreads.append(max(xs) - min(xs) if xs else 0)
    if len(spreads) < 4:
        return 1
    mid = (min(spreads) + max(spreads)) / 2
    wide = [v > mid for v in spreads]
    steps = sum(1 for i in range(len(wide)) if wide[i] and not wide[i - 1]) or 1   # 벌린 묶음 수 (처음·끝 이어짐)
    return max(1, round(steps / 2))


def _load_anchors(path: Path) -> tuple[dict[str, list[float]], list[str]]:
    """manifest 의 그림별 발 위치. 예전 형식(모든 그림이 같은 캔버스·발 위치)도 읽는다."""
    m = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(m.get("frames"), dict):
        return dict(m["frames"]), list(m.get("sources", []))
    return {n: list(m["anchor"]) for n in m["frames"]}, [m["source"]] if m.get("source") else []


def _save_preview(out_dir: Path, names: list[str], anchors: dict[str, list[float]]) -> None:
    """이번에 넣은 그림들을 같은 바닥선·가운데선에 맞춰 번호와 함께 (정렬 확인용)."""
    imgs = [QImage(str(out_dir / f"{n}.png")) for n in names]
    left = max(anchors[n][0] for n in names)
    right = max(img.width() - anchors[n][0] for n, img in zip(names, imgs))
    up = max(anchors[n][1] for n in names)
    down = max(img.height() - anchors[n][1] for n, img in zip(names, imgs))
    cell_w, cell_h = int(left + right) + 10, int(up + down) + 28
    cols = min(6, len(names))
    rows = (len(names) + cols - 1) // cols
    prev = QImage(cell_w * cols, cell_h * rows, QImage.Format_ARGB32)
    prev.fill(QColor("#EDE6EA"))
    p = QPainter(prev)
    p.setFont(QFont("Malgun Gothic", 10))
    for i, (name, img) in enumerate(zip(names, imgs)):
        ox, oy = (i % cols) * cell_w + 5 + left, (i // cols) * cell_h + 4 + up   # 이 칸의 발 위치
        p.setPen(QColor(200, 16, 46, 120))
        p.drawLine(QPointF(ox - left, oy), QPointF(ox + right, oy))       # 바닥선
        p.drawLine(QPointF(ox, oy - up), QPointF(ox, oy + down))          # 가운데
        ax, ay = anchors[name]
        p.drawImage(QPointF(ox - ax, oy - ay), img)
        p.setPen(QColor("#2B1D21"))
        p.drawText(QRectF(ox - left, oy + down + 2, cell_w - 10, 20), Qt.AlignCenter, f"{i + 1}. {name}")
    p.end()
    prev.save(str(out_dir / "_preview.png"))


if __name__ == "__main__":
    sys.exit(main())
