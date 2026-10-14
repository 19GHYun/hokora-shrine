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
os.environ.update(APPDATA=str(TMP / "appdata"), HOKORA_ALL="1", HOKORA_NAP_AFTER="999999",
                  HOKORA_SEASON="summer", HOKORA_NIGHT="0", HOKORA_WEATHER="cloudy")
if os.environ.get("HOKORA_SMOKE_SHOW") != "1":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hokora import app as hk  # noqa: E402
from hokora import affection as aff  # noqa: E402
from hokora import cucumber, daily, guests, ink, offering, omamori, photo, play, prayer, torii, wardrobe  # noqa: E402
from hokora import ufo as hk_ufo  # noqa: E402
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
          and win.bell_btn.isEnabled())
    win.bell_btn.click()
    check("손님 방울 사기", s.guest_bell and s.guest_bell_on and s.saisen == 1_000
          and win.bell_check.isVisible() and win.bell_check.isChecked() and not win.bell_buy.isVisible(),
          (s.saisen, win.height()))
    win.close()
    check("손님이 오면 알림", game.visits.start("tewi") and toasts and "테위" in toasts[-1][1], toasts[-1:])
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
    s.saisen, s.cuke_week, s.cuke_have, s.cuke_paid = 50_000, "", 0, 0
    got = cucumber.buy(s, 100)
    check("오이 사기 (일요일)", got == 100 and s.cuke_have == 100 and s.cuke_paid == 100 * s.cuke_base)
    now[0] = real_dt(2026, 10, 12, 9, 0)                 # 월요일 오전
    check("월요일 오전엔 아직 못 팖", cucumber.sell(s, 10) == 0 and cucumber.can_buy(now[0]))
    now[0] = real_dt(2026, 10, 14, 15, 0)                # 수요일 오후
    price = cucumber.price_now(s)
    got = cucumber.sell(s, 50)
    check("그때 시세대로 팔기", got == 50 * price and s.cuke_have == 50 and price == cucumber.prices(s)[5])
    check("평일엔 못 삼", cucumber.buy(s, 10) == 0)
    w = cucumber.CucumberWindow(game)
    w.show()
    check("오이 시세 창", w.isVisible() and len(w.btns) == 2)
    w.close()
    now[0] = real_dt(2026, 10, 18, 8, 0)                 # 다음 일요일
    check("다음 주가 되면 시듦", cucumber.refresh(s) == 50 and s.cuke_have == 0)
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
         (t_cuke, 300), (t_offer, 1500), (t_offer2, 1500), (t_life, 1000), (t_settings, 500), (t_end, 0)]


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
