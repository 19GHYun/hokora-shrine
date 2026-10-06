# -*- coding: utf-8 -*-
"""게임 진행 상태와 저장. %APPDATA%\\Hokora\\save.json 에 원자적으로 저장한다."""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

log = logging.getLogger("Hokora.state")

APP_NAME = "Hokora"
DATA_DIR = Path(os.environ.get("APPDATA") or (Path.home() / ".local" / "share")) / APP_NAME
SAVE_FILE = DATA_DIR / "save.json"
LOG_DIR = DATA_DIR / "logs"

# ── 경제 ──
SHRINE_STAGES = {  # 단계 → (이름, 분당 새전, 이 단계로 올리는 비용)
    1: ("호코라", 2, 0),
    2: ("신사", 5, 300),
    3: ("대신사", 12, 1500),
    4: ("명소 신사", 25, 5000),
    5: ("환상향 제일 신사", 50, 15000),
}
# 새전함: 단계 → (꺼져 있는 동안 최대 몇 시간, 그동안 수입의 몇 %, 이 단계로 올리는 비용)
SAISEN_BOX = {
    0: (1, 0.25, 0),
    1: (2, 0.5, 300),
    2: (4, 0.5, 1000),
    3: (8, 0.75, 3000),
    4: (12, 1.0, 8000),
}
MAX_STAGE = max(SHRINE_STAGES)
# 신사 장식: 키 → (이름, 가격, 분당 새전 보너스, 화면에서의 높이 px)
DECOR = {
    "furin": ("풍경", 150, 1, 78),
    "lantern": ("돌등롱", 200, 1, 72),
    "omikuji_rack": ("오미쿠지 걸이", 300, 1, 62),
    "ema_rack": ("에마 걸이", 300, 1, 62),
    "fox": ("여우 석상", 400, 1, 60),
    "umbrella": ("빨간 양산", 500, 1, 76),
    "temizuya": ("손 씻는 물", 600, 2, 48),
    "sakura": ("벚꽃나무", 800, 2, 112),
    "saisen_box": ("큰 새전함", 1000, 3, 46),
}
PAT_REWARD = 1           # 쓰다듬기 한 번에 새전
PAT_COOLDOWN = 1.5       # 같은 캐릭터를 연타해도 보상은 이 간격(초)마다


@dataclass
class GameState:
    version: int = 1
    saisen: int = 0                  # 지금 가진 새전
    saisen_total: int = 0            # 지금까지 모은 새전 (해금 조건용)
    shrine_level: int = 1
    unlocked: list[str] = field(default_factory=lambda: ["reimu"])
    pats: int = 0
    runtime_sec: float = 0.0         # 켜 둔 시간 누적
    shrine_x: float = 0.82           # 신사 위치 (화면 폭 대비 0~1)
    income_carry: float = 0.0        # 분당 수입의 소수점 이월
    climb: bool = True               # 캐릭터가 열려 있는 창 위에도 올라감
    cursor_play: bool = True         # 마우스 커서 위에 올라타기·따라가기
    omikuji_date: str = ""           # 마지막으로 오미쿠지를 뽑은 날 (YYYY-MM-DD)
    omikuji_count: int = 0
    decor_owned: list[str] = field(default_factory=list)       # 산 장식
    decor_pos: dict[str, float] = field(default_factory=dict)  # 놓아 둔 장식 → x 위치
    show_decor: bool = True          # 장식을 화면에 보일지 (꺼도 놓아 둔 장식의 효과는 그대로)
    thief_caught: int = 0
    box_level: int = 0               # 새전함 단계 (꺼져 있는 동안의 수입)
    affection: dict[str, int] = field(default_factory=dict)   # 캐릭터 → 호감도 (affection.py)
    talk_date: dict[str, str] = field(default_factory=dict)   # 캐릭터 → 마지막으로 말 건 날
    gifts_given: int = 0
    last_seen: float = 0.0           # 마지막으로 저장한 실제 시각 (time.time) — 꺼져 있던 시간 계산용
    night_sec: float = 0.0           # 밤(20시~5시)에 함께한 시간 — 레밀리아
    fate_boost: bool = False
    # 참배(prayer.py): 효과가 끝나는 시각(time.time 기준)
    buff_income_until: float = 0.0
    buff_pat_until: float = 0.0
    charm_until: float = 0.0
    omikuji_extra: int = 0           # 오늘 더 뽑을 수 있는 오미쿠지 수
    wishes_made: int = 0         # 레밀리아가 운명을 조작함 → 다음 오미쿠지는 좋은 운세
    # 손님 (guests.py)
    guest_visits: dict[str, int] = field(default_factory=dict)   # 손님 → 다녀간 횟수
    fairies_caught: int = 0
    suika_saisen: int = 0            # 스이카가 두고 간 새전 합계
    news: list[str] = field(default_factory=list)   # 붕붕마루 신문 최근 제목 (최대 5개, 오래된 것부터)
    news_until: float = 0.0          # 기사 효과가 끝나는 시각 (time.time)
    # 오늘의 부탁·출석 도장 (daily.py)
    daily_date: str = ""
    daily_tasks: list[dict] = field(default_factory=list)   # [{kind, goal, count, reward, done}]
    daily_base_total: int = 0        # 그날 시작할 때의 모은 새전·함께한 시간 (새전 모으기·함께 지내기 부탁용)
    daily_base_runtime: float = 0.0
    daily_done: int = 0              # 지금까지 들어준 부탁 수
    attend_last: str = ""            # 마지막으로 출석 도장을 찍은 날
    attend_streak: int = 0
    attend_days: int = 0
    season_fx: bool = True           # 계절 연출 (벚꽃잎·단풍잎·눈·반딧불)
    photos: int = 0
    # 보이는 모습
    shrine_look: int = 0             # 신사 모양 (0 = 가장 높이 올린 단계 그대로, 1~ = 그 단계 모양)
    size_scale: float = 1.0          # 신사·캐릭터·장식 크기 (1.0 보통, 0.85 작게, 0.7 아주 작게)
    resting: list[str] = field(default_factory=list)   # 신사에서 쉬는(작업표시줄에 안 나오는) 친구
    # 센본토리이 (torii.py)·부적 (omamori.py)
    torii: int = 0
    omamori: dict[str, int] = field(default_factory=dict)   # 부적 → 레벨
    equipped: list[str] = field(default_factory=list)       # 지닌 부적 (최대 3개)
    gacha_pulls: int = 0
    gacha_pity: int = 0              # 마지막 전설 부적 뒤로 뽑은 횟수
    # 의상실 (wardrobe.py)
    wardrobe: list[str] = field(default_factory=list)       # 가진 옷·이펙트 ("reimu:blue", "fx:hearts")
    skins: dict[str, str] = field(default_factory=dict)     # 캐릭터 → 입은 옷 (없으면 기본)
    effects: dict[str, str] = field(default_factory=dict)   # 캐릭터 → 이펙트
    cloth: int = 0                   # 옷감 (중복으로 모임 → 원하는 것 교환)
    wardrobe_pulls: int = 0
    wardrobe_pity: int = 0
    created: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @property
    def stage_name(self) -> str:
        return SHRINE_STAGES[self.shrine_level][0]

    @property
    def decor_bonus(self) -> int:
        return sum(DECOR[k][2] for k in self.decor_pos if k in DECOR)

    @property
    def income_per_min(self) -> int:
        return SHRINE_STAGES[self.shrine_level][1] + self.decor_bonus + self.torii // 2   # 도리이 2개마다 +1

    def buy_decor(self, key: str) -> bool:
        if key not in DECOR or key in self.decor_owned or self.saisen < DECOR[key][1]:
            return False
        self.saisen -= DECOR[key][1]
        self.decor_owned.append(key)
        return True

    @property
    def look_stage(self) -> int:
        """화면에 보일 신사 모양 (수입은 shrine_level 그대로)."""
        return self.shrine_look if 1 <= self.shrine_look <= self.shrine_level else self.shrine_level

    @property
    def next_stage_cost(self) -> int | None:
        """다음 단계로 올리는 비용 (이미 최고 단계면 None)."""
        nxt = SHRINE_STAGES.get(self.shrine_level + 1)
        return nxt[2] if nxt else None

    def add_saisen(self, amount: int) -> None:
        self.saisen += amount
        self.saisen_total += amount

    @property
    def next_box_cost(self) -> int | None:
        nxt = SAISEN_BOX.get(self.box_level + 1)
        return nxt[2] if nxt else None

    def upgrade_box(self) -> bool:
        cost = self.next_box_cost
        if cost is None or self.saisen < cost:
            return False
        self.saisen -= cost
        self.box_level += 1
        return True

    def upgrade_shrine(self) -> bool:
        cost = self.next_stage_cost
        if cost is None or self.saisen < cost:
            return False
        self.saisen -= cost
        self.shrine_level += 1
        return True


