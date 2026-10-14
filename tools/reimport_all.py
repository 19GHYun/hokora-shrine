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
    "props": [("item1.png", "sakura,lantern,fox,omikuji_rack,ema_rack,umbrella,temizuya,furin,saisen_box", True),
              ("1.png", "kadomatsu,snowman,xmas_tree,hina,koinobori,tanabata,sunflower,tsukimi,pumpkin", False),
              ("mistia_item.png", "yatai", False),
              ("item.png", "pond,taiko,bamboo_fence,maneki_neko,yukimi_lantern,maple,suzu,mini_torii,incense --grid 3x3 --keep 0.04", False)],
    "shrines": [("2.png", "moriya,snowy,sakura,scarlet --grid 2x2", True)],
    # 니토리: 다시 넣으면 몇 컷의 모자 위에 위 칸 장화 끝이 붙어 들어옴 → 맨 위 몇 줄을 지워야 함
    "nitori": [("3_1_1.png", GUEST + " --grid 3x4", True)],
    "tewi": [("3_3_1.png", GUEST + " --grid 3x4", True)],
    "youmu": [("youmu_1.png", "preset:move", True),
              ("youmu_2.png", "sit_0,-,fall,happy_0,happy_1,happy_2,happy_3,held_0,held_1,held_2", False),
              ("youmu_3.png", "preset:life --grid 3x3", False),
              ("youmu_5.png", "preset:walk", False),
              ("youmu_6.png", "sit_0,sit_1", False)],
    "meiling": [("5..png", "preset:move --grid 3x3", True), ("6.png", "preset:react", False),
                ("7.png", "preset:life --grid 3x3 --keep 0.03", False), ("8.png", "preset:walk --star", False)],
    "reisen": [("10-a.png", "idle_0,idle_1,blink,bow,walk_0,walk_1 --grid 2x3", True),
               ("10-b.png", "walk_2,walk_3,skill_0,-,skill_1,caught,-,happy --grid 2x4 --keep 0.02", False)],
    # 할로윈 의상: 마녀 레이무는 다시 넣은 뒤 walk_1 발밑(아래 칸 모자 끝)을 손으로 지우고, skill_1 만 --keep 0.03 판으로 바꿔야 함
    "reimu@witch": [("1-b.png", "preset:outfit --grid 3x4", True)],
    "sanae@pumpkin": [("2-b.png", "preset:outfit --grid 3x4 --keep 0.03", True)],
    "cirno@obake": [("3-b.png", "preset:outfit --grid 3x4", True)],
    # 크리스마스 의상·손님 유카리·파츄리 (1-b 는 칸 줄이 있는 시트 — 연두색이라 배경 지우기로 같이 지워짐)
    "sakuya@santa": [("1-b.png", "preset:outfit --grid 3x4 --keep 0.03", True)],
    "flandre@reindeer": [("2-b.png", "preset:outfit --grid 3x4 --keep 0.02", True)],
    "marisa@gift": [("3-b.png", "preset:outfit --grid 3x4 --keep 0.03", True)],
    "yukari": [("4-b.png", "preset:guest --grid 3x4 --keep 0.02", True)],
    "patchouli": [("5-b.png", "preset:guest --grid 3x4 --keep 0.01", True)],
    "fish": [("fish.png", "medaka,funa,goldfish,koi,catfish,eel,can,boot,coins,cucumber,tamatebako,golden_koi --grid 3x4 --keep 0.03", True)],
    "yuyuko": [("yuyuko_1.png", GUEST + " --grid 3x4", True)],
    "mystia": [("mistia_1.png", GUEST + " --grid 3x4", True)],
    "koishi": [("3_2_1.png", "idle_0,idle_1,blink,bow,-,walk_0,walk_1,walk_2,walk_3,skill_0,skill_1,caught,happy", True)],
    # 공물·답례품 아이콘 (공물 시트는 ✦ 가 공물상 위에 있어서 --star)
    "items": [("111.png", "offer_konpeito,offer_scoop,offer_sake,offer_carrot,offer_rose,offer_cucumber,offer_onigiri,"
                          "offer_score,offer_dango,offer_grimoire,offer_inari,offer_sanbo --grid 3x4 --keep 0.03 --star", True),
              ("222.png", "gift_fairies,gift_aya,gift_suika,gift_tewi,gift_koishi,gift_nitori,gift_yuyuko,gift_mystia,"
                          "gift_reisen,gift_patchouli,gift_yukari --grid 3x4 --keep 0.03", False)],
    # 누에: --keep 0.02 로 특기 컷의 작은 UFO 를 살림. 다시 넣은 뒤 happy 오른팔의 ✦ 자국(회색)을 소매색으로 칠하고
    # 초록 테두리를 빼야 함 (g > max(r, b) + 18 → g = max(r, b))
    "nue": [("444.png", "preset:guest --grid 3x4 --keep 0.02", True)],
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
