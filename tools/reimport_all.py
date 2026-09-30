# -*- coding: utf-8 -*-
"""지금까지 받은 스프라이트 시트를 처음부터 다시 가져온다 (가져오기 방식을 고쳤을 때).

  python tools/reimport_all.py [시트 폴더]      기본: ~/Downloads

캐릭터마다 시트를 넣은 순서·이름을 그대로 적어 둔 목록. 새 시트를 넣으면 여기에도 추가한다.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIRST = "idle,blink,walk_0,walk_1,sit,happy,held,sit_1,happy_1,fall,sleep"
MOVE_A = "idle_0,idle_1,blink,walk_0,walk_1,walk_2,walk_3,walk_4,walk_5"
WALK6 = "walk_0,walk_1,walk_2,walk_3,walk_4,walk_5"
IDLE_HAPPY_HELD = "idle_0,idle_1,blink,happy_0,happy_1,happy_2,happy_3,held_0,held_1,held_2"
REACT = "sit_0,sit_1,fall,happy_0,happy_1,happy_2,happy_3,held_0,held_1,held_2"

# (캐릭터, [(시트 파일, "names" 또는 "preset:이름", 새로 시작?)])
# how: "이름,이름,…" 또는 "preset:이름". 뒤에 " --옵션 값" 을 붙이면 그대로 넘김 (예: " --grid 3x4")
GUEST = "idle_0,idle_1,blink,bow,walk_0,walk_1,walk_2,walk_3,skill_0,skill_1,caught,happy"
PLAN = {
    "reimu": [("Gemini_Generated_Image_ftv5b5ftv5b5ftv5.png",
               "idle,blink,walk_0,walk_1,sit,happy,held,sit_1,idle_1,fall,sleep", True),
              ("Gemini_Generated_Image_b50spdb50spdb50s.png", WALK6, False),
              ("Gemini_Generated_Image_8xy8cg8xy8cg8xy8.png", IDLE_HAPPY_HELD, False),
              ("reimu3.png", "preset:life", False),
              ("reimu_run.png", "preset:walk", False)],
    "marisa": [("Gemini_Generated_Image_u1flfzu1flfzu1fl.png", FIRST, True),
               ("marisa1.png", WALK6, False), ("marisa2.png", IDLE_HAPPY_HELD, False),
               ("marisa3.png", "preset:life", False),
               ("marisa_run2.png", "preset:walk --walk-cycles 2", False)],
    "sakuya": [("Gemini_Generated_Image_w9b67cw9b67cw9b6.png", FIRST, True),
               ("sakuya1.png", WALK6, False),
               ("sakuya2.png", "idle_0,idle_1,blink,happy_0,-,happy_1,happy_2,-,held_0,held_1", False),
               ("sakuya3.png", "preset:life", False),
              ("sakuya_run.png", "preset:walk", False)],
    "cirno": [("Gemini_Generated_Image_yizj9yizj9yizj9y.png", FIRST, True),
              ("cirno1.png", WALK6, False), ("cirno2.png", IDLE_HAPPY_HELD, False),
              ("chirno3.png", "preset:life", False),
              ("cirno_run.png", "preset:walk", False)],
    "sanae": [("sanae2.png", MOVE_A, True), ("sanae3.png", REACT, False), ("sanae4.png", "preset:life", False),
                ("sanae_run.png", "preset:walk", False)],
    "flandre": [("flan2.png", MOVE_A, True),
                ("flan3.png", "sit_0,sit_1,fall,happy_0,happy_1,happy_2,happy_3,-,held_1,held_2", False),
                ("flan4.png", "preset:life", False),
                ("flan_run.png", "preset:walk", False)],
    "remilia": [("remil2.png", MOVE_A, True), ("remil3.png", REACT, False), ("remil4.png", "preset:life", False),
                ("remil_run.png", "preset:walk", False)],
    "sunny": [("sunnymilk2.png", GUEST + " --grid 3x4", True)],
    "luna": [("lunachild2.png", GUEST, True)],
    "star": [("starsapphire2.png", GUEST, True)],
    "aya": [("Aya2.png", GUEST, True)],
    "suika": [("suika2.png", GUEST + " --grid 3x4", True)],
    "props": [("item1.png", "sakura,lantern,fox,omikuji_rack,ema_rack,umbrella,temizuya,furin,saisen_box", True)],
}


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Downloads"
    only = sys.argv[2:] or list(PLAN)
    for key in only:
        for sheet, how, fresh in PLAN[key]:
            path = src / sheet
            if not path.exists():
                print(f"[{key}] 시트 없음 — 건너뜀: {path}")
                continue
            cmd = [sys.executable, str(ROOT / "tools" / "import_sheet.py"), str(path), key]
            how, *extra = how.split(" ")
            if how.startswith("preset:"):
                cmd += ["--preset", how.split(":", 1)[1]]
            else:
                cmd += ["--names", how] + ([] if fresh else ["--append"])
            cmd += extra
            print(f"[{key}] {sheet}", flush=True)
            if subprocess.call(cmd) != 0:
                print(f"[{key}] 실패: {sheet}")
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