def _replace_retry(src: Path, dst: Path, tries: int = 8) -> None:
    """Windows 에선 방금 쓴 파일을 백신·검색 색인이 잠깐 잡고 있어 교체가 거부될 때가 있다 → 잠깐 뒤 다시."""
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.05 * (i + 1))


class SaveStore:
    """calendar 앱의 NoteStore 와 같은 방식: 임시 파일에 쓰고 교체, 깨진 파일은 따로 보관."""

    def __init__(self, path: Path = SAVE_FILE):
        self.path = path
        self.readonly = False
        self.problem: str | None = None

    def load(self) -> GameState:
        if not self.path.exists():
            log.info("저장 파일 없음 — 새 게임: %s", self.path)
            return GameState()
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError as e:
            self.readonly = True
            self.problem = f"저장 파일을 읽지 못해 저장을 막아두었습니다.\n{self.path}\n{e}"
            log.exception("저장 파일 읽기 실패")
            return GameState()
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("최상위가 dict 가 아님")
            known = GameState.__dataclass_fields__
            state = GameState(**{k: v for k, v in data.items() if k in known})
            if state.shrine_level not in SHRINE_STAGES:
                raise ValueError(f"알 수 없는 신사 단계: {state.shrine_level}")
            if not isinstance(state.unlocked, list) or not state.unlocked:
                state.unlocked = ["reimu"]
            log.info("불러옴: 새전 %d, 신사 %s, 캐릭터 %s", state.saisen, state.stage_name, state.unlocked)
            return state
        except (ValueError, TypeError) as e:
            backup = self.path.with_name(f"save.corrupt-{datetime.now():%Y%m%d-%H%M%S}.json")
            try:
                self.path.replace(backup)
                self.problem = f"저장 파일이 손상되어 따로 보관하고 새로 시작합니다.\n보관 위치: {backup}\n원인: {e}"
            except OSError:
                self.readonly = True
                self.problem = f"저장 파일이 손상됐고 보관에도 실패해 저장을 막아두었습니다.\n원인: {e}"
            log.exception("저장 파일 형식 오류")
            return GameState()

    def save(self, state: GameState) -> bool:
        if self.readonly:
            return False
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(asdict(state), f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            _replace_retry(tmp, self.path)
            return True
        except OSError:
            log.exception("저장 실패: %s", self.path)
            return False
