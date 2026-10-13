# -*- coding: utf-8 -*-
"""업적: 지금까지 해 온 것들에 한 번씩 큰 보상. 달성한 업적은 칭호로 달 수 있다 (신사 관리 창·사진에 나옴).

처음 업데이트했을 때 이미 채운 업적이 많으면 한 장의 카드로 모아서 알려 준다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import affection as aff
from . import omamori
from .state import DECOR, GameState

# 보상 등급 → (새전, 옷감)
TIER = {1: (300, 0), 2: (1500, 5), 3: (5000, 15), 4: (20000, 40)}


@dataclass(frozen=True)
class Achievement:
    key: str
    icon: str
    name: str          # 칭호로도 씀
    desc: str
    check: Callable[[GameState], bool]
    tier: int

    @property
    def reward(self) -> tuple[int, int]:
        return TIER[self.tier]


def _hearts5(s: GameState) -> int:
    return sum(1 for k in s.unlocked if aff.level(s, k) >= aff.MAX_HEARTS)


def _guests_met(s: GameState) -> int:
    from .guests import VISITS                    # guests 가 무거워서 필요할 때만
    keys = [k for ks, _ in VISITS.values() for k in ks]
    return sum(1 for k in keys if s.guest_visits.get(k))


def _guest_total() -> int:
    from .guests import VISITS
    return sum(len(ks) for ks, _ in VISITS.values())


def _all_chars() -> int:
    from .render import CHARACTERS
    return len(CHARACTERS)


A = Achievement
ACHIEVEMENTS = {a.key: a for a in [
    A("pat100", "🤚", "쓰다듬기 입문", "친구를 100번 쓰다듬기", lambda s: s.pats >= 100, 1),
    A("pat1000", "🤚", "쓰다듬기 달인", "친구를 1,000번 쓰다듬기", lambda s: s.pats >= 1000, 2),
    A("pat10000", "🤚", "신의 손", "친구를 10,000번 쓰다듬기", lambda s: s.pats >= 10000, 4),
    A("total10k", "💰", "작은 부자 신사", "새전을 모두 합쳐 10,000 모으기", lambda s: s.saisen_total >= 10_000, 1),
    A("total100k", "💰", "번창하는 신사", "새전을 모두 합쳐 100,000 모으기", lambda s: s.saisen_total >= 100_000, 2),
    A("total1m", "💰", "환상향의 부호", "새전을 모두 합쳐 1,000,000 모으기", lambda s: s.saisen_total >= 1_000_000, 4),
    A("stage3", "⛩", "대신사의 주인", "신사를 3단계로 키우기", lambda s: s.shrine_level >= 3, 1),
    A("stage5", "⛩", "환상향 제일", "신사를 5단계로 키우기", lambda s: s.shrine_level >= 5, 3),
    A("torii10", "⛩", "참배길", "도리이 10개 봉납", lambda s: s.torii >= 10, 1),
    A("torii100", "⛩", "도리이 숲", "도리이 100개 봉납", lambda s: s.torii >= 100, 3),
    A("torii1000", "⛩", "센본토리이", "도리이 1,000개 봉납", lambda s: s.torii >= 1000, 4),
    A("friends5", "👭", "북적이는 신사", "친구 5명 만나기", lambda s: len(s.unlocked) >= 5, 1),
    A("friendsall", "👭", "환상향 모두의 신사", "친구를 모두 만나기", lambda s: len(s.unlocked) >= _all_chars(), 3),
    A("guests5", "🙋", "손님 맞이", "손님 5명 만나기", lambda s: _guests_met(s) >= 5, 1),
    A("guestsall", "🙋", "환상향 사교계", "손님을 모두 만나기", lambda s: _guests_met(s) >= _guest_total(), 3),
    A("heart1", "💕", "단짝", "하트 5개 친구 1명", lambda s: _hearts5(s) >= 1, 2),
    A("heart3", "💕", "모두의 친구", "하트 5개 친구 3명", lambda s: _hearts5(s) >= 3, 3),
    A("gift50", "🎁", "선물 대장", "선물 50번 하기", lambda s: s.gifts_given >= 50, 2),
    A("thief10", "🕵", "도둑 잡는 무녀", "새전 도둑 10번 잡기", lambda s: s.thief_caught >= 10, 1),
    A("thief50", "🕵", "마리사의 천적", "새전 도둑 50번 잡기", lambda s: s.thief_caught >= 50, 3),
    A("guard10", "🚪", "든든한 문지기", "메이링이 도둑을 10번 막기", lambda s: s.meiling_blocks >= 10, 2),
    A("fairy10", "🧚", "요정 사냥꾼", "장난치는 요정 10번 잡기", lambda s: s.fairies_caught >= 10, 2),
    A("koishi5", "👁", "무의식을 보는 눈", "숨은 코이시 5번 찾기", lambda s: s.koishi_found >= 5, 2),
    A("yuyuko10", "🍙", "명계의 요리사", "유유코를 배불리 먹이기 10번", lambda s: s.yuyuko_fed >= 10, 2),
    A("omikuji30", "🔮", "운세 마니아", "오미쿠지 30번 뽑기", lambda s: s.omikuji_count >= 30, 1),
    A("attend7", "💮", "개근상", "7일 연속 출석", lambda s: s.attend_streak >= 7, 1),
    A("attend30", "💮", "한 달의 정성", "모두 30일 출석", lambda s: s.attend_days >= 30, 3),
    A("daily30", "✅", "부탁 해결사", "오늘의 부탁 30개 들어주기", lambda s: s.daily_done >= 30, 2),
    A("photo10", "📸", "신사 사진사", "사진 10장 찍기", lambda s: s.photos >= 10, 1),
    A("charmall", "🎴", "부적 수집가", "부적 15종 모두 모으기", lambda s: len(s.omamori) >= len(omamori.CHARMS), 3),
    A("gacha100", "🎴", "뽑기의 신", "부적·의상 뽑기 합쳐 100번", lambda s: s.gacha_pulls + s.wardrobe_pulls >= 100, 2),
    A("wardrobe30", "👘", "멋쟁이 신사", "옷·이펙트 30개 모으기", lambda s: len(s.wardrobe) >= 30, 2),
    A("decor10", "🏮", "꾸미기 장인", "장식 10개 사기", lambda s: len(s.decor_owned) >= 10, 1),
    A("decorall", "🏮", "환상향 정원사", "장식 모두 사기", lambda s: len(s.decor_owned) >= len(DECOR), 4),
    A("expedition10", "🗺", "모험의 시작", "원정 10번 다녀오기", lambda s: s.expedition_done >= 10, 2),
    A("expedition50", "🗺", "환상향 탐험가", "원정 50번 다녀오기", lambda s: s.expedition_done >= 50, 3),
    A("festival1", "🎆", "축제의 시작", "예대제 열기", lambda s: s.festivals >= 1, 1),
    A("festival5", "🎆", "축제의 신사", "예대제 5번 열기", lambda s: s.festivals >= 5, 3),
    A("fish50", "🎣", "낚시꾼", "물고기 50마리 낚기", lambda s: s.fish_caught >= 50, 2),
    A("fishall", "🎣", "연못의 주인", "낚을거리 12종 모두 낚기", lambda s: len(s.fish) >= 12, 3),
]}


def check(s: GameState) -> list[Achievement]:
    """새로 달성한 업적들 (보상은 여기서 줌)."""
    new = []
    for a in ACHIEVEMENTS.values():
        if a.key not in s.achievements and a.check(s):
            s.achievements.append(a.key)
            saisen, cloth = a.reward
            s.add_saisen(saisen)
            s.cloth += cloth
            new.append(a)
    return new


def title(s: GameState) -> str:
    a = ACHIEVEMENTS.get(s.title)
    return a.name if a and a.key in s.achievements else ""


def reward_text(a: Achievement) -> str:
    saisen, cloth = a.reward
    return f"새전 +{saisen:,}" + (f" · 옷감 +{cloth}" if cloth else "")

