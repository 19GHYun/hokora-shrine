# -*- coding: utf-8 -*-
"""Hokora 전체 기능을 한 번에 돌려 보는 연기(smoke) 시험.

    python tests/smoke.py

- 저장은 임시 폴더(APPDATA)에, 사진은 임시 폴더에 — 진짜 저장·사진 폴더·클립보드는 건드리지 않는다.
- 마우스는 가짜 커서, 자리 비움(낮잠)은 끔.
- 실제로 창을 띄우므로 2분쯤 화면 아래에서 캐릭터들이 움직인다.
끝나면 통과/실패를 출력하고, 실패가 있으면 종료 코드 1.
"""
from __future__ import annotations

import os
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="hokora_smoke_"))
os.environ.update(APPDATA=str(TMP / "appdata"), HOKORA_ALL="1", HOKORA_NAP_AFTER="999999",
                  HOKORA_SEASON="summer", HOKORA_NIGHT="0")
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hokora import app as hk  # noqa: E402
from hokora import affection as aff  # noqa: E402
from hokora import daily, guests, omamori, photo, play, prayer, torii, wardrobe  # noqa: E402
from hokora import events as hk_events  # noqa: E402
from hokora.events import SKILL_COOLDOWN  # noqa: E402

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)


class FakeCursor:
    @staticmethod
    def pos():
        return QPoint(10, 10)


hk.QCursor = FakeCursor
hk.winutil.left_button_down = lambda: False
hk.winutil.idle_seconds = lambda: 0.0
photo.photo_dir = lambda: TMP / "photos"
photo.to_clipboard = lambda img: None
play.TAG_TIME, play.DUEL_TIME = 4.0, 2.0
guests.FAIRY_PRANK, guests.SUIKA_STAY = 6.0, (4.0, 4.0)

game = hk.Game(app)
game.start()
s = game.state
s.unlocked = ["reimu", "marisa", "cirno", "sakuya", "sanae", "remilia", "flandre"]
P = {p.ch.key: p for p in game.pets}
ev = game.events
ev._play_next = ev._thief_next_check = time.monotonic() + 1e9     # 저절로 생기는 일은 막고 시험에서만
ev._skill_at = {k: time.monotonic() for k in SKILL_COOLDOWN}     # 특기도 시험에서만 (시간 정지가 끼어들지 않게)
game.visits._next = time.monotonic() + 1e9
RESULTS: list[tuple[str, bool, str]] = []
G: dict = {}


def check(name: str, ok: bool, detail: object = "") -> None:
    RESULTS.append((name, bool(ok), str(detail)))
    print(("  ok  " if ok else "  FAIL") + f"  {name}  {detail}", flush=True)


def ground():
    return game.ground_under(game.shrine.pos_x)


def place(pet, x: float) -> None:
    g = ground()
    pet.pos_x, pet.pos_y, pet.on, pet._on_left = x, g.y, g.hwnd, g.win_left
    pet.state, pet.vx, pet.vy, pet.scripted = "idle", 0.0, 0.0, False
    pet.state_until = time.monotonic() + 999
    pet._place()


def calm() -> None:
    """다들 신사 근처에 줄 세우고 스스로 움직이지 않게."""
    for c in list(game._card_queue):
        c.close()
    for i, p in enumerate(game.pets):
        place(p, ground().x1 + 120 + i * 110)
        p._choose_next = lambda: None
        p.frozen_until = 0.0                       # 사쿠야 시간 정지가 걸려 있으면 풂


# ── 단계들 (함수, 다음 단계까지 기다릴 ms) ──
def t_core():
    calm()
    r = P["reimu"]
    before = s.saisen
    r.last_reward = 0
    game.on_pat(r)
    check("쓰다듬기 새전", s.saisen > before, s.saisen - before)
    m = P["marisa"]
    m.state, m.on, m.vx, m.vy = "fall", None, 300.0, -700.0
    m.pos_y -= 300


