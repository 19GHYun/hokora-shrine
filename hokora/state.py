# -*- coding: utf-8 -*-
"""게임 진행 상태와 저장. %APPDATA%\\Hokora\\save.json 에 원자적으로 저장한다."""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

log = logging.getLogger("Hokora.state")

APP_NAME = "Hokora"
DATA_DIR = Path(os.environ.get("APPDATA") or (Path.home() / ".local" / "share")) / APP_NAME
SAVE_FILE = DATA_DIR / "save.json"
LOG_DIR = DATA_DIR / "logs"
KEEP_BACKUPS = 7

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
    # 정원 장식 (2탄)
    "pond": ("연못", 3000, 3, 40),
    "taiko": ("큰 북", 2500, 2, 60),
    "bamboo_fence": ("대나무 울타리", 1500, 2, 54),
    "maneki_neko": ("마네키네코", 4000, 4, 62),
    "yukimi_lantern": ("유키미 석등", 2000, 2, 58),
    "maple": ("단풍나무", 3500, 3, 104),
    "suzu": ("신사 방울", 2500, 2, 76),
    "mini_torii": ("작은 도리이", 2000, 2, 66),
    "incense": ("향로", 1800, 2, 50),
    # 계절 한정 (SEASONAL 의 달에만 살 수 있음, 산 뒤에는 언제든 놓을 수 있음)
    "kadomatsu": ("카도마츠", 5000, 2, 84),
    "snowman": ("눈사람", 5000, 2, 74),
    "xmas_tree": ("크리스마스 트리", 6000, 2, 100),
    "hina": ("히나 인형", 5000, 2, 50),
    "koinobori": ("코이노보리", 6000, 2, 116),
    "tanabata": ("칠석 대나무", 5000, 2, 100),
    "sunflower": ("해바라기", 4000, 2, 70),
    "tsukimi": ("츠키미 경단", 4000, 2, 62),
    "pumpkin": ("할로윈 호박", 5000, 2, 60),
}
GARDEN = ("pond", "taiko", "bamboo_fence", "maneki_neko", "yukimi_lantern", "maple", "suzu", "mini_torii", "incense")
SEASONAL = {  # 계절 한정 장식 → 파는 달
    "kadomatsu": (12, 1), "snowman": (12, 1, 2), "xmas_tree": (11, 12), "hina": (2, 3), "koinobori": (4, 5),
    "tanabata": (6, 7), "sunflower": (7, 8), "tsukimi": (9, 10), "pumpkin": (10,),
}
# 신사 스킨: 키 → (이름, 값). 그림은 hokora/sprites/shrines/<키>.png
SHRINE_SKINS = {
    "moriya": ("모리야 신사", 15000), "snowy": ("눈 덮인 신사", 15000),
    "sakura": ("벚꽃 신사", 15000), "scarlet": ("홍마관", 20000),
}


