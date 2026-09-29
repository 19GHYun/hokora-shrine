# -*- coding: utf-8 -*-
"""게임 진행 상태와 저장. %APPDATA%\\Hokora\\save.json 에 원자적으로 저장한다."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

log = logging.getLogger("Hokora.state")

APP_NAME = "Hokora"
DATA_DIR = Path(os.environ.get("APPDATA") or (Path.home() / ".local" / "share")) / APP_NAME
SAVE_FILE = DATA_DIR / "save.json"
LOG_DIR = DATA_DIR / "logs"

# ── 경제 ──
SHRINE_STAGES = {  # 단계 → (이름, 분당 새전)
    1: ("호코라", 2),
    2: ("신사", 5),
    3: ("대신사", 12),
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
    created: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @property
    def stage_name(self) -> str:
        return SHRINE_STAGES[self.shrine_level][0]

    @property
    def income_per_min(self) -> int:
        return SHRINE_STAGES[self.shrine_level][1]

    def add_saisen(self, amount: int) -> None:
        self.saisen += amount
        self.saisen_total += amount


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
            os.replace(tmp, self.path)
            return True
        except OSError:
            log.exception("저장 실패: %s", self.path)
            return False