def t_core2():
    m = P["marisa"]
    check("던지면 착지", m.on is not None and m.state not in ("fall", "jump"), (m.state, m.on))
    game.save()
    check("저장 파일", (TMP / "appdata" / "Hokora" / "save.json").exists())
    calm()
    s.saisen = 1000
    hk_events.GUARD_CHANCE = 0.0                    # 메이링 문지기는 따로 시험
    place(P["marisa"], game.shrine.pos_x + 60)
    check("새전 도둑 출발", ev.start_thief(force=True))


def t_thief():
    check("도둑질 중", ev.thief_phase in ("steal", "flee"), ev.thief_phase)
    stolen = ev.stolen
    before = s.saisen
    game.on_pat(P["marisa"])
    check("도둑 붙잡으면 돌려받고 보너스", s.saisen >= before + stolen and ev.thief is None, (stolen, s.saisen - before))
    calm()
    ev._skill_at.clear()
    check("사쿠야 특기", ev.try_skill(P["sakuya"]))


def t_skill():
    frozen = [p.ch.key for p in game.pets if p.frozen_until > time.monotonic()]
    check("시간 정지로 멈춤", len(frozen) >= 3, frozen)
    for p in game.pets:
        p.frozen_until = 0.0
    s.saisen = 5000
    inc = s.income_per_min
    game.on_decor("fox", "buy")
    check("장식 사서 놓기", "fox" in game.decors and s.income_per_min == inc + 1, s.income_per_min - inc)
    game.on_decor("fox", "remove")
    check("장식 치우기", "fox" not in game.decors)
    game.pray("prosper")
    game.pray("bond")
    game.pray("charm")
    check("번영 기원 수입 2배", prayer.income_multiplier(s) == 2.0, prayer.income_multiplier(s))
    check("인연 기원 쓰다듬기 5배", prayer.pat_multiplier(s) == 5)
    check("도둑 방지 부적", prayer.charm_active(s))
    s.buff_income_until = s.buff_pat_until = s.charm_until = 0.0
    r = P["reimu"]
    a0 = G["a0"] = aff.points(s, "reimu")
    game.talk_to(r)
    game.talk_to(r)
    game.give_gift(r, "tea")
    check("선물 (좋아하는 것 +8)", aff.points(s, "reimu") == a0 + 8, aff.points(s, "reimu") - a0)


def t_aff():
    check("말 걸기는 하루 한 번 +2", aff.points(s, "reimu") == G["a0"] + 10, aff.points(s, "reimu") - G["a0"])
    calm()
    check("술래잡기 시작", ev.start_play("tag"))


def t_tag():
    check("술래잡기 끝", ev.tag is None and not any(p.scripted for p in game.pets),
          (ev.tag is not None, [p.ch.key for p in game.pets if p.scripted]))
    calm()
    check("탄막놀이 시작", ev.start_play("duel"))


def t_duel():
    check("탄막놀이 끝", ev.duel is None and not any(p.scripted for p in game.pets))
    calm()
    s.saisen = 1000
    s.shrine_level = 1
    game.shrine.set_level(1)
    check("세 요정 방문", game.visits.start("fairies"))


def t_fairies():
    v = game.visits.visit
    check("요정 장난 중", v is not None and v.phase == "prank", v.phase if v else None)
    if v is not None:
        game.on_pat(v.sunny.pet)
        check("서니 붙잡기", v.sunny.caught)


def t_fairies2():
    check("요정들 돌아감", game.visits.visit is None)
    check("붙잡은 요정 수", s.fairies_caught >= 1, s.fairies_caught)
    calm()
    s.shrine_level = 2
    game.shrine.set_level(2)
    check("아야 방문", game.visits.start("aya"))


def t_aya():
    check("아야 취재 끝", game.visits.visit is None)
    check("붕붕마루 신문 호외", len(s.news) >= 1 and prayer.news_active(s), s.news[-1:] if s.news else None)
    s.news_until = 0.0
    calm()
    s.shrine_level = 3
    game.shrine.set_level(3)
    check("스이카 방문", game.visits.start("suika"))
    QTimer.singleShot(1500, lambda: game.visits.visit and game.visits.visit.treat())


