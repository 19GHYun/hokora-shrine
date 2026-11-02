# -*- coding: utf-8 -*-
"""Hokora 전체 기능을 한 번에 돌려 보는 연기(smoke) 시험.

    python tests/smoke.py

- 저장은 임시 폴더(APPDATA)에, 사진은 임시 폴더에 — 진짜 저장·사진 폴더·클립보드는 건드리지 않는다.
- 마우스는 가짜 커서, 자리 비움(낮잠)은 끔.
- 기본은 화면에 아무것도 띄우지 않고(오프스크린) 돈다. 화면에 띄워 보려면 HOKORA_SMOKE_SHOW=1.
- 날씨는 '흐림'으로 고정 (바람·손님 배수가 다른 시험에 끼어들지 않게).
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
os.environ.update(APPDATA=str(TMP / "appdata"), HOKORA_ALL="1", HOKORA_NAP_AFTER="999999", HOKORA_MUTE="1",
                  HOKORA_SEASON="summer", HOKORA_NIGHT="0", HOKORA_WEATHER="cloudy")
if os.environ.get("HOKORA_SMOKE_SHOW") != "1":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, QPointF, Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

from hokora import app as hk  # noqa: E402
from hokora import affection as aff  # noqa: E402
from hokora import cucumber, daily, guests, ink, offering, omamori, photo, play, prayer, torii, wardrobe  # noqa: E402
from hokora import ufo as hk_ufo  # noqa: E402
from hokora import sound as hk_sound  # noqa: E402
from hokora import omikuji as hk_omikuji  # noqa: E402
from hokora.state import GameState  # noqa: E402
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

SOUNDS: list[str] = []
hk_sound.play_suzu = lambda: SOUNDS.append("suzu") or True      # 진짜 소리는 내지 않고 기록만
game = hk.Game(app)
game.start()
s = game.state
s.tutorial = 99                                  # 처음 안내는 따로 시험 (다른 시험에 끼어들지 않게)
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
    for tab in range(9):
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


def t_weather():
    calm()
    base = prayer.income_multiplier(s)
    for key, want in (("clear", 1.2), ("aurora", 2.0)):
        os.environ["HOKORA_WEATHER"] = key
        check(f"날씨 {key} 수입 ×{want}", abs(prayer.income_multiplier(s) / base - want) < 1e-9)
    os.environ["HOKORA_WEATHER"] = "drizzle"
    game._refresh_season()
    check("안개비 연출", game.wfx.isVisible() and game.wfx.kind == "drizzle")
    os.environ["HOKORA_WEATHER"] = "cloudy"
    game._refresh_season()
    check("흐림은 연출 없음", not game.wfx.isVisible())
    os.environ["HOKORA_WEATHER"] = "storm"
    p = ev.gust()
    check("풍우: 바람에 날아감", p is not None and p.state == "fall", p.ch.key if p else None)
    rates = {}
    for key in ("cloudy", "sunshower"):                 # 여우비: 대길·중길이 잘 나옴
        os.environ["HOKORA_WEATHER"] = key
        st, rng, top = GameState(), random.Random(7), 0
        for _ in range(3000):
            st.omikuji_date = ""
            top += hk_omikuji.draw(st, rng).fortune.rank in ("대길", "중길")
        rates[key] = top / 3000
    check("여우비: 대길·중길 2배쯤", rates["sunshower"] > rates["cloudy"] * 1.6, rates)
    os.environ["HOKORA_WEATHER"] = "cloudy"
    game._refresh_season()


def t_cutin():
    calm()
    ev._skill_at.clear()
    game._cutin_at = -1e9
    before = len([w for w in game._cards if type(w).__name__ == "CutIn"])
    ev.try_skill(P["reimu"])
    after = len([w for w in game._cards if type(w).__name__ == "CutIn"])
    check("스펠카드 컷인", after == before + 1)
    s.cutin = False
    game._cutin_at = -1e9
    ev._skill_at.clear()
    calm()
    ev.try_skill(P["sakuya"])
    check("컷인 끄기", len([w for w in game._cards if type(w).__name__ == "CutIn"]) <= after)
    s.cutin = True
    for p in game.pets:
        p.frozen_until = 0.0


def t_yukari():
    calm()
    xmas = [k for k in ("sakuya:santa", "flandre:reindeer", "marisa:gift") if k in wardrobe.ITEMS]
    check("크리스마스 의상 3벌", len(xmas) == 3 and all(wardrobe.is_limited(wardrobe.ITEMS[k]) for k in xmas), xmas)
    s.saisen = 10 ** 7
    if time.localtime().tm_mon != 12:
        check("12월이 아니면 새전으로 사기", game.on_action("wbuy", "flandre:reindeer") and "flandre:reindeer" in s.wardrobe)
    check("루돌프 플랑드르 입기", "flandre:reindeer" not in s.wardrobe
          or (game.on_action("wear", ("flandre", "reindeer")) and P["flandre"].skin == "reindeer"))
    check("유카리 방문", game.visits.start("yukari"))
    G["pos"] = {p.ch.key: round(p.pos_x) for p in game.pets}
    v = game.visits.visit
    if v is not None:
        v.next_at = 0.0
        v.phase = "tricks"


def t_yukari2():
    moved = [p.ch.key for p in game.pets if abs(round(p.pos_x) - G["pos"][p.ch.key]) > 30]
    check("유카리 틈으로 친구 옮기기", len(moved) >= 1, moved)
    check("옮겨진 친구가 다시 보임", all(p.windowOpacity() > 0.9 for p in game.pets if p.ch.key in moved))
    if game.visits.visit:
        game.visits.visit.cancel()


def t_patchouli():
    calm()
    check("파츄리 방문", game.visits.start("patchouli"))
    v = game.visits.visit
    if v is not None:
        v.phase = "shop"
        os.environ.pop("HOKORA_WEATHER", None)
        check("날씨 마법 (오로라)", v.buy("aurora") and game.state.weather_magic == "aurora")
        from hokora import weather as hk_weather
        check("마법 날씨가 지금 날씨", hk_weather.current().key == "aurora" and hk_weather.magic_left() > 1700)
        check("마법은 한 번만", not v.buy("clear"))
        hk_weather.set_magic("", 0.0)
        s.weather_magic, s.weather_magic_until = "", 0.0
        os.environ["HOKORA_WEATHER"] = "cloudy"
        v.cancel()


def t_expedition():
    calm()
    from hokora import expedition
    s.saisen = 10 ** 7
    s.shrine_level = 5
    check("원정 보내기", game.on_action("expedition", ("reimu", "youkai")))
    check("같은 친구는 또 못 보냄", not game.on_action("expedition", ("reimu", "village")))
    G["exp_reward"] = s.expeditions[0]["reward"] if s.expeditions else None
    check("적성 보너스 (레이무 → 요괴 퇴치)", G["exp_reward"] is not None
          and G["exp_reward"]["saisen"] == int(max(10, s.income_per_min) * expedition.PLACES["youkai"].saisen * 1.5))


def t_expedition2():
    check("원정 간 친구는 작업표시줄에 없음", "reimu" not in [p.ch.key for p in game.pets])
    for e in s.expeditions:                           # 시간이 다 된 걸로
        e["end"] = time.time() - 1
    before, cloth = s.saisen_total, s.cloth
    game._check_expeditions()
    check("원정 귀환 보상", s.saisen_total >= before + G["exp_reward"]["saisen"] and s.cloth >= cloth + G["exp_reward"]["cloth"])
    check("돌아온 친구", "reimu" in [p.ch.key for p in game.pets] and s.expedition_done == 1 and not s.expeditions)
    for c in list(game._card_queue):
        c.close()


def t_achieve():
    from hokora import achievements
    n0 = len(s.achievements)
    total0 = s.saisen_total
    s.pats = max(s.pats, 100)
    game._check_achievements()
    check("업적 달성 + 보상", len(s.achievements) > n0 and s.saisen_total > total0, len(s.achievements))
    k = s.achievements[0]
    check("칭호 달기", game.on_action("title", k) and achievements.title(s) == achievements.ACHIEVEMENTS[k].name)
    check("없는 업적은 칭호 못 닮", not game.on_action("title", "pat10000") or "pat10000" in s.achievements)
    for c in list(game._card_queue):
        c.close()


def t_fishing():
    from hokora import fishing
    calm()
    s.saisen = 10 ** 7
    game.on_decor("pond", "buy")
    check("연못 놓기", "pond" in game.decors)
    b0 = fishing.bait(s)
    game.go_fishing()
    win = getattr(game, "_fishing", None)
    check("낚시 창", win is not None and fishing.bait(s) == b0 - 1)
    if win is not None:
        before = s.saisen
        win._finish("koi", "")
        check("비단잉어 낚기", s.fish.get("koi") == 1 and s.saisen > before and s.fish_caught == 1)
        win.close()
    game._fishing = None
    game.go_fishing()
    win = game._fishing
    if win is not None:
        win._finish(None, "놓쳤다")
        check("놓치면 아무것도 없음", sum(s.fish.values()) == 1)
        win.close()
    game._fishing = None
    s.fish_bait, s.fish_bait_date = 0, __import__("datetime").date.today().isoformat()
    game.go_fishing()
    check("미끼가 없으면 못 낚음", game._fishing is None)


def t_festival():
    from hokora import festival
    calm()
    s.saisen = 10 ** 7
    base = prayer.income_multiplier(s)
    check("예대제 열기", game.on_action("festival") and festival.active(s))
    check("예대제 수입 ×2", abs(prayer.income_multiplier(s) / base - 2.0) < 1e-9)
    check("등롱 줄", game.ffx.isVisible())
    check("예대제는 하루에 한 번", not game.on_action("festival"))
    s.festival_until = time.time() - 1
    before = s.saisen_total
    game._festival_tick()
    check("예대제 결산 (참배객 새전)", s.festival_reported and s.saisen_total > before and not game.ffx.isVisible())
    for c in list(game._card_queue):
        c.close()


def t_crowd():
    calm()
    game.set_max_out(3)
    out = [p.ch.key for p in game.pets]
    check("동시에 3명만", len(out) == 3, out)
    G["crowd_prev"] = out
    game._crowd_tick(rotate=True)


def t_crowd2():
    out2 = [p.ch.key for p in game.pets]
    check("10분마다 번갈아", len(out2) == 3 and set(out2) != set(G.get("crowd_prev", [])), out2)
    game.set_max_out(0)


def t_crowd3():
    check("전부 다시 나옴", len(game.pets) == len(game._eligible()), len(game.pets))
    calm()


def t_tutorial():
    s.tutorial = 0
    game._tutorial_show()
    check("처음 안내 말풍선", game.tip is not None and game.tip.isVisible())
    r = P["reimu"] if P["reimu"] in game.pets else game.pets[0]
    r.last_reward = 0
    game.on_pat(r)
    game.on_thrown(r, 900)
    game.open_panel()
    game.panel.close()
    before = s.saisen_total
    if s.tutorial == 3:
        game.omikuji() if hk.can_draw(s) else game._tutorial_show()
    game._tutorial_event("menu")
    check("처음 안내 끝 + 새전 100", s.tutorial == 99 and s.saisen_total >= before + 100 and game.tip is None, s.tutorial)
    for c in list(game._card_queue):
        c.close()
    for w in list(game._cards):
        if type(w).__name__ == "FortuneSlip":
            w.close()


def t_settings():
    game.open_settings()
    win = [w for w in game._cards if type(w).__name__ == "SettingsWindow"]
    check("설정 창", bool(win) and win[-1].isVisible())
    for w in win:
        w.close()
    game.save()
    st = game.store
    check("하루 한 번 백업", any(p.name.startswith("save-") for p in st.backup_dir.glob("*.json")))
    st.backup(force=True)
    rows = st.backups()
    check("백업 목록", len(rows) >= 2 and "saisen" in rows[0][1], len(rows))
    G["restarted"] = False
    game._restart = lambda: G.__setitem__("restarted", True)
    game.restore_backup(rows[-1][0])
    check("백업 되돌리기 (다시 시작)", G["restarted"] and st.readonly)


def t_life():
    from hokora import bubble, moon
    from datetime import datetime, timezone
    calm()

    def said(word: str) -> bool:
        return any(word in b.text for b in bubble._alive)
    check("달 계산 (2024-01-25 보름)", moon.is_full(datetime(2024, 1, 25, 17, 54, tzinfo=timezone.utc)))
    check("달 계산 (2024-01-11 삭)", moon.is_new(datetime(2024, 1, 11, 11, 57, tzinfo=timezone.utc)))
    real_full = moon.is_full
    moon.is_full = lambda now=None: True
    os.environ["HOKORA_NIGHT"] = "1"
    base_night = prayer.income_multiplier(s)
    moon.is_full = lambda now=None: False
    check("보름달 밤 수입 ×1.3", abs(base_night / prayer.income_multiplier(s) - 1.3) < 1e-9)
    moon.is_full = real_full
    os.environ["HOKORA_NIGHT"] = "0"
    game._chime(15)
    check("시계 친구 팻말", any(type(w).__name__ == "HourSign" for w in game._cards))
    G["real"] = (hk.winutil.battery, hk.winutil.recycle_bin, game._cpu.sample)
    hk.winutil.battery = lambda: (15, False)
    game._pc_tick()
    check("배터리 부족 반응", game._batt_low)
    hk.winutil.battery = lambda: (16, True)
    game._pc_tick()
    check("충전 반응", not game._batt_low)
    game._cpu.sample = lambda: 97.0
    for _ in range(3):
        game._pc_tick()
    check("CPU 과열 반응", "cpu" in game._said)
    hk.winutil.recycle_bin = lambda: (500, 3 * 1024 ** 3)
    game._said.pop("recycle", None)               # 이 PC 의 진짜 휴지통이 가득이면 시험 전에 이미 말했을 수 있음
    game._pc_tick(recycle=True)
    check("휴지통 청소 친구", said("휴지통"))
    hk.winutil.battery, hk.winutil.recycle_bin, game._cpu.sample = G["real"]
    game.make_card()
    cards = list((TMP / "photos").glob("hokora_card_*.png"))
    from PySide6.QtGui import QImage
    check("신사 명함", len(cards) == 1 and QImage(str(cards[0])).width() == 1200)
    for c in list(game._card_queue):
        c.close()


def t_options():
    """설정: 센본토리이 숨기기, 전체화면에서도 돌아다니기, 손님 방울."""
    calm()
    s.torii = max(s.torii, 4)
    game._sync_torii()
    check("센본토리이 보임", game.torii_row.isVisible() and game.torii_row in game.windows())
    game.set_show_torii(False)
    check("센본토리이 숨기기 (수입은 그대로)", not game.torii_row.isVisible()
          and game.torii_row not in game.windows() and torii.income(s) == s.torii // 2)
    game.set_show_torii(True)
    check("센본토리이 다시 보이기", game.torii_row.isVisible())

    real = hk.winutil.fullscreen_app_running
    hk.winutil.fullscreen_app_running = lambda games_only=False: not games_only     # 영상·브라우저 전체화면
    game._watch()
    check("전체화면이면 숨음 (기본)", game.hidden_for_fullscreen and not game.shrine.isVisible())
    game.set_fullscreen_show(True)
    check("전체화면에서도 돌아다니기", not game.hidden_for_fullscreen and game.shrine.isVisible()
          and game.torii_row.isVisible() and all(p.isVisible() for p in game.pets))
    hk.winutil.fullscreen_app_running = lambda games_only=False: True               # 전용 전체화면 게임
    game._watch()
    check("전용 전체화면 게임에선 켜도 숨음", game.hidden_for_fullscreen and not game.shrine.isVisible())
    hk.winutil.fullscreen_app_running = real
    game.set_fullscreen_show(False)
    game._watch()
    check("전체화면 끝나면 다시 보임", not game.hidden_for_fullscreen and game.shrine.isVisible())

    toasts: list = []
    G["tray"] = game.tray
    game.tray = type("FakeTray", (), {"showMessage": lambda self, *a: toasts.append(a)})()
    s.guest_bell, s.saisen = False, 5_000
    game.ring_bell("aya")
    check("손님 방울 없으면 알림 없음", not toasts)
    check("손님 방울: 새전 모자라면 못 삼", not game.buy_guest_bell() and not s.guest_bell and s.saisen == 5_000)
    s.saisen = guests.BELL_PRICE + 1_000
    game.open_settings()
    win = [w for w in game._cards if type(w).__name__ == "SettingsWindow"][-1]
    G["settings_h"] = win.height()
    check("설정 창: 방울 사기 버튼", win.bell_buy.isVisible() and not win.bell_check.isVisible()
          and not win.bell_sound.isVisible() and win.bell_btn.isEnabled())
    win.bell_btn.click()
    check("손님 방울 사기", s.guest_bell and s.guest_bell_on and s.saisen == 1_000
          and win.bell_check.isVisible() and win.bell_check.isChecked() and not win.bell_buy.isVisible()
          and win.bell_sound.isVisible() and win.bell_sound_check.isChecked(),
          (s.saisen, win.height()))
    win.close()
    n_sound = len(SOUNDS)
    check("손님이 오면 알림", game.visits.start("tewi") and toasts and "테위" in toasts[-1][1], toasts[-1:])
    check("손님이 오면 방울 소리", len(SOUNDS) == n_sound + 1)
    check("소리 재생 모듈 (winsound)", hk_sound.available())
    game.set_guest_bell_sound(False)
    game.ring_bell("aya")
    check("방울 소리 끄기 (알림은 그대로)", len(SOUNDS) == n_sound + 1 and "아야" in toasts[-1][1])
    game.set_guest_bell_sound(True)
    wav = Path(hk_sound.suzu_path())
    import wave as _wave
    with _wave.open(str(wav), "rb") as w:
        check("방울 소리 파일 (코드로 합성)", w.getframerate() == hk_sound.RATE and w.getnframes() > hk_sound.RATE,
              wav.stat().st_size)
    game.set_guest_bell(False)
    n = len(toasts)
    game.ring_bell("aya")
    check("손님 방울 끄기", len(toasts) == n)
    game.set_guest_bell(True)
    if game.visits.visit:
        game.visits.visit.cancel()
    game.tray = G["tray"]


def t_goods():
    """놀잇감: 요술 붓(그린 길이 발판, 가파르면 미끄럼)."""
    calm()
    s.goods, s.saisen = [], 1_000

    def cards():
        return [w for w in game._cards if type(w).__name__ == "GoodsCard"]
    game.use_goods("brush")
    check("잠긴 놀잇감 → 사기 카드", bool(cards()) and cards()[-1].isVisible() and not cards()[-1].buy_btn.isEnabled())
    for c in cards():
        c.close()
    check("새전 모자라면 못 삼", not game.buy_goods("brush") and "brush" not in s.goods)
    s.saisen = 60_000
    game.use_goods("brush")
    cards()[-1].buy_btn.click()
    canvas = game._ink_canvas
    check("요술 붓 사기 → 바로 그리기", "brush" in s.goods and s.saisen == 40_000
          and canvas is not None and canvas.isVisible())
    g = ground()
    x0 = g.x1 + 40
    pts = ([(x0 + i * 4, g.y - 4 - i * 2.0) for i in range(50)]
           + [(x0 + 196 + i * 4, g.y - 102 + i * 3.0) for i in range(1, 30)])
    canvas.pick("shu")
    made = canvas.on_stroke(pts, canvas.color)
    pc = game.ink[-1].pieces[0] if game.ink and game.ink[-1].pieces else None
    xm = pc.x1 + 50 if pc else 0.0
    check("그린 길 = 발판", made is not None and pc is not None and game.ink[-1].win.isVisible()
          and game.platform(pc.id, xm, 0.0) is not None
          and (game.find_landing(xm, pc.y_at(xm) - 30, pc.y_at(xm) + 5) or (0, 0))[1] == pc.id)
    real = hk.winutil.fullscreen_app_running
    hk.winutil.fullscreen_app_running = lambda games_only=False: True    # 화면을 덮는 그리기 판 = 전체화면으로 보임
    game._watch()
    check("그리는 동안은 전체화면으로 숨지 않음", game._ink_canvas is canvas and canvas.isVisible()
          and not game.hidden_for_fullscreen)
    hk.winutil.fullscreen_app_running = real
    canvas.close()
    check("다 그렸어요 → 색 기억", game._ink_canvas is None and s.ink_color == "shu")
    steep = [x for x in pc.xs if pc.slope_at(x) > 0.65] if pc else []
    pet = G["ink_pet"] = game.pets[0]                 # 붐빔 조절 시험 뒤라 P 의 창은 이미 바뀌었을 수 있음
    if steep:
        x = steep[len(steep) // 4]
        pet.pos_x, pet.pos_y, pet.on, pet._on_left = x, pc.y_at(x), pc.id, 0.0
        pet.state, pet.vx, pet.scripted = "idle", 0.0, False
        pet.state_until = time.monotonic() + 99
    G["slides0"] = s.slides


def t_goods2():
    """그린 길 미끄럼·사라짐, 신사 미닫이문(신사 안 들여다보기)."""
    pet = G["ink_pet"]
    check("가파른 길 → 미끄럼 → 슝", s.slides > G["slides0"], (pet.state, pet.on, s.slides))
    st = game.ink[-1]
    st.born = time.monotonic() - ink.INK_LIFE - 1
    game._ink_tick()
    check("그린 길은 시간이 지나면 사라짐", not game.ink)
    game.add_stroke([(ground().x1 + 50 + i * 5, ground().y - 60) for i in range(40)], "sumi")
    game.clear_ink()
    check("그린 길 지우기", not game.ink)

    s.saisen = 40_000
    game.use_goods("room")
    [w for w in game._cards if type(w).__name__ == "GoodsCard"][-1].buy_btn.click()
    room = game._room
    check("미닫이문 사기 → 신사 안", "room" in s.goods and s.saisen == 10_000 and room is not None and room.isVisible())
    invited = list(room.invited) if room else []
    check("안이 비면 친구가 잠깐 들어옴", room is not None and len(room.seats) >= 2 and invited,
          (room.seats if room else None, invited))
    n0 = s.snacks
    who = room.eat()
    key = next(iter(room.seats))
    room.poke(key)
    room.grab()
    check("귤 먹기·말 걸기", s.snacks == n0 + 1 and who in room.seats and any(b[0] == key for b in room.bubbles))
    room.close()
    check("문 닫으면 다시 밖으로", game._room is None and all(any(p.ch.key == k for p in game.pets) for k in invited))
    game.open_room()
    real = hk.winutil.fullscreen_app_running
    hk.winutil.fullscreen_app_running = lambda games_only=False: True
    game._watch()
    check("전체화면이면 신사 안 창 닫힘", game._room is None)
    hk.winutil.fullscreen_app_running = real
    game._watch()


def t_ufo():
    """누에의 UFO: 여러 번 누르면 격추 → 친구가 떨어져 돌아옴."""
    calm()
    check("UFO 등장", game.summon_ufo() and game.ufo is not None)
    u = game.ufo
    if u is None:
        return
    u.x, u.y = u.target
    u._start_beam()
    pet = G["ufo_pet"] = u.pet
    check("빛으로 빨아올림", u.phase == "beam" and pet.scripted and u.beam.isVisible())
    n0 = s.ufo_shot
    for _ in range(u.hp_max):
        u.hit()
    check("UFO 격추 → 친구가 떨어짐", u.phase == "hit" and not pet.scripted and pet.state == "fall"
          and s.ufo_shot == n0 + 1)
    check("격추하면 누에가 떨어짐", any(p.ch.key == "nue" for p in game.guests))


def t_ufo2():
    """구출된 친구 착지 / 끌려가는 친구를 잡아채서 구출 / 못 막으면 끌려감."""
    pet = G["ufo_pet"]
    check("구출된 친구 착지", pet.on is not None and not pet.scripted, (pet.state, pet.on))
    if game.ufo is not None:
        game.ufo.close()
        game.ufo = None
    game.summon_ufo()
    u = game.ufo
    u.x, u.y = u.target
    u._start_beam()
    n0 = s.ufo_rescued
    u.pet._press_pos = QPoint(1, 1)                      # 사용자가 잡아챔
    u.step(0.05)
    u.pet._press_pos = None
    u.pet.state = "fall"
    check("잡아채서 구출", u.phase == "leave" and s.ufo_rescued == n0 + 1 and not u.pet.scripted)
    u.close()
    game.ufo = None
    hk_ufo.LIFT_TIME = 0.4
    game.summon_ufo()
    u = game.ufo
    u.x, u.y = u.target
    u._start_beam()
    G["victim"] = u.pet.ch.key


def t_ufo3():
    key = G["victim"]
    hk_ufo.LIFT_TIME = 9.0
    check("못 막으면 끌려감", key in game._abducted and all(p.ch.key != key for p in game.pets) and s.ufo_taken >= 1)
    check("끌려간 친구는 붐빔 조절·신사 안에서 빠짐", key not in game._eligible() and key not in game.room_friends())
    game._abducted[key] = time.time() - 1
    game._ufo_returns()
    check("시간이 지나면 선물 들고 돌아옴", key not in game._abducted and any(p.ch.key == key for p in game.pets))
    if game.ufo is not None:
        game.ufo.close()
        game.ufo = None


def t_cuke():
    """니토리의 오이 시세: 일요일에 사서 평일에 팔고, 다음 주엔 시든다."""
    from datetime import datetime as real_dt
    now = [real_dt(2026, 10, 11, 10, 0)]                 # 일요일

    class FakeDT(real_dt):
        @classmethod
        def now(cls, tz=None):
            return now[0]
    cucumber.datetime = FakeDT
    s.saisen, s.cuke_week, s.cuke_have, s.cuke_paid, s.cuke_fees = 50_000, "", 0, 0, 0
    got = cucumber.buy(s, 100)
    check("오이 사기 (일요일)", got == 100 and s.cuke_have == 100 and s.cuke_paid == 100 * s.cuke_base)
    s.saisen = 10 ** 7
    got = cucumber.buy(s, 10_000)
    check("오이 한도 없음 (3,000개 넘게)", got == 10_000 and s.cuke_have == 10_100)
    w = cucumber.CucumberWindow(game)
    w.show()
    check("사는 날 단추 (10 · 100 · 1,000 · 최대)", len(w.btns) == 4 and w.btns[3].text().startswith("최대")
          and w.btns[2].text().startswith("1,000개"), [b.text() for b in w.btns])
    w.close()
    now[0] = real_dt(2026, 10, 12, 9, 0)                 # 월요일 오전
    check("월요일 오전엔 아직 못 팖", cucumber.sell(s, 10) == 0 and cucumber.can_buy(now[0]))
    now[0] = real_dt(2026, 10, 14, 15, 0)                # 수요일 오후
    price = cucumber.price_now(s)
    got = cucumber.sell(s, 50)
    gross = 50 * price
    check("그때 시세대로 팔기 (수수료 5% 빼고)", got == gross - cucumber.fee(gross) and s.cuke_have == 10_050
          and price == cucumber.prices(s)[5] and s.cuke_fees == cucumber.fee(gross) > 0, (got, gross))
    check("평일엔 못 삼", cucumber.buy(s, 10) == 0)
    w = cucumber.CucumberWindow(game)
    w.show()
    check("오이 시세 창", w.isVisible() and len(w.btns) == 2)
    w.close()
    now[0] = real_dt(2026, 10, 18, 8, 0)                 # 다음 일요일
    check("다음 주가 되면 시듦", cucumber.refresh(s) == 10_050 and s.cuke_have == 0)
    shapes = [cucumber.make_prices(seed, 100) for seed in range(400)]
    check("시세 패턴 (12칸, 대폭등은 2배 넘게)", all(len(ps) == 12 and min(ps) >= 9 for _, ps in shapes)
          and all(max(ps) >= 200 for pat, ps in shapes if pat == 1))
    cucumber.datetime = real_dt


def t_offer():
    """공물: 올려 두면 그 손님이 와서 먹고 답례품."""
    for c in list(game._card_queue):
        c.close()
    s.saisen, s.offering, s.gifts = 10_000, "", {}
    check("공물 올리기", game.place_offering("onigiri") and s.offering == "onigiri"
          and game.offer_tray.isVisible() and s.saisen == 8_000 and offering.wanted(s) == "yuyuko")
    check("공물은 한 번에 하나", not game.place_offering("sake"))
    game.clear_offering()
    s.cuke_have, s.cuke_paid, s.cuke_bought = 20, 2_000, s.cuke_week
    check("가진 오이 10개로 공물", game.place_offering("cucumber", True) and s.cuke_have == 10 and s.saisen == 8_000)
    game.clear_offering()
    check("치우면 공물상도 사라짐", not s.offering and not game.offer_tray.isVisible())
    w = offering.OfferingWindow(game)
    w.show()
    check("공물 창", w.isVisible())
    w.close()
    game.place_offering("onigiri")
    offering.EAT_AFTER = 0.3
    if game.visits.visit is not None:
        game.visits.visit.cancel()
    G["yuyuko"] = game.visits.start("yuyuko")


def t_offer2():
    offering.EAT_AFTER = 7.0
    cards = [c for c in game._card_queue if type(c).__name__ == "GiftCard"]
    check("손님이 먹고 답례품", G["yuyuko"] and not s.offering and s.gifts.get("yuyuko") == 1 and cards,
          (G["yuyuko"], s.offering, s.gifts))
    for c in list(game._card_queue):
        c.close()
    if game.visits.visit is not None:
        game.visits.visit.cancel()


def t_sengu():
    """식년천궁: 최고 단계 신사를 새로 지어 수입 +10% (영구), 값은 할 때마다 2배."""
    from hokora import diary, sengu
    calm()
    s.shrine_level, s.sengu, s.sengu_until, s.saisen = 4, 0, 0.0, 10 ** 7
    check("최고 단계 전엔 못 함", not game.on_action("sengu") and "단계" in sengu.blocked(s))
    s.shrine_level = 5
    base, off0 = prayer.income_multiplier(s), diary.offline_income(s, 3600)
    check("식년천궁 시작", game.on_action("sengu") and sengu.building(s) and game.shrine.building
          and s.saisen == 10 ** 7 - sengu.BASE_COST)
    check("짓는 중엔 또 못 함", not game.on_action("sengu"))
    game.open_panel()
    p = game.panel
    check("신사 탭: 짓는 중 (남은 시간)", p.up_btn.text() == "짓는 중" and not p.up_btn.isEnabled() and "남음" in p.up_label.text())
    p.close()
    s.sengu_until = time.time() - 1
    game._sengu_tick()
    check("다 지으면 2대째 · 수입 +10%", s.sengu == 1 and not game.shrine.building and not s.sengu_until
          and abs(prayer.income_multiplier(s) / base - 1.1) < 1e-9, prayer.income_multiplier(s) / base)
    check("꺼져 있는 동안의 수입에도 +10%", abs(diary.offline_income(s, 3600) / off0 - 1.1) < 0.01)
    check("다음 천궁은 2배", sengu.cost(s) == 2 * sengu.BASE_COST)
    game.open_panel()
    p = game.panel
    check("신사 탭: 천궁하기 · 2대째 표시", p.up_btn.text() == "천궁하기" and p.up_btn.isEnabled() and "2대째" in p.title.text())
    p.close()
    img = game.shrine.grab().toImage()
    game.shrine.set_building(True)
    img2 = game.shrine.grab().toImage()
    check("공사 중엔 비계 · 가림막이 그려짐", img != img2)
    game.shrine.set_building(False)
    for c in list(game._card_queue):
        c.close()
    s.sengu = 0                                    # 다른 시험의 수입 계산에 끼어들지 않게


def t_train():
    """친구 수련: 특기 Lv.10 까지, 값은 레벨마다 2배."""
    from hokora import training
    calm()
    s.saisen, s.skill_lv = 10 ** 7, {}
    check("수련 Lv.1 → 2", game.on_action("train", "sanae") == 2 and s.skill_lv["sanae"] == 2
          and s.saisen == 10 ** 7 - training.BASE_COST)
    check("값은 레벨마다 2배", training.cost(s, "sanae") == 2 * training.BASE_COST)
    met = list(s.unlocked)
    s.unlocked = [k for k in met if k != "youmu"]
    check("아직 못 만난 친구는 못 함", game.on_action("train", "youmu") is None and "만나지" in training.blocked(s, "youmu"))
    s.unlocked = met
    s.skill_lv = {"sanae": 1, "sakuya": 1, "meiling": 1, "marisa": 1, "youmu": 1}
    lv1 = (ev.miracle_amount(), ev.time_stop_seconds(), ev.guard_chance(), ev.catch_bonus(100), ev.garden_amount())
    s.skill_lv = {"sanae": 10, "sakuya": 10, "meiling": 10, "marisa": 10, "youmu": 10, "reimu": 10}
    lv10 = (ev.miracle_amount(), ev.time_stop_seconds(), ev.guard_chance(), ev.catch_bonus(100), ev.garden_amount())
    check("Lv.1 은 지금과 같음", lv1[0] == hk_events.MIRACLE_SAISEN and lv1[1] == hk_events.TIME_STOP
          and lv1[2] == hk_events.GUARD_CHANCE and lv1[3] == 50, lv1)
    check("Lv.10: 기적 · 시간 정지 · 문지기 · 붙잡기 보너스 · 정원 손질이 셈",
          lv10[0] > lv1[0] and lv10[1] == 7.5 and abs(lv10[2] - 0.97) < 1e-9 and lv10[3] == 140
          and lv10[4] == round(lv1[4] * 5.5),
          lv10)
    check("Lv.10 은 특기를 더 자주 (쿨타임 64%)", abs(training.cooldown_scale(s, "reimu") - 0.64) < 1e-9)
    check("최고 레벨이면 더 못 올림", game.on_action("train", "sanae") is None and training.cost(s, "sanae") is None)
    s.skill_lv = {"remilia": 5}
    ranks = set()
    for i in range(40):
        st = GameState(skill_lv={"remilia": 5}, fate_boost=True)
        ranks.add(hk_omikuji.draw(st, random.Random(i)).fortune.rank)
    check("레밀리아 Lv.5: 조작된 운명은 대길만", ranks == {"대길"}, ranks)
    game.open_panel()
    p = game.panel
    name = p.cards["remilia"][1].text()
    p.close()
    check("도감에 특기 레벨", "Lv.5" in name, name)
    s.skill_lv = {}


def t_fireworks():
    """불꽃놀이 봉납: 새전을 넣고 신사 위 하늘에 불꽃 (짧게 줄여서 시험)."""
    import dataclasses
    from hokora import fireworks
    calm()
    G["fw_s"] = fireworks.SIZES["s"]
    fireworks.SIZES["s"] = dataclasses.replace(G["fw_s"], seconds=4.2)
    s.saisen, n0 = 10 ** 7, s.fireworks
    check("불꽃놀이 봉납 (소)", game.on_action("fireworks", "s") and game.fireworks_show is not None
          and game.fireworks_show.isVisible() and s.saisen == 10 ** 7 - 1_000 and s.fireworks == n0 + 1)
    check("쏘는 동안엔 또 못 쏨", not game.on_action("fireworks", "m") and "끝나면" in fireworks.blocked(s, "m", True))
    w = game.fireworks_show
    scr = app.primaryScreen().geometry()
    check("하늘 창은 화면을 다 덮지 않음 (전체화면으로 안 보이게)", w.height() < scr.height() * 0.8, (w.width(), w.height()))
    game.open_panel()
    p = game.panel
    check("참배 탭: 쏘는 중엔 단추가 꺼짐", not any(b.isEnabled() for b in p.fw_btns.values()))
    p.close()


def t_fireworks2():
    w = game.fireworks_show
    if w is None:
        check("불꽃이 터짐", False, "벌써 닫힘")
        return
    img = w.grab().toImage()
    lit = sum(img.pixelColor(x, y).alpha() > 40 for y in range(0, img.height(), 6) for x in range(0, img.width(), 6))
    check("불꽃이 터짐 (하늘에 그려짐)", w.bursts >= 1 and lit > 10, (w.bursts, lit))


def t_fireworks3():
    from hokora import fireworks
    check("다 쏘면 저절로 닫힘", game.fireworks_show is None)
    fireworks.SIZES["s"] = G["fw_s"]
    xl = fireworks.FireworksShow(fireworks.SIZES["xl"], app.primaryScreen().availableGeometry(), 400, text="시험 신사")
    xl.started -= fireworks.SIZES["xl"].seconds - fireworks.TEXT_TIME + 0.5   # 「奉納」 글자가 뜬 때
    img = xl.grab().toImage()
    lit = sum(img.pixelColor(x, y).alpha() > 100 for y in range(0, img.height(), 4) for x in range(0, img.width(), 4))
    xl.close()
    check("특대: 마지막에 「奉納」 글자", lit > 50, lit)
    sched = fireworks.schedule(fireworks.SIZES["xl"], random.Random(1))
    check("특대 90발 · 피날레에 몰아서", len(sched) == 90 and sum(t > sched[-1] * 0.8 for t in sched) >= 30)


def close_cards() -> None:
    for c in list(game._card_queue):
        c.close()


def t_letters():
    """친구 편지: 하트가 늘면 편지가 오고, 누르면 펼쳐짐 · 다섯 번째엔 옷감 · 편지함."""
    from hokora import letters
    from hokora.render import short_name
    calm()
    close_cards()
    P.update({p.ch.key: p for p in game.pets})        # 앞 시험에서 다시 나온 친구는 새 창
    s.letters, s.letters_read, s.affection = {}, [], {}
    game._check_letters()
    check("하트가 없으면 편지도 없음", letters.count(s) == 0 and not game._card_queue)
    game._add_affection(P["reimu"], 5)
    game._check_letters()
    note = game._card_queue[-1] if game._card_queue else None
    check("하트 1개 → 편지 1통 · 알림 카드", letters.got(s, "reimu") == [1] and isinstance(note, letters.LetterNote))
    if note is not None:
        note.on_open()
    opened = [w for w in game._cards if isinstance(w, letters.LetterWindow)]
    check("알림을 누르면 편지지가 펼쳐지고 읽음", opened and "reimu:1" in s.letters_read)
    for w in opened:
        w.close()
    close_cards()
    s.affection.update(marisa=150, cirno=40)
    queued = len(game._card_queue)                    # 닫은 카드는 이벤트 루프가 돌아야 빠짐
    game._check_letters()
    note = game._card_queue[-1] if game._card_queue else None
    check("이미 친한 친구 편지는 한꺼번에 · 알림은 한 장",
          letters.got(s, "marisa") == [1, 2, 3, 4, 5] and letters.got(s, "cirno") == [1, 2, 3]
          and len(game._card_queue) == queued + 1 and "8통" in note.title, getattr(note, "title", None))
    cloth0 = s.cloth
    gift = letters.read(s, "marisa", 5)
    check("다섯 번째 편지엔 옷감", gift and s.cloth == cloth0 + letters.LAST_GIFT)
    check("두 번 읽어도 선물은 한 번", letters.read(s, "marisa", 5) == "" and s.cloth == cloth0 + letters.LAST_GIFT)
    book = letters.LetterBook(s, s.unlocked, lambda k, n: G.__setitem__("letter", (k, n)))
    b = book.buttons
    check("편지함: 받은 것만 열림 · 안 읽은 건 ●", b[("marisa", 1)].isEnabled() and b[("marisa", 1)].text().startswith("●")
          and not b[("reimu", 2)].isEnabled() and b[("reimu", 1)].text() == "1")
    b[("cirno", 2)].click()
    check("편지함에서 누르면 그 편지", G.get("letter") == ("cirno", 2))
    book.close()
    win = letters.LetterWindow("remilia", 5, "선물")
    check("편지지 그림", not win.grab().isNull())
    win.close()
    check("편지 45통 · 친구마다 5통 · 글이 다 있음", letters.TOTAL == 45 and all(len(v) == 5 for v in letters.LETTERS.values())
          and all(a and b_ and c for v in letters.LETTERS.values() for a, b_, c in v))
    check("짧은 이름 (레밀리아 · 레이센)", short_name("remilia") == "레밀리아" and short_name("reisen") == "레이센"
          and short_name("reimu") == "레이무")
    m = QMenu()
    game._fill_menu(m)
    texts = [a.text() for a in m.actions()]
    check("메뉴: 💌 편지함 (안 읽은 편지) · 🎮 놀이", any(x.startswith("💌 편지함  (안 읽은 편지") for x in texts)
          and "🎮 놀이" in texts, texts)
    close_cards()


def t_janken():
    """가위바위보: 친구마다 버릇 · 이기면 새전 (하루 10번) · 그날 처음 이기면 호감도."""
    from hokora import janken
    rng = random.Random(3)
    check("치르노는 거의 늘 바위", sum(janken.friend_hand("cirno", "paper", rng) == "rock" for _ in range(300)) > 250)
    lose = sum(janken.judge("rock", janken.friend_hand("sakuya", "rock", rng)) == "lose" for _ in range(3000)) / 3000
    check("사쿠야는 조금 잘 이김", 0.47 < lose < 0.6, lose)
    check("판정", janken.judge("rock", "scissors") == "win" and janken.judge("rock", "paper") == "lose"
          and janken.judge("paper", "paper") == "draw")

    class Scissors:
        def random(self):
            return 0.99

        def choice(self, seq):
            return "scissors"
    s.janken_day = ""
    before = s.saisen
    _theirs, result, reward, first = janken.play(s, "reimu", "rock", Scissors())
    check("이기면 새전 · 그날 처음이면 호감도", result == "win" and reward == max(10, s.income_per_min) and first
          and s.saisen == before + reward)
    check("같은 날 두 번째 승리는 호감도 없음", not janken.play(s, "reimu", "rock", Scissors())[3])
    for _ in range(12):
        janken.play(s, "marisa", "rock", Scissors())
    check("새전은 하루 10번까지", s.janken_today == janken.DAILY_REWARDS
          and janken.play(s, "sanae", "rock", Scissors())[2] == 0)
    n = s.janken_games
    game.janken(P["sanae"], "paper")
    check("친구 우클릭 → 가위바위보", s.janken_games == n + 1)


def t_dodge():
    """탄막 피하기: 끝까지 버티면 승리, 세 번 맞으면 짐, 패턴마다 탄, 연습 보상은 하루 5번."""
    from hokora import dodge
    calm()
    w = dodge.DodgeWindow("reimu", "레이무", lambda won, hits: G.__setitem__("dodge", (won, hits)), 3.0,
                          rng=random.Random(2))
    w.soul_override = QPointF(20, 20)
    for _ in range(int((dodge.READY + 3.0) / 0.05) + 3):
        w.step(0.05)
        w.bullets.clear()
    check("끝까지 버티면 승리", w.result is True and w.hits == 0)
    for _ in range(int(dodge.END_SHOW / 0.05) + 3):
        w.step(0.05)
    check("결과를 보여 준 뒤 끝 (on_end)", G.get("dodge") == (True, 0))
    w2 = dodge.DodgeWindow("cirno", "치르노", lambda won, hits: G.__setitem__("dodge2", (won, hits)), 10.0,
                           rng=random.Random(2))
    w2.soul_override = QPointF(100, 100)
    for _ in range(400):
        w2.step(0.05)
        if w2.result is not None and "dodge2" in G:
            break
        if w2.result is None:
            w2.bullets.append([100.0, 100.0, 0.0, 0.0, 4.5, -1])
    check("세 번 맞으면 짐 (맞은 뒤 잠깐 무적)", G.get("dodge2") == (False, dodge.LIVES), G.get("dodge2"))
    shot = {}
    for key in dodge.STYLES:
        w3 = dodge.DodgeWindow(key, key, lambda *a: None, 6.0, boss=True, rng=random.Random(4))
        w3.soul_override = QPointF(170, 200)
        w3.inv_until = 1e9
        most = 0
        for _ in range(int((dodge.READY + 4.0) / 0.05)):
            w3.step(0.05)
            most = max(most, len(w3.bullets))
        shot[key] = most
        if key == "flandre":
            check("탄막 상자 그림", not w3.grab().isNull())
        w3.timer.stop()
        w3.close()
    check("친구 · 흑막마다 탄을 쏨", all(v >= 3 for v in shot.values()), shot)
    s.dodge_day = ""
    a = dodge.practice_reward(s, True, 0)
    check("연습 보상: 노피탄이면 2배", a == max(50, s.income_per_min * 4) * 2)
    check("지면 보상 없음", dodge.practice_reward(s, False, 3) == 0)
    for _ in range(6):
        dodge.practice_reward(s, True, 1)
    check("연습 보상은 하루 5번까지", s.dodge_today == dodge.DAILY_REWARDS and dodge.rewards_left(s) == 0)
    check("친구 탄막 연습 창이 열림", game.start_dodge("marisa", near=P["marisa"].pos_x)
          and game.dodge is not None and game.dodge.isVisible())
    check("한 번에 하나만", not game.start_dodge("reimu"))
    if game.dodge is not None:
        game.dodge.give_up()
    check("오른쪽 클릭 · ✕ 로 그만두기", game.dodge is None)


def t_hide():
    """숨바꼭질: 친구들이 화면 곳곳에 숨음."""
    from hokora import hideseek
    calm()
    close_cards()
    game._hide_ready = 0.0
    check("숨바꼭질 시작", game.start_hide() and game.hide_game is not None)
    hg = G["hide"] = game.hide_game
    if hg is None:
        return
    check("숨은 친구는 작업표시줄에서 빠짐", 2 <= len(hg.keys) <= hideseek.MAX_HIDERS
          and all(k in game._hiding for k in hg.keys) and not any(p.ch.key in hg.keys for p in game.pets))
    check("숨은 동안은 다시 나오지 않음", not any(k in game._eligible() for k in hg.keys))
    check("하는 중엔 또 못 함", not game.start_hide())


def t_hide2():
    hg = G.get("hide")
    if hg is None:
        return
    check("숨는 곳에 나타남", len(hg.spots) == len(hg.keys) and all(sp.isVisible() for sp in hg.spots.values()))
    check("숨는 곳이 제각각", len({sp.kind for sp in hg.spots.values()}) == len(hg.spots),
          [sp.kind for sp in hg.spots.values()])
    hg.next_hint = 0.0
    hg.tick()
    check("힌트: 숨은 곳이 들썩", any(time.monotonic() < sp.wiggle_until for sp in hg.spots.values()))
    before, found0 = s.saisen, s.hide_found
    spots = list(hg.spots.values())
    spots[0].mousePressEvent(None)
    check("찾으면 새전", spots[0].found and s.saisen == before + hg.reward_each() and s.hide_found == found0 + 1)
    for sp in spots[1:-1]:
        sp.mousePressEvent(None)
    G["hide_left"] = spots[-1]
    hg.ends = time.monotonic() - 1
    hg.tick()
    check("시간이 다 되면 끝 · 못 찾은 친구는 드러남", hg.over and game.hide_game is None and spots[-1].alpha == 1.0)


def t_hide3():
    hg = G.get("hide")
    if hg is None:
        return
    check("끝나면 모두 작업표시줄로", not game._hiding and all(any(p.ch.key == k for p in game.pets) for k in hg.keys))
    check("결과 카드", any("숨바꼭질" in getattr(c, "title", "") for c in game._card_queue))
    check("끝나면 잠깐 쉼", not game.start_hide())
    game._hide_ready = 0.0
    P.update({p.ch.key: p for p in game.pets})
    close_cards()


def t_race():
    """요정 달리기: 배당 = 0.9 ÷ 이길 확률, 정한 1착이 그대로 들어옴."""
    from hokora import race
    rng = random.Random(5)
    c = race.new_card(rng)
    check("출전표: 넷 · 배당 1.2 이상", len(c) == 4 and all(o >= 1.2 for _k, o, _c in c), c)
    total, n = 0.0, 20000
    for _ in range(n):
        cc = race.new_card(rng)
        win, k = race.decide(cc, rng), rng.choice(race.RUNNERS)
        total += next(o for kk, o, _c in cc if kk == k) if win == k else 0
    check("길게 보면 신사가 10% 정도", 0.85 < total / n < 0.96, round(total / n, 3))
    s.saisen = 500
    check("새전이 모자라면 못 검", race.blocked(s, 1000, False))
    s.saisen, s.race_card = 10 ** 6, []
    count0 = s.race_count
    odds = race.odds_of(s, "cirno")
    orig, race.decide = race.decide, (lambda c, rng=None: "cirno")
    try:
        ok = game.start_race("cirno", 1000)
    finally:
        race.decide = orig
    check("내기 걸고 출발", ok and game.race is not None and s.saisen == 10 ** 6 - 1000 and s.race_count == count0 + 1)
    check("달리는 중엔 또 못 검", not game.start_race("luna", 1000))
    w = game.race
    if w is None:
        return
    T = race.RACE_SECONDS
    check("1착은 정한 대로 들어옴", w.order(T)[0] == "cirno" and w.progress("cirno", T) == 1.0
          and all(w.progress(k, T) < 1 for k in w.keys if k != "cirno"))
    check("처음엔 모두 출발선", all(w.progress(k, 0.0) == 0.0 for k in w.keys))
    check("경주로 그림", not w.grab().isNull())
    G["race"] = odds
    w.started -= T - 0.3


def t_race2():
    from hokora import race
    odds = G.get("race")
    if odds is None:
        return
    check("1착이면 건 새전 × 배당", s.saisen == 10 ** 6 - 1000 + int(1000 * odds) and s.race_wins >= 1,
          (s.saisen, odds))
    check("다음 출전표가 새로 나옴", len(s.race_card) == 4)
    board = race.RaceBoard(s, lambda k, b: G.__setitem__("bet", (k, b)))
    check("출전표 창: 4명 × 3가지", len(board.buttons) == 12 and all(b.isEnabled() for b in board.buttons.values()))
    board.buttons[("star", 10_000)].click()
    check("누르면 그 친구에게 건다", G.get("bet") == ("star", 10_000))
    s.saisen = 5000
    board = race.RaceBoard(s, lambda k, b: None)
    check("새전이 모자란 칸은 못 누름", board.buttons[("luna", 1000)].isEnabled()
          and not board.buttons[("luna", 10_000)].isEnabled())
    board.close()
    s.saisen = 10 ** 6


def t_incident():
    """이변: 때가 되면 일어남 → 수입 ×0.85 · 이변의 모습 · 단서 구슬."""
    from hokora import incident
    calm()
    close_cards()
    G["level"] = s.shrine_level
    s.incident, s.incident_next, s.incident_clues, s.shrine_level = "", 0.0, 0, 1
    check("신사 1단계엔 이변 없음", incident.roll(s, 1000.0) is None and not s.incident_next)
    s.shrine_level = 2
    check("처음엔 20~40분 뒤로 예약", incident.roll(s, 1000.0) is None and 2200 <= s.incident_next <= 3400)
    base = G["base"] = prayer.income_multiplier(s)
    s.incident_next = time.time() - 1
    game._incident_tick()
    inc = incident.active(s)
    check("때가 되면 이변 발생 · 알림 카드", inc is not None
          and any("이변 발생" in getattr(c, "title", "") for c in game._card_queue))
    if inc is None:
        return
    check("이변 중엔 새전 수입 ×0.85", abs(prayer.income_multiplier(s) / base - incident.MULTIPLIER) < 1e-9)
    check("신사 둘레에 이변의 모습", game.ifx.isVisible() and game.ifx.kind == s.incident and game.ifx in game.windows())
    pics = []
    for k in incident.INCIDENTS:
        game.ifx.set_kind(k)
        game.ifx._tick()
        pics.append(game.ifx.grab().toImage())
    game.ifx.set_kind(s.incident)
    check("이변마다 모습이 다름", len({bytes(im.constBits()) for im in pics}) == 5)
    s.incident = "ufo"
    check("UFO 이변엔 UFO 4배", incident.ufo_boost(s) == 4.0)
    s.incident = inc.key
    game._clue_next = 0.0
    game._incident_tick()
    clue = game.clue
    check("단서 구슬이 떠오름", clue is not None and clue.isVisible())
    if clue is not None:
        clue.mousePressEvent(None)
    check("단서를 주우면 1/3", s.incident_clues == 1 and game.clue is None)
    game.spawn_clue()
    if game.clue is not None:
        game.clue.born -= incident.CLUE_STAY + 1
        game.clue._tick()
    game.open_panel()
    p = game.panel
    check("모험 탭: 이변 현황", "단서 1/3" in p.inc_now.text() and inc.name in p.inc_now.text(), p.inc_now.text())
    check("새전 수입 표시에 이변", inc.name in p.sub.text())
    p.close()


def t_incident2():
    from hokora import dodge, incident
    check("가만두면 단서 구슬은 사라짐", game.clue is None)
    close_cards()
    s.incident_clues = 2
    game._clue_next = 0.0
    game._incident_tick()
    if game.clue is not None:
        game.clue.mousePressEvent(None)
    check("단서 3개 → 흑막이 드러남", incident.ready(s))
    game.visits.visit = None
    check("흑막 등장", game.summon_boss() and isinstance(game.visits.visit, incident.IncidentVisit))
    v = game.visits.visit
    if not isinstance(v, incident.IncidentVisit):
        return
    G["iv"] = v
    check("흑막은 그 이변의 주인", v.boss.key == incident.active(s).boss)
    m = QMenu()
    game.visits.fill_menu(v.boss.pet, m)
    check("우클릭 → ⚔ 탄막 승부", any("탄막 승부" in a.text() for a in m.actions()))
    check("흑막을 누르면 탄막 승부 (20초)", v.fight() and game.dodge is not None and game.dodge.boss
          and game.dodge.seconds == dodge.BOSS_SECONDS)
    check("승부 중엔 또 못 함", not v.fight())
    if game.dodge is not None:
        game.dodge.give_up()
    check("지면 이변은 그대로 · 다시 도전", s.incident and v.phase in ("taunt", "wait") and not v.fighting)
    v.fight()
    before, reward, solved0 = s.saisen, incident.reward(s), incident.solved_total(s)
    d = game.dodge
    if d is not None:
        d.result, d.end_at = True, 0.0
        d.step(0.01)
    check("이기면 이변 해결 · 큰 새전", not s.incident and s.saisen == before + reward
          and incident.solved_total(s) == solved0 + 1, (s.saisen - before, reward))
    check("해결 카드", any("해결" in getattr(c, "title", "") for c in game._card_queue))
    check("이변의 모습이 걷히고 수입도 원래대로", not game.ifx.isVisible()
          and abs(prayer.income_multiplier(s) - G["base"]) < 1e-9)
    check("다음 이변은 2~4일 뒤", 2 * 86400 - 5 <= s.incident_next - time.time() <= 4 * 86400)
    check("흑막은 졌다며 돌아감", v.phase == "beaten")


def t_incident3():
    from hokora import incident
    check("흑막이 돌아가면 방문 끝", game.visits.visit is None)
    incident.start(s, "border", time.time() - incident.EXPIRE - 1)
    game._incident_tick()
    check("사흘 지나면 저절로 가라앉음", not s.incident and s.incident_next > time.time())
    w = incident.ClueWindow(incident.INCIDENTS["spring"], lambda w: None)
    check("단서 구슬 그림", not w.grab().isNull())
    w.close()
    s.shrine_level = G.get("level", s.shrine_level)
    close_cards()


def t_end():
    app.quit()


STEPS = [(t_core, 3000), (t_core2, 2500), (t_thief, 1600), (t_skill, 1800), (t_aff, 6000), (t_tag, 6000),
         (t_duel, 8500), (t_fairies, 8000), (t_fairies2, 17000), (t_aya, 20000), (t_suika, 2000),
         (t_shop, 1000), (t_season_shop, 12000), (t_tewi, 1500), (t_koishi, 7500), (t_nitori, 11000),
         (t_nitori2, 1500), (t_yuyuko, 9000), (t_yuyuko2, 1500), (t_mystia, 2500), (t_mystia2, 1500),
         (t_youmu, 0), (t_meiling, 11000), (t_reisen, 1000), (t_weather, 1500), (t_cutin, 500), (t_yukari, 6000),
         (t_yukari2, 1000), (t_patchouli, 1500), (t_expedition, 2200),
         (t_expedition2, 1000), (t_achieve, 1000), (t_fishing, 1000), (t_festival, 1000),
         (t_crowd, 1500), (t_crowd2, 1500), (t_crowd3, 2500), (t_tutorial, 2000), (t_options, 1500), (t_goods, 1800), (t_goods2, 1000), (t_ufo, 1500), (t_ufo2, 1200), (t_ufo3, 500),
         (t_cuke, 300), (t_offer, 1500), (t_offer2, 1500), (t_life, 1000), (t_settings, 500),
         (t_sengu, 500), (t_train, 500), (t_fireworks, 2500), (t_fireworks2, 2600), (t_fireworks3, 300),
         (t_letters, 300), (t_janken, 300), (t_dodge, 500), (t_hide, 2600), (t_hide2, 3600), (t_hide3, 300),
         (t_race, 1500), (t_race2, 300), (t_incident, 600), (t_incident2, 5500), (t_incident3, 300), (t_end, 0)]


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
