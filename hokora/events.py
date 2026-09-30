# -*- coding: utf-8 -*-
"""캐릭터끼리 어울리기와 특기, 마리사의 새전 도둑질.

- 마주치면 인사: 같은 발판에서 가까이 스치면 둘 다 손을 흔든다.
- 특기 (가끔 스스로): 레이무 마당 쓸기 / 치르노 얼음 던지기(맞은 친구가 깜짝) /
  사쿠야 시간 정지(다른 친구들이 몇 초 멈춤). 마리사의 특기는 도둑질에만 쓴다.
- 새전 도둑: 가끔 마리사가 새전함으로 달려가 새전을 훔쳐 도망간다.
  도망가는 마리사를 누르거나 붙잡으면 돌려받고 보너스까지. 놓치면 그대로 잃는다.
"""
from __future__ import annotations

import logging
import random
import time
from typing import TYPE_CHECKING

from .bubble import say
from .omikuji import can_draw
from .prayer import charm_active
from .pet import RUN_SPEED as RUN
from .play import Duel, Tag, combo_for

if TYPE_CHECKING:
    from .app import Game
    from .pet import PetWindow

log = logging.getLogger("Hokora.events")

MEET_DIST = 36           # 이만큼 가까이 스치면 인사
MEET_COOLDOWN = 45.0     # 같은 둘은 이 시간(초) 동안 다시 인사하지 않음
SKILL_COOLDOWN = {"reimu": 90.0, "cirno": 120.0, "sakuya": 300.0,
                  "sanae": 240.0, "flandre": 180.0, "remilia": 600.0}
MIRACLE_SAISEN = 10
TIME_STOP = 3.0
THIEF_CHECK = 60.0       # 이 간격으로 도둑질할지 주사위
THIEF_CHANCE = 0.15      # → 평균 7분쯤에 한 번 (최소 간격 아래)
THIEF_COOLDOWN = 600.0
THIEF_MIN_SAISEN = 30
FLEE_TIME = 7.0
BUBBLE_UP = 76           # 캐릭터 발에서 말풍선 꼬리까지
PLAY_CHECK = 60.0        # 이 간격으로 놀이(술래잡기·탄막)를 할지 주사위
PLAY_CHANCE = 0.12       # → 평균 8분쯤에 한 번