def t_suika():
    check("스이카가 새전을 두고 감 (대접)", game.visits.visit is None and s.suika_saisen > 0, s.suika_saisen)
    calm()
    s.daily_tasks = [{"kind": "pat", "goal": 2, "count": 0, "reward": 20, "done": False},
                     {"kind": "throw", "goal": 1, "count": 0, "reward": 20, "done": False},
                     {"kind": "photo", "goal": 1, "count": 0, "reward": 20, "done": False}]
    check("출석 도장", s.attend_streak >= 1 and s.attend_last == daily.today(), s.attend_streak)
    r = P["reimu"]
    for _ in range(2):
        r.last_reward = 0
        game.on_pat(r)
    game.on_thrown(r, 900)
    game._shoot()
    check("오늘의 부탁 셋 다", all(t["done"] for t in s.daily_tasks))
    check("사진 저장", len(list((TMP / "photos").glob("*.png"))) == 1)
    for c in list(game._card_queue):
        c.close()
    for kind, want in (("spring", "petal"), ("autumn", "leaf"), ("winter", "snow")):
        os.environ["HOKORA_SEASON"] = kind
        game._refresh_season()
        check(f"계절 연출 {kind}", game.fx.kind == want and game.fx.isVisible(), game.fx.kind)
    os.environ["HOKORA_SEASON"], os.environ["HOKORA_NIGHT"] = "summer", "1"
    game._refresh_season()
    check("여름밤 반딧불·신사 불빛", game.fx.kind == "firefly" and game.shrine.night)
    os.environ["HOKORA_NIGHT"] = "0"
    game._refresh_season()


def t_shop():
    s.saisen = 10 ** 7
    s.shrine_level = 5
    game.shrine.set_level(s.look_stage)
    check("센본토리이 10개 → 칭호", game.on_action("torii", 10) == ["참배길"] and game.torii_row.isVisible(), s.torii)
    check("도리이 수입", torii.income(s) == 5)
    res = game.on_action("pull", 10)
    check("부적 10번 뽑기 (귀함 이상 보장)", len(res) == 10 and any(omamori.CHARMS[k].rarity in ("SR", "SSR") for k, _ in res))
    check("부적 지니기 3칸", len(s.equipped) <= omamori.SLOTS and len(s.equipped) >= 1, s.equipped)
    res = game.on_action("wpull", 10)
    check("의상실 10번 뽑기", len(res) == 10 and any(wardrobe.ITEMS[k].rarity in ("SR", "SSR") for k, _ in res))
    s.wardrobe = list(wardrobe.ITEMS)
    for k, sk in (("reimu", "blue"), ("marisa", "neon"), ("cirno", "pixel"), ("sakuya", "gold")):
        check(f"옷 입히기 {k} {sk}", game.on_action("wear", (k, sk)) and P[k].skin == sk)
    check("이펙트", game.on_action("wfx", ("reimu", "hearts")) and P["reimu"].fx_kind == "hearts")
    s.wardrobe = []
    s.cloth = 40
    check("옷감 교환", game.on_action("exchange", "reimu:black") and s.cloth == 10)
    w0 = game.shrine.width()
    game.on_action("look", 2)
    check("신사 모양 2단계", s.look_stage == 2 and game.shrine.width() < w0, (w0, game.shrine.width()))
    game.on_action("scale", 0.7)
    check("크기 작게", game.shrine.width() < 170)
    game.on_action("scale", 1.0)
    game.on_action("out", ("cirno", False))
    check("친구 쉬게 하기", "cirno" not in [p.ch.key for p in game.pets])
    game.on_action("out", ("cirno", True))
    check("다시 내보내기", "cirno" in [p.ch.key for p in game.pets])
    for tab in range(8):
        game._panel_tab = tab
        game.open_panel()
        app.processEvents()
        game.panel.close()
    check("신사 관리 창 탭 8개 열기", True)