def in_season(key: str, month: int | None = None) -> bool:
    """계절 한정 장식이면 지금 파는 달인지 (일반 장식은 늘 True)."""
    return key not in SEASONAL or (month or datetime.now().month) in SEASONAL[key]
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
    # 신사 스킨·새 손님
    shrine_skin: str = ""            # 지금 쓰는 신사 스킨 ("" = 코드로 그린 단계 모양)
    shrine_skins: list[str] = field(default_factory=list)
    nitori_until: float = 0.0        # 니토리의 증기 선풍기: 이때까지 수입 ×1.5
    koishi_found: int = 0
    tewi_luck: int = 0
    yuyuko_fed: int = 0              # 유유코를 배불리 먹인 횟수 → 3번이면 요우무
    mystia_until: float = 0.0        # 미스티아의 장어구이: 이때까지 수입 ×1.3
    meiling_blocks: int = 0          # 메이링이 새전 도둑을 막은 횟수
    reisen_until: float = 0.0        # 레이센의 피로회복약: 이때까지 쓰다듬기 새전 ×2
    dream_pill: bool = False         # 레이센의 꿈나라 약: 다음에 꺼져 있는 동안 새전함 2배
    weather_slot: str = ""           # 마지막으로 알린 날씨 시간대 (weather.slot)
    # 원정 (expedition.py)·업적 (achievements.py)·낚시 (fishing.py)
    expeditions: list[dict] = field(default_factory=list)   # [{char, place, start, end, reward}]
    expedition_done: int = 0
    achievements: list[str] = field(default_factory=list)
    title: str = ""                  # 단 칭호 (업적 키)
    fish: dict[str, int] = field(default_factory=dict)      # 낚을거리 → 낚은 수
    fish_caught: int = 0
    fish_bait: int = 0
    fish_bait_date: str = ""
    # 예대제 (festival.py)
    festival_until: float = 0.0
    festival_next: float = 0.0
    festival_start_total: int = 0
    festival_reported: bool = True
    festivals: int = 0
    tutorial: int = -1               # 처음 안내 단계 (-1 = 아직 안 정함, 99 = 끝)
    max_out: int = 0                 # 동시에 나와 있는 친구 수 (0 = 전부)
    clock_friend: bool = True        # 시계 친구 (정각마다 팻말)
    pc_react: bool = True            # PC 상태 반응 (배터리·CPU·늦은 밤·휴지통)
    cards: int = 0                   # 만든 신사 명함 수
    weather_magic: str = ""          # 파츄리의 날씨 마법
    weather_magic_until: float = 0.0
    cutin: bool = True               # 스펠카드 컷인
    show_torii: bool = True          # 센본토리이 줄을 화면에 보일지 (꺼도 분당 새전은 그대로)
    fullscreen_show: bool = False    # 영상·브라우저 전체화면에서도 숨지 않고 돌아다니기
    guest_bell: bool = False         # 손님 방울을 샀나 (손님이 오면 Windows 알림)
    guest_bell_on: bool = True       # 산 뒤 켜고 끄기
    goods: list[str] = field(default_factory=list)   # 새전으로 연 놀잇감 (goods.py: brush·room)
    ink_color: str = "sumi"          # 요술 붓 색
    ink_drawn: int = 0               # 그린 길 수
    slides: int = 0                  # 친구들이 그린 길에서 미끄럼 탄 횟수
    room_visits: int = 0             # 신사 안을 들여다본 횟수
    snacks: int = 0                  # 신사 안에서 귤·수박을 먹은 수
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
        if key not in DECOR or key in self.decor_owned or self.saisen < DECOR[key][1] or not in_season(key):
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

    @property
    def backup_dir(self) -> Path:
        return self.path.parent / "backups"

    def backup(self, force: bool = False) -> Path | None:
        """저장 파일을 backups/ 에 복사 (하루 한 번, force 면 지금). 최근 7개만 남김."""
        if not self.path.exists():
            return None
        d = self.backup_dir
        d.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        target = d / (f"save-{now:%Y%m%d-%H%M%S}.json" if force else f"save-{now:%Y%m%d}.json")
        if target.exists() and not force:
            return None
        try:
            shutil.copy2(self.path, target)
        except OSError:
            log.exception("백업 실패")
            return None
        for old in sorted(d.glob("save-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[KEEP_BACKUPS:]:
            old.unlink(missing_ok=True)
        log.info("백업: %s", target.name)
        return target

    def backups(self) -> list[tuple[Path, dict]]:
        """(백업 파일, 새전·단계·친구 요약) — 새것부터."""
        out = []
        for p in sorted(self.backup_dir.glob("save-*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                out.append((p, data if isinstance(data, dict) else {}))
            except (OSError, ValueError):
                continue
        return out

    def restore(self, backup: Path) -> bool:
        """백업을 저장 파일로 (지금 저장은 따로 백업해 둠). 이 뒤로는 저장하지 않음 — 다시 켜야 함."""
        try:
            json.loads(backup.read_text(encoding="utf-8"))
            self.backup(force=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            shutil.copy2(backup, tmp)
            _replace_retry(tmp, self.path)
        except (OSError, ValueError):
            log.exception("되돌리기 실패")
            return False
        self.readonly = True
        return True

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
            self.backup()                             # 하루 한 번 백업
            return True
        except OSError:
            log.exception("저장 실패: %s", self.path)
            return False