class Events:
    def __init__(self, game: "Game"):
        self.game = game
        self._met: dict[frozenset, float] = {}
        self._skill_at: dict[str, float] = {}
        self._thief_next_check = time.monotonic() + THIEF_CHECK
        self._thief_last = time.monotonic() - THIEF_COOLDOWN / 2   # 켜자마자 훔치진 않게
        self.thief: PetWindow | None = None
        self.thief_phase = ""
        self.thief_until = 0.0
        self.stolen = 0
        self.tag: Tag | None = None
        self.duel: Duel | None = None
        self._play_next = time.monotonic() + PLAY_CHECK * 2

    # ── 공통 ──
    def _say(self, pet: "PetWindow", text: str, seconds: float = 2.5) -> None:
        if not self.game.hidden_for_fullscreen:
            say(text, pet.pos_x, pet.pos_y - BUBBLE_UP, seconds)

    def tick(self) -> None:
        if self.game.hidden_for_fullscreen or self.game.napping:
            return
        self._meetings()
        self._thief_tick()
        self._play_tick()

    # ── 놀이: 술래잡기·탄막놀이 ──
    def _play_tick(self) -> None:
        now = time.monotonic()
        if self.tag is not None and not self.tag.tick():
            self.tag = None
        if self.tag or self.duel or self.thief or now < self._play_next:
            return
        self._play_next = now + PLAY_CHECK
        if random.random() < PLAY_CHANCE:
            self.start_play(random.choice(("tag", "duel")))

    def start_play(self, kind: str) -> bool:
        """같은 바닥에 있는 친구들로 놀이를 시작 (사람이 모자라면 False)."""
        free = [p for p in self.game.pets if p.grounded and p.on is not None and p.on < 0]
        by_ground: dict[int, list] = {}
        for p in free:
            by_ground.setdefault(p.on, []).append(p)
        group = max(by_ground.values(), key=len, default=[])
        if kind == "tag" and len(group) >= 3:
            self.tag = Tag(self, random.sample(group, min(4, len(group))))
            return True
        if kind == "duel" and len(group) >= 2:
            a = random.choice(group)
            near = [p for p in group if p is not a and 60 < abs(p.pos_x - a.pos_x) < 420]
            if near:
                self.duel = Duel(self, a, random.choice(near))
                self.duel.destroyed.connect(lambda *_: setattr(self, "duel", None))
                self.duel.show()
                return True
        return False

    def cancel_play(self) -> None:
        if self.tag is not None:
            self.tag.end()
            self.tag = None
        if self.duel is not None:
            self.duel.finish()

    # ── 마주치면 인사 ──
    def _meetings(self) -> None:
        now = time.monotonic()
        pets = [p for p in self.game.pets if p.grounded and p.state in ("idle", "walk")]
        for i, a in enumerate(pets):
            for b in pets[i + 1:]:
                if a.on != b.on or abs(a.pos_x - b.pos_x) > MEET_DIST:
                    continue
                pair = frozenset((a.ch.key, b.ch.key))
                if now - self._met.get(pair, -1e9) < MEET_COOLDOWN:
                    continue
                self._met[pair] = now
                combo = combo_for(a, b)
                if combo:                                   # 콤비는 특별한 행동
                    x, y, (sx, sy, lx, ly, secs) = combo
                    for me, other, st in ((x, y, sx), (y, x, sy)):
                        me.act(st, secs)
                        me.facing = 1 if other.pos_x > me.pos_x else -1
                    self._say(x, lx, 2.8)
                    self.game.later(1.4, lambda: self._say(y, ly, 2.8))
                    x.hearts.append([0.0, x.width() / 2, 40])
                elif random.random() < 0.6:
                    for me, other in ((a, b), (b, a)):
                        me.act("wave", 1.8)
                        me.facing = 1 if other.pos_x > me.pos_x else -1
                    a.hearts.append([0.0, a.width() / 2, 40])

    # ── 특기 ──
    def try_skill(self, pet: "PetWindow") -> bool:
        key = pet.ch.key
        cool = SKILL_COOLDOWN.get(key)
        now = time.monotonic()
        if cool is None or now - self._skill_at.get(key, -1e9) < cool or not pet.grounded:
            return False
        if self.game.napping or self.game.hidden_for_fullscreen:
            return False
        self._skill_at[key] = now
        if key == "reimu":
            pet.act("skill", random.uniform(4, 7))
            if random.random() < 0.3:
                self._say(pet, random.choice(["오늘도 깨끗하게~", "새전 좀 들어오라~"]))
        elif key == "cirno":
            pet.act("skill", 1.2)
            target = self._nearest(pet, 260)
            if target is not None:
                pet.facing = 1 if target.pos_x > pet.pos_x else -1
                self.game.later(0.7, lambda: target.grounded and target.react(False))
            self._say(pet, random.choice(["나는 최강이야!", "에잇!", "얼음 맛 좀 봐라!"]))
        elif key == "sakuya":
            pet.act("skill", 1.2)
            self.game.later(0.9, lambda: self._time_stop(pet))
        elif key == "sanae":
            pet.act("skill", 1.4)
            self.game.later(1.0, lambda: self._miracle(pet))
        elif key == "flandre":
            pet.act("skill", 1.2)
            targets = [o for o in self.game.pets if o is not pet and o.grounded and o.on == pet.on
                       and abs(o.pos_x - pet.pos_x) < 220]
            if targets:
                pet.facing = 1 if targets[0].pos_x > pet.pos_x else -1
            self.game.later(0.6, lambda: self._blast(pet, targets))
            self._say(pet, random.choice(["와장창~!", "같이 놀자!", "꽈광!"]))
        elif key == "remilia":
            if not can_draw(self.game.state) or self.game.state.fate_boost:
                self._skill_at[key] = now - cool + 60    # 조작할 운명이 없으면 1분 뒤 다시
                return False
            pet.act("skill", 1.6)
            self.game.state.fate_boost = True
            self._say(pet, "오늘의 운명은 내가 정했어.")
            log.info("레밀리아 운명 조작 → 다음 오미쿠지 대길·중길")
        return True

    def _miracle(self, sanae: "PetWindow") -> None:
        g = self.game
        g.state.add_saisen(MIRACLE_SAISEN)
        g.shrine.set_saisen(g.state.saisen)
        g.shrine.pop(f"+{MIRACLE_SAISEN}")
        self._say(sanae, "기적이 일어났어요!")
        g.check_unlocks()

    def _blast(self, flan: "PetWindow", targets: list) -> None:
        """레바테인 한 방: 근처 친구들이 통 튕겨 날아간다 (다치진 않음)."""
        for o in targets:
            if not o.grounded:
                continue
            away = 1 if o.pos_x >= flan.pos_x else -1
            o.on, o.state = None, "fall"
            o.vx, o.vy = away * random.uniform(220, 360), -random.uniform(450, 650)

    def _nearest(self, pet: "PetWindow", reach: float):
        others = [o for o in self.game.pets if o is not pet and o.on == pet.on and abs(o.pos_x - pet.pos_x) < reach]
        return min(others, key=lambda o: abs(o.pos_x - pet.pos_x)) if others else None

    def _time_stop(self, sakuya: "PetWindow") -> None:
        others = [p for p in self.game.pets if p is not sakuya and p.state != "held"]
        if not others:
            return
        self._say(sakuya, "시간이여, 멈춰라.")
        for p in others:
            p.freeze(TIME_STOP)
        log.info("사쿠야 시간 정지 (%d명)", len(others))

    # ── 새전 도둑 ──
    def _thief_tick(self) -> None:
        now = time.monotonic()
        if self.thief is None:
            if now >= self._thief_next_check:
                self._thief_next_check = now + THIEF_CHECK
                if (now - self._thief_last >= THIEF_COOLDOWN and not charm_active(self.game.state)
                        and random.random() < THIEF_CHANCE):
                    self.start_thief()
            return
        m = self.thief
        shrine = self.game.shrine
        if self.thief_phase == "approach":
            if not m.scripted or m.on is None:          # 도중에 잡혀서 던져짐 → 취소
                return self._end_thief("취소")
            if abs(m.pos_x - shrine.pos_x) < 18 or m.vx == 0:
                self._steal()
        elif self.thief_phase == "steal":
            if m.state == "held":
                return self.catch()
            if now >= self.thief_until:
                away = 1 if m.pos_x >= shrine.pos_x else -1
                g = self.game.ground_under(m.pos_x)
                if (g.x2 - m.pos_x) > (m.pos_x - g.x1) * 1.5:  # 한쪽이 훨씬 넓으면 넓은 쪽으로
                    away = 1
                elif (m.pos_x - g.x1) > (g.x2 - m.pos_x) * 1.5:
                    away = -1
                m.act("run", FLEE_TIME, vx=away * RUN)
                self.thief_phase, self.thief_until = "flee", now + FLEE_TIME
        elif self.thief_phase == "flee":
            if m.state == "held":
                return self.catch()
            if now >= self.thief_until or m.vx == 0:
                self._say(m, "다음엔 잡아 보라고~!")
                log.info("마리사 도망 성공: 새전 %d 잃음", self.stolen)
                self._end_thief("도망")

    def start_thief(self, force: bool = False) -> bool:
        """마리사가 새전함으로 달려간다. 조건이 안 맞으면 False."""
        g = self.game
        m = next((p for p in g.pets if p.ch.key == "marisa"), None)
        if m is None or not m.grounded or m.state == "sleep":
            return False
        if not force and g.state.saisen < THIEF_MIN_SAISEN:
            return False
        if m.on != g.ground_under(g.shrine.pos_x).hwnd:   # 신사와 같은 바닥에 있을 때만
            return False
        self.thief, self.thief_phase = m, "approach"
        self._thief_last = time.monotonic()
        m.scripted = True
        d = 1 if g.shrine.pos_x > m.pos_x else -1
        m.act("run", 60, vx=d * RUN * 0.7)
        log.info("마리사가 새전함으로 간다")
        return True

    def _steal(self) -> None:
        m, g = self.thief, self.game
        amount = int(min(max(5, g.state.saisen * 0.1), 100, g.state.saisen))
        g.state.saisen -= amount
        self.stolen = amount
        g.shrine.set_saisen(g.state.saisen)
        g.shrine.pop(f"-{amount}")
        m.act("skill", 1.4)
        m.facing = 1 if g.shrine.pos_x > m.pos_x else -1
        self._say(m, "잠깐 빌려갈게~!")
        self.thief_phase, self.thief_until = "steal", time.monotonic() + 1.4
        log.info("마리사가 새전 %d 훔침", amount)

    def catch(self) -> None:
        """도둑질 중인 마리사를 붙잡음 → 돌려받고 보너스."""
        m, g = self.thief, self.game
        if m is None or self.thief_phase not in ("steal", "flee"):
            return
        bonus = max(5, self.stolen // 2)
        g.state.saisen += self.stolen
        g.state.add_saisen(bonus)
        g.state.thief_caught += 1
        g.shrine.set_saisen(g.state.saisen)
        g.shrine.pop(f"+{self.stolen + bonus}")
        if m.state != "held":
            m.act("caught", 1.6)
        self._say(m, random.choice(["쳇, 들켰네…", "빌린 거라니까~!", "알았어, 돌려줄게…"]))
        log.info("마리사 잡음: %d 돌려받고 보너스 %d", self.stolen, bonus)
        self._end_thief("잡힘")
        g.check_unlocks()
        g.save()

    def _end_thief(self, why: str) -> None:
        log.debug("도둑 이벤트 끝: %s", why)
        if self.thief is not None:
            self.thief.scripted = False
            if self.thief.state == "run":
                self.thief.act("idle", 1.0)
        self.thief, self.thief_phase, self.stolen = None, "", 0

    def cancel_thief(self) -> None:
        """낮잠·불러오기 등으로 도둑질을 그만둠 (훔친 새전은 조용히 되돌림)."""
        if self.thief is None:
            return
        if self.stolen:
            self.game.state.saisen += self.stolen
            self.game.shrine.set_saisen(self.game.state.saisen)
        self._end_thief("취소")

    def is_fleeing(self, pet: "PetWindow") -> bool:
        return pet is self.thief and self.thief_phase in ("steal", "flee")