def t_season_shop():
    from hokora.state import SEASONAL, in_season
    now_key = next(k for k in SEASONAL if in_season(k))
    off_key = next(k for k in SEASONAL if not in_season(k))
    s.saisen = 10 ** 7
    game.on_decor(off_key, "buy")
    check("철 지난 계절 장식은 못 삼", off_key not in s.decor_owned, off_key)
    game.on_decor(now_key, "buy")
    check("이번 달 계절 장식", now_key in s.decor_owned and now_key in game.decors, now_key)
    check("신사 스킨 사기", game.on_action("shrine_skin", "moriya") and game.shrine.skin == "moriya")
    check("신사 스킨 벗기", game.on_action("shrine_skin", "moriya") and game.shrine.skin is None)
    calm()
    check("테위 방문", game.visits.start("tewi"))


def t_tewi():
    v = game.visits.visit
    check("테위가 함정 팜", v is not None and v.pit_x is not None, v.phase if v else None)
    s.fate_boost = False
    if v is not None:
        game.on_pat(v.tewi.pet)
    check("테위 쓰다듬기 → 오미쿠지 행운", s.fate_boost and s.tewi_luck >= 1)
    if game.visits.visit:
        game.visits.visit.cancel()


def t_koishi():
    check("코이시 방문", game.visits.start("koishi"))
    v = game.visits.visit
    check("코이시는 거의 투명", v is not None and v.koishi.pet.windowOpacity() < 0.3)
    if v is not None:
        game.on_pat(v.koishi.pet)
    check("코이시 찾기", s.koishi_found == 1)


def t_nitori():
    check("코이시 돌아감", game.visits.visit is None)
    calm()
    check("니토리 방문", game.visits.start("nitori"))


def t_nitori2():
    v = game.visits.visit
    check("니토리 노점", v is not None and v.phase == "shop", v.phase if v else None)
    if v is not None:
        key = v.goods[0]
        check(f"니토리 물건 사기 ({key})", v.buy(key) and key in v.sold)
        v.cancel()


def t_yuyuko():
    calm()
    s.saisen = 10 ** 7
    s.yuyuko_fed = 2
    check("유유코 방문", game.visits.start("yuyuko"))
    v = game.visits.visit
    if v is not None:
        check("유유코 대접 (도시락)", v.feed("bento") and v.full == 60)
        v.feed("bento")
        check("유유코 배부름", v.phase == "full", v.full)


def t_yuyuko2():
    check("유유코 3번 → 요우무 해금", s.yuyuko_fed == 3 and "youmu" in s.unlocked, (s.yuyuko_fed, "youmu" in s.unlocked))
    if game.visits.visit:
        game.visits.visit.cancel()


def t_mystia():
    calm()
    check("미스티아 방문 (포장마차)", game.visits.start("mystia") and game.visits.visit.stall is not None)


def t_mystia2():
    v = game.visits.visit
    a0 = aff.points(s, "reimu")
    if v is not None:
        check("장어구이 → 수입 ×1.3", v.buy("kabayaki") and prayer.eel_active(s))
        check("오뎅 → 호감도 +2", v.buy("oden") and aff.points(s, "reimu") == a0 + 2)
        v.cancel()
    calm()
    ev._skill_at.clear()
    G["s_y"] = s.saisen
    youmu = next((p for p in game.pets if p.ch.key == "youmu"), None)
    check("요우무 특기", youmu is not None and ev.try_skill(youmu))


def t_youmu():
    check("요우무 정원 손질 새전", s.saisen > G["s_y"], s.saisen - G["s_y"])


