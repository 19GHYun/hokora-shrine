# -*- coding: utf-8 -*-
"""붕붕마루 신문(文々。新聞) 호외: 아야가 취재하고 떠나면 신사 위에 신문이 뜬다.

기사가 나면 참배객이 늘어 잠깐 동안 새전 수입이 늘어난다 (prayer.income_multiplier 가 news_until 을 봄).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .prayer import NEWS_BOOST, NEWS_SECONDS
from .render import CHARACTERS
from .sprites import image_sprites
from .state import GameState

ANSWERS = {  # 취재에 대한 대답
    "reimu": ["새전은 언제든 환영이야.", "요괴 퇴치 의뢰도 받고 있어."],
    "marisa": ["난 그냥 지나가던 마법사다제.", "새전함? 전혀 모르는 일이다제~"],
    "cirno": ["내가 최강이니까 1면에 실어!", "얼음 조각 사진도 찍어 줘!"],
    "sakuya": ["아가씨 사진은 곤란해요.", "청소는 제가 조금 도왔을 뿐이에요."],
    "sanae": ["모리야 신사도 꼭 실어 주세요!", "기적은 매일 일어나요!"],
    "remilia": ["이 신사의 운명은 밝아.", "사진은 잘 나오게 찍으렴."],
    "flandre": ["카메라 부숴도 돼?", "언니한테 보여 줄 거야!"],
}
HEADLINES = {  # 취재한 친구별 제목
    "reimu": "하쿠레이 신사 무녀, 오늘도 새전함 앞을 지키다",
    "marisa": "보통의 마법사 K씨, 새전함 근처서 또 목격",
    "cirno": "호수의 얼음 요정, 스스로 '최강' 선언",
    "sakuya": "홍마관 메이드장, 신사 청소 상태에 한마디",
    "sanae": "모리야 신사 무녀, 하쿠레이 신사서 포교?",
    "remilia": "홍마관 주인 \"이 신사의 운명은 밝다\"",
    "flandre": "악마의 여동생 신사 나들이… 기물 파손은 없어",
}


def answer_for(key: str) -> str:
    return random.choice(ANSWERS.get(key, ["잘 부탁드려요!"]))


@dataclass
class Article:
    headline: str
    lines: list[str]
    photo: str | None            # 사진에 찍힌 캐릭터 (없으면 신사 풍경 대신 기자 본인)
    boost_seconds: float = NEWS_SECONDS
    day: str = field(default_factory=lambda: date.today().isoformat())


def _stat_headlines(s: GameState) -> list[str]:
    out = []
    if s.saisen_total >= 1000:
        out.append(f"하쿠레이 신사, 누적 새전 {s.saisen_total:,} 돌파!")
    if s.thief_caught:
        out.append(f"새전 도둑 벌써 {s.thief_caught}번째 덜미… \"빌렸을 뿐\"")
    if s.fairies_caught:
        out.append(f"장난꾸러기 세 요정, 신사서 {s.fairies_caught}번째 붙잡혀")
    if s.shrine_level >= 3:
        out.append(f"'{s.stage_name}'로 거듭난 하쿠레이 신사, 참배 명소로")
    if len(s.decor_pos) >= 3:
        out.append(f"신사 새 단장, 장식 {len(s.decor_pos)}점 늘어")
    if s.suika_saisen:
        out.append("오니의 통 큰 새전, 신사에 화제")
    return out


def make_article(s: GameState, key: str | None, answer: str, thrown: bool,
                 rng: random.Random | None = None) -> Article:
    rng = rng or random.Random()
    stats = _stat_headlines(s)
    if thrown:
        headline = "취재 중이던 기자, 신사에서 내동댕이?!"
    elif key in HEADLINES and (not stats or rng.random() < 0.6):
        headline = HEADLINES[key]
    elif stats:
        headline = rng.choice(stats)
    else:
        headline = "하쿠레이 신사 탐방, 오늘의 모습은?"
    lines = []
    if key and answer:
        name = CHARACTERS[key].name if key in CHARACTERS else key
        lines.append(f"{name}: \"{answer}\"")
    if thrown:
        lines.append("기자는 \"취재의 자유를 보장하라\"고 밝혔다.")
    lines.append(f"{s.stage_name}의 새전은 지금 분당 {s.income_per_min}.")
    lines.append("기사를 본 참배객들이 몰려들고 있다!")
    return Article(headline, lines, key)


def _photo(key: str | None, size: int) -> QImage:
    """빛바랜 흑백 사진 (사진에 찍힌 캐릭터의 서 있는 모습)."""
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(QColor("#E4DCCB"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.fillRect(QRectF(0, size * 0.78, size, size * 0.22), QColor("#CFC4AE"))   # 바닥
    sprites = image_sprites(key or "aya")
    if sprites is not None:
        name = sprites.sequence("happy")[0] if key else sprites.sequence("idle")[0]
        src = sprites.images[name][0]
        gray = src.convertToFormat(QImage.Format_Grayscale8).convertToFormat(QImage.Format_ARGB32)
        gray.setAlphaChannel(src.convertToFormat(QImage.Format_Alpha8))
        sc = size * 0.86 / src.height()
        w, h = src.width() * sc, src.height() * sc
        p.drawImage(QRectF((size - w) / 2, size * 0.94 - h, w, h), gray)
    p.setCompositionMode(QPainter.CompositionMode_Multiply)     # 세피아
    p.fillRect(QRectF(0, 0, size, size), QColor(236, 214, 178))
    p.end()
    return img


class NewsCard(QWidget):
    """붕붕마루 신문 호외. 누르면 닫히고, 가만히 두면 40초 뒤 저절로 닫힌다."""

    W = 360
    PHOTO = 104

    def __init__(self, article: Article):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setCursor(Qt.PointingHandCursor)
        self.a = article
        self.f_mast = QFont("Malgun Gothic", 17)
        self.f_mast.setBold(True)
        self.f_small = QFont("Malgun Gothic", 8)
        self.f_head = QFont("Malgun Gothic", 12)
        self.f_head.setBold(True)
        self.f_body = QFont("Malgun Gothic", 9)
        self.f_foot = QFont("Malgun Gothic", 10)
        self.f_foot.setBold(True)
        self.photo = _photo(article.photo, self.PHOTO * 2)
        fm_h = QFontMetricsF(self.f_head)
        self.head_h = fm_h.boundingRect(QRectF(0, 0, self.W - 36, 999), Qt.TextWordWrap, article.headline).height()
        fm_b = QFontMetricsF(self.f_body)
        body_h = sum(fm_b.boundingRect(QRectF(0, 0, self._body_w, 999), Qt.TextWordWrap, ln).height() + 3
                     for ln in article.lines)
        self.setFixedSize(self.W, int(78 + self.head_h + 10 + max(self.PHOTO, body_h) + 44))
        QTimer.singleShot(40_000, self.close)

    @property
    def _body_w(self) -> float:
        return self.W - 36 - self.PHOTO - 12

    def show_above(self, cx: float, bottom: float) -> None:
        self.move(round(cx - self.width() / 2), round(bottom - self.height() - 8))
        self.show()

    def mousePressEvent(self, _e) -> None:
        self.close()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 6, 6)
        p.setPen(QPen(QColor(90, 70, 50, 140), 1.2))
        p.setBrush(QColor("#F6F0E2"))
        p.drawPath(path)
        ink = QColor("#2B2320")
        # 제호
        p.setFont(self.f_mast)
        p.setPen(ink)
        p.drawText(QRectF(18, 10, 200, 34), Qt.AlignLeft | Qt.AlignVCenter, "文々。新聞")
        stamp = QRectF(self.W - 74, 14, 56, 26)                   # 빨간 호외 도장
        p.setPen(QPen(QColor("#C8102E"), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(stamp, 4, 4)
        p.setFont(self.f_foot)
        p.setPen(QColor("#C8102E"))
        p.drawText(stamp, Qt.AlignCenter, "호외")
        p.setFont(self.f_small)
        p.setPen(QColor("#6E5F55"))
        p.drawText(QRectF(18, 44, self.W - 36, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{self.a.day}   ·   기자 샤메이마루 아야")
        p.setPen(QPen(ink, 2))
        p.drawLine(QPointF(18, 64), QPointF(self.W - 18, 64))
        p.setPen(QPen(ink, 0.8))
        p.drawLine(QPointF(18, 67), QPointF(self.W - 18, 67))
        # 제목
        p.setFont(self.f_head)
        p.setPen(ink)
        y = 76.0
        p.drawText(QRectF(18, y, self.W - 36, self.head_h + 2), Qt.TextWordWrap, self.a.headline)
        y += self.head_h + 10
        # 사진 + 기사
        pr = QRectF(18, y, self.PHOTO, self.PHOTO)
        p.drawImage(pr, self.photo)
        p.setPen(QPen(QColor(60, 45, 35, 160), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(pr)
        p.setFont(self.f_body)
        p.setPen(QColor("#3A302B"))
        fm = QFontMetricsF(self.f_body)
        by = y
        bx = 18 + self.PHOTO + 12
        for ln in self.a.lines:
            h = fm.boundingRect(QRectF(0, 0, self._body_w, 999), Qt.TextWordWrap, ln).height()
            p.drawText(QRectF(bx, by, self._body_w, h + 2), Qt.TextWordWrap, ln)
            by += h + 3
        y += max(self.PHOTO, by - y) + 10
        # 기사 효과
        p.setPen(QPen(QColor(60, 45, 35, 80), 1))
        p.drawLine(QPointF(18, y), QPointF(self.W - 18, y))
        p.setFont(self.f_foot)
        p.setPen(QColor("#C8102E"))
        p.drawText(QRectF(18, y + 4, self.W - 36, 26), Qt.AlignCenter,
                   f"📈 기사 효과: {int(NEWS_SECONDS // 60)}분 동안 새전 수입 ×{NEWS_BOOST:g}")
        p.end()
