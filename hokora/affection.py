# -*- coding: utf-8 -*-
"""호감도·선물·말 걸기. 친해질수록 쓰다듬기 새전이 늘고, 말도 더 다정해진다."""
from __future__ import annotations

import random
from datetime import date

from .state import GameState

HEART_STEPS = [0, 5, 15, 40, 80, 150]          # 하트 1~5개가 되는 호감도
MAX_HEARTS = len(HEART_STEPS) - 1
TALK_GAIN = 2                                   # 하루 첫 대화
PAT_GAIN_EVERY = 30.0                           # 쓰다듬기로는 캐릭터마다 30초에 1씩
FAVORITE_GAIN, GIFT_GAIN = 8, 3

# 선물: 키 → (이름, 그림 문자, 새전)
GIFTS = {
    "tea": ("녹차", "🍵", 20),
    "dango": ("경단", "🍡", 30),
    "mushroom": ("버섯", "🍄", 30),
    "shaved_ice": ("빙수", "🍧", 30),
    "black_tea": ("홍차", "☕", 40),
    "pudding": ("푸딩", "🍮", 40),
    "cake": ("케이크", "🍰", 50),
    "sake": ("술", "🍶", 60),
}
FAVORITES = {
    "reimu": {"tea", "dango"},
    "marisa": {"mushroom"},
    "cirno": {"shaved_ice"},
    "sakuya": {"black_tea"},
    "sanae": {"pudding"},
    "remilia": {"black_tea", "cake"},
    "flandre": {"cake"},
}

TALK = {  # 캐릭터 → (처음엔, 친해지면)
    "reimu": (["새전함은 저쪽이야. …넣고 가는 거지?", "무슨 일이야? 요괴 퇴치 의뢰?", "차 마실래? 찻잎은 네가 가져와."],
              ["오늘도 와 줬네. 좀 쉬었다 가.", "너 덕분에 신사가 제법 신사다워졌어.", "…고마워. 새전 말고, 그냥."]),
    "marisa": (["왜 보고 있냐? 빌려 간 건 나중에 돌려준다니까.", "탄막은 파워다제!", "오, 재밌는 거 없나?"],
               ["너랑 있으면 심심할 틈이 없다제.", "비밀인데, 다음 마법 실험 도와줄래?", "레이무한텐 말하지 마, 새전 조금 빌린 거."]),
    "cirno": (["나는 최강이야!", "개구리 얼리는 법 알려 줄까?", "여름엔 내 옆에 있으면 시원하다구!"],
              ["너도 꽤 최강인데? 내 다음으로!", "우리 둘이면 무적이야!", "오늘은 특별히 얼음 조각 줄게."]),
    "sakuya": (["신사에 무슨 볼일이라도?", "아가씨께서 기다리시니 오래는 못 있어요.", "시간은 금이에요."],
               ["잠깐 시간을 멈춰서 같이 차라도 할까요?", "당신 앞에선 칼을 넣어 둘게요.", "…오늘은 조금 더 있어도 괜찮아요."]),
    "sanae": (["모리야 신사도 잘 부탁드려요!", "기적은 일어나는 거예요!", "상식에 얽매이면 안 돼요!"],
              ["우리 신사에도 놀러 와요! 신앙 대환영!", "당신이랑 있으면 기적이 자주 일어나요.", "레이무 씨한텐 비밀이지만, 여기 좋아요."]),
    "remilia": (["인간 주제에 말을 거는 거니?", "홍마관의 주인에게 예의를 갖추렴.", "운명이 보여… 흥미로운걸."],
                ["네 운명은 내가 지켜 줄게. 특별히.", "홍차 한 잔, 같이 할래?", "…다음에 홍마관에도 초대해 줄게."]),
    "flandre": (["너, 부서지지 않는 장난감이야?", "언니는 어디 갔어?", "같이 놀자! 뭐 하고 놀까?"],
                ["너는 부수지 않을게. 약속!", "언니보다 네가 더 재밌어. 비밀이야!", "오늘도 같이 놀아 줄 거지?"]),
}
TALK_DEFAULT = (["안녕!"], ["또 만났네!"])


def josa(word: str, with_final: str, without_final: str) -> str:
    """받침이 있으면 앞의 것(과·이다), 없으면 뒤의 것(와·다)을 붙인다."""
    code = ord(word[-1]) - 0xAC00
    return word + (with_final if 0 <= code < 11172 and code % 28 else without_final)


def points(s: GameState, key: str) -> int:
    return s.affection.get(key, 0)


def level(s: GameState, key: str) -> int:
    p = points(s, key)
    return max(i for i, step in enumerate(HEART_STEPS) if p >= step)


def hearts(s: GameState, key: str) -> str:
    lv = level(s, key)
    return "♥" * lv + "♡" * (MAX_HEARTS - lv)


def add(s: GameState, key: str, amount: int) -> bool:
    """호감도를 올리고, 하트가 늘었으면 True."""
    before = level(s, key)
    s.affection[key] = points(s, key) + amount
    return level(s, key) > before


def pat_bonus(s: GameState, key: str) -> int:
    """친해질수록 쓰다듬기 새전 배수 (하트 2개마다 +1)."""
    return 1 + level(s, key) // 2


def talk(s: GameState, key: str, rng: random.Random | None = None) -> tuple[str, int]:
    """(대사, 오른 호감도). 대사는 하트 3개부터 다정해지고, 하루 첫 대화에만 호감도가 오른다."""
    rng = rng or random.Random()
    low, high = TALK.get(key, TALK_DEFAULT)
    line = rng.choice(high if level(s, key) >= 3 else low)
    today = date.today().isoformat()
    gained = 0
    if s.talk_date.get(key) != today:
        s.talk_date[key] = today
        gained = TALK_GAIN
    return line, gained


def gift(s: GameState, key: str, gift_key: str) -> tuple[bool, int, bool]:
    """(줬는지, 오른 호감도, 좋아하는 선물인지). 새전이 모자라면 안 줌."""
    price = GIFTS[gift_key][2]
    if s.saisen < price:
        return False, 0, False
    s.saisen -= price
    fav = gift_key in FAVORITES.get(key, set())
    gained = FAVORITE_GAIN if fav else GIFT_GAIN
    s.gifts_given += 1
    return True, gained, fav