def t_meiling():
    calm()
    s.saisen = 5000
    hk_events.GUARD_CHANCE = 1.0
    me = P["meiling"]
    place(P["marisa"], game.shrine.pos_x + 200)
    place(me, game.shrine.pos_x + 120)
    blocks = s.meiling_blocks
    ev.start_thief(force=True)
    ev._thief_tick()
    check("메이링이 새전 도둑 막기", ev.thief is None and s.meiling_blocks == blocks + 1)
    # 졸고 있으면 못 막음
    calm()
    ev._doze_at = 0.0
    ev._meiling_tick()
    check("메이링 졸기", P["meiling"].state == "sleep")
    place(P["marisa"], game.shrine.pos_x + 200)
    P["meiling"].state, P["meiling"].state_until = "sleep", float("inf")
    ev.start_thief(force=True)
    ev._thief_tick()
    check("졸면 도둑을 못 막음", ev.thief is not None and ev.thief_phase == "approach")
    ev.cancel_thief()
    game.on_pat(P["meiling"])
    ev._meiling_tick()
    check("쓰다듬으면 깸", P["meiling"].state != "sleep" and not ev._doze_until)
    hk_events.GUARD_CHANCE = 0.7
    # 정원 장식·할로윈 의상
    s.saisen = 10 ** 7
    game.on_decor("maneki_neko", "buy")
    check("정원 장식 (마네키네코)", "maneki_neko" in game.decors)
    ev_items = wardrobe.event_items(s)
    check("10월 한정 할로윈 의상", len(ev_items) == 3 if time.localtime().tm_mon == 10 else len(ev_items) == 0,
          [it.id for it in ev_items])
    s.wardrobe.append("reimu:witch")
    check("마녀 레이무 입기", game.on_action("wear", ("reimu", "witch")) and P["reimu"].skin == "witch")
    real = dict(wardrobe.ART_SEASON)                 # 기간이 아닐 때: 뽑기엔 없고 새전으로 살 수 있음
    month = time.localtime().tm_mon
    wardrobe.ART_SEASON.update({k: ((month % 12) + 1,) for k in real})
    check("기간 아니면 뽑기에 없음", not any(it.kind == "art" and it.skin in real for it in wardrobe.pool(s)))
    s.saisen = 10 ** 7
    check("기간 아니면 새전으로 사기", game.on_action("wbuy", "sanae:pumpkin") and "sanae:pumpkin" in s.wardrobe)
    s.cloth = 300
    check("기간 아니어도 옷감 교환", game.on_action("exchange", "cirno:obake") and s.cloth == 0)
    wardrobe.ART_SEASON.clear()
    wardrobe.ART_SEASON.update(real)
    calm()
    check("레이센 방문", game.visits.start("reisen"))


def t_reisen():
    v = game.visits.visit
    check("레이센 약 행상", v is not None and v.phase == "shop", v.phase if v else None)
    if v is not None:
        before = prayer.pat_multiplier(s)
        check("피로회복약 → 쓰다듬기 ×2", v.buy("energy") and prayer.pat_multiplier(s) == before * 2)
        check("꿈나라 약", v.buy("dream") and s.dream_pill)
        v.cancel()
    s.reisen_until = 0.0


def t_end():
    app.quit()


STEPS = [(t_core, 3000), (t_core2, 2500), (t_thief, 1600), (t_skill, 1800), (t_aff, 6000), (t_tag, 6000),
         (t_duel, 8500), (t_fairies, 8000), (t_fairies2, 17000), (t_aya, 20000), (t_suika, 2000),
         (t_shop, 1000), (t_season_shop, 12000), (t_tewi, 1500), (t_koishi, 7500), (t_nitori, 11000),
         (t_nitori2, 1500), (t_yuyuko, 9000), (t_yuyuko2, 1500), (t_mystia, 2500), (t_mystia2, 1500),
         (t_youmu, 0), (t_meiling, 11000), (t_reisen, 1000), (t_end, 0)]


def run(i: int = 0) -> None:
    fn, wait = STEPS[i]
    try:
        fn()
    except Exception as e:  # 한 단계가 터져도 나머지는 계속
        check(f"{fn.__name__} 예외", False, repr(e))
    if i + 1 < len(STEPS):
        t = QTimer(app)
        t.setTimerType(Qt.PreciseTimer)
        t.setSingleShot(True)
        t.timeout.connect(lambda: run(i + 1))
        t.start(wait)


QTimer.singleShot(4500, run)          # 켜고 출석 카드가 뜬 뒤부터
random.seed(1)
app.exec()
fails = [r for r in RESULTS if not r[1]]
print(f"\n통과 {len(RESULTS) - len(fails)} / {len(RESULTS)}" + (f"   실패: {[r[0] for r in fails]}" if fails else ""))
shutil.rmtree(TMP, ignore_errors=True)
os._exit(1 if fails else 0)
