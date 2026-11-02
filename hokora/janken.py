# -*- coding: utf-8 -*-
"""가위바위보: 친구를 우클릭 → ✊ 가위바위보. 친구마다 버릇이 있다.

- 치르노는 거의 늘 바위 ("최강은 주먹이야!").
- 사쿠야는 가끔 시간을 멈추고 내 손을 보고 낸다, 레밀리아는 가끔 운명을 본다 (둘 다 조금 잘 이김).
- 이기면 새전 (하루 10번까지), 그날 그 친구에게 처음 이기면 호감도도 조금.
"""
from __future__ import annotations

import random
from datetime import date

from .state import GameState

HANDS = {"rock": ("✊", "바위"), "scissors": ("✌", "가위"), "paper": ("✋", "보")}
BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}      # 왼쪽이 오른쪽을 이김
DAILY_REWARDS = 10
LINES = {
    "win": ["으아, 졌다~!", "에잇, 한 번 더!", "제법인데?"],
    "lose": ["내가 이겼다~!", "후후, 내 승리!", "아직 멀었네~"],
    "draw": ["비겼다! 한 번 더~", "어라, 똑같네?"],
}
SPECIAL = {   # 친구 → {결과: 대사}
    "cirno": {"lose": "최강은 언제나 주먹이야!", "win": "말도 안 돼! 주먹이 졌다고?!", "draw": "너도 주먹이구나! 최강끼리네!"},
    "sakuya": {"lose": "…읽혔네요. 시간을 조금 빌렸어요."},
    "remilia": {"lose": "운명이 정해 둔 결과야."},
    "flandre": {"win": "우와, 또 하자! 또!"},
}


def friend_hand(key: str, mine: str, rng: random.Random) -> str:
    winner = next(h for h, loser in BEATS.items() if loser == mine)        # 내 손을 이기는 손
    if key == "cirno":
        return "rock" if rng.random() < 0.9 else rng.choice(list(HANDS))
    if key == "sakuya" and rng.random() < 0.3:
        return winner
    if key == "remilia" and rng.random() < 0.25:
        return winner
    return rng.choice(list(HANDS))


def judge(mine: str, theirs: str) -> str:
    if mine == theirs:
        return "draw"
    return "win" if BEATS[mine] == theirs else "lose"


def play(s: GameState, key: str, mine: str, rng: random.Random | None = None) -> tuple[str, str, int, bool]:
    """(친구 손, 결과 win/lose/draw, 받은 새전, 오늘 그 친구에게 처음 이겼는지)."""
    rng = rng or random.Random()
    theirs = friend_hand(key, mine, rng)
    result = judge(mine, theirs)
    today = date.today().isoformat()
    if s.janken_day != today:
        s.janken_day, s.janken_today, s.janken_beaten = today, 0, []
    s.janken_games += 1
    reward, first = 0, False
    if result == "win":
        s.janken_wins += 1
        if s.janken_today < DAILY_REWARDS:
            s.janken_today += 1
            reward = max(10, s.income_per_min)
            s.add_saisen(reward)
        first = key not in s.janken_beaten                    # 그날 그 친구에게 처음 이김
        if first:
            s.janken_beaten.append(key)
    return theirs, result, reward, first


def line(key: str, result: str, rng: random.Random | None = None) -> str:
    rng = rng or random.Random()
    return SPECIAL.get(key, {}).get(result) or rng.choice(LINES[result])
