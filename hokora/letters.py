# -*- coding: utf-8 -*-
"""친구 편지: 하트가 하나 늘 때마다 그 친구에게서 편지가 한 통 온다 (친구마다 5통, 모두 45통).

- 새로 온 편지는 카드로 알려 주고, 누르면 편지지가 펼쳐진다. 지난 편지는 우클릭 → 💌 편지함에서 다시 읽는다.
- 이미 친해져 있던 친구의 편지는 한꺼번에 오지만, 알림은 한 장으로 묶는다.
- 다섯 번째 편지에는 작은 선물(옷감)이 들어 있다.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import affection as aff
from .diary import DiaryCard
from .render import CHARACTERS, short_name
from .state import GameState

LAST_GIFT = 20                       # 다섯 번째 편지에 든 옷감

# 친구 → [(제목, 본문, 서명)] — 하트 1 · 2 · 3 · 4 · 5 개가 될 때 한 통씩
LETTERS: dict[str, list[tuple[str, str, str]]] = {
    "reimu": [
        ("새전함 이야기", "이걸 편지라고 부르기도 쑥스럽지만… 요즘 새전함이 조금 무거워졌어.\n"
         "네가 자주 들러 줘서 그런가 봐. 고맙다는 말은 한 번만 할 거야.", "레이무"),
        ("차 마시러 와", "신사 툇마루에서 마시는 차는 혼자보다 둘이 낫더라.\n"
         "찻잎은 내가 준비할 테니 화과자는 네가 가져와. 그게 공평하잖아?", "레이무"),
        ("요괴 퇴치 다녀왔어", "어젯밤 이변 비슷한 게 있어서 다녀왔는데, 돌아와 보니 네가 신사를 지켜 주고 있더라.\n"
         "덕분에 푹 잤어. 다음엔 같이 가 볼래? 위험하면 내가 지켜 줄게.", "레이무"),
        ("비밀", "마리사한텐 말하지 마.\n사실 너랑 보내는 시간이 꽤 좋아.\n…새전 얘기가 아니라는 건 알아 둬.", "레이무"),
        ("너의 신사", "처음엔 작은 호코라였는데, 이제 어엿한 신사가 됐네.\n"
         "이건 내 신사이기도 하지만, 네 신사이기도 해.\n앞으로도 잘 부탁해. 진심이야.", "하쿠레이 레이무"),
    ],
    "marisa": [
        ("빌린 거 아니라구", "레이무네 새전함에서 몇 개 빌린 건 사실인데, 언젠가 돌려줄 거다제! 아마도.\n"
         "그것보다 너, 버섯 좋아하냐?", "마리사"),
        ("버섯 수프", "마법의 숲에서 딴 버섯으로 수프를 끓였는데 너무 많이 만들었다제.\n"
         "먹으러 와. 색깔이 좀 이상해도 맛은 보장한다! (아마도)", "마리사"),
        ("새 마법", "새로운 스펠카드를 연구 중이다제. 이름은 아직 비밀인데,\n"
         "완성되면 네가 제일 먼저 보는 거다! 탄막은 파워라구.", "마리사"),
        ("고마워", "요즘 내가 신사에 자주 오는 이유? 새전 때문… 만은 아니라제.\n"
         "너랑 노는 게 재밌어서다. 이런 말 하니까 간지럽네!", "마리사"),
        ("약속", "앞으로 이 신사 새전은 안 빌리기로 했다제. 진짜로! 너랑 한 약속이니까.\n"
         "…레이무 거는 별개지만. 헤헤.", "키리사메 마리사"),
    ],
    "cirno": [
        ("최강의 편지", "이건 최강인 내가 쓴 최강의 편지야! 읽으면 시원해질걸?\n아, 편지가 좀 얼었으면 미안.", "치르노"),
        ("개구리 얼리기 대회", "어제 개구리 얼리기 대회를 했는데 내가 1등 했어!\n"
         "참가자는 나 혼자였지만 1등은 1등이야!", "치르노"),
        ("부하 1호", "대요정이 그러는데 너 착한 사람이래.\n그래서 특별히 내 부하 1호로 임명할게! 영광으로 알라구!", "치르노"),
        ("더운 날엔", "더운 날엔 나한테 와! 신사 옆에서 얼음 조각 만들어 줄게.\n무료야! 친구니까!", "치르노"),
        ("최강 콤비", "너랑 나랑 둘이면 진짜로 무적이야. 레이무도 마리사도 이길 수 있어!\n"
         "…그러니까 앞으로도 쭉 같이 있자. 약속이다!", "최강의 치르노"),
    ],
    "sakuya": [
        ("메이드장으로서", "아가씨께서 신사에 다녀오라 하셔서 들렀습니다.\n"
         "깔끔하게 관리되고 있더군요. 메이드장으로서 칭찬해 드리지요.", "이자요이 사쿠야"),
        ("홍차 끓이는 법", "찻잎은 넉넉히, 물은 막 끓은 것으로, 시간은… 제가 멈춰 두면 되니 신경 쓰지 마세요.\n"
         "다음에 직접 끓여 드릴게요.", "사쿠야"),
        ("멈춘 시간 속에서", "가끔 시간을 멈추고 혼자 있을 때가 있어요. 조용해서 좋지만 조금 쓸쓸하죠.\n"
         "요즘은 그때 당신 생각을 하곤 합니다. …못 들은 걸로 해 주세요.", "사쿠야"),
        ("문지기 이야기", "문지기가 또 졸고 있었어요. 그런데 당신 이야기를 하니 벌떡 일어나더군요.\n"
         "당신은 홍마관에서도 인기가 많은 모양이에요.", "사쿠야"),
        ("당신의 시간", "제 시간은 모두 아가씨의 것이지만,\n차 한 잔 마실 시간 정도는 당신에게 드려도 괜찮겠죠.\n"
         "언제든 불러 주세요.", "이자요이 사쿠야"),
    ],
    "sanae": [
        ("모리야 신사에서 인사드려요", "안녕하세요! 모리야 신사의 무녀, 코치야 사나에예요.\n"
         "이 신사도 신앙이 가득하네요! 서로 경쟁… 아니, 협력해요!", "사나에"),
        ("기적 일으키기 연습", "오늘은 기적을 세 번이나 일으켰어요!\n"
         "하나는 잃어버린 머리핀 찾기, 하나는 맑은 날씨, 하나는… 당신이 신사에 와 준 거예요!", "사나에"),
        ("스와코 님과 카나코 님", "두 신님께 당신 이야기를 했더니 꼭 한번 데려오래요.\n"
         "개구리 모자를 쓴 분이 스와코 님이에요. 귀엽다고 하면 좋아하세요!", "사나에"),
        ("상식에 얽매이지 않기", "환상향에선 상식에 얽매이면 안 된대요.\n"
         "그래서 저도 용기 내서 말할게요. 당신이랑 있는 시간이 정말 즐거워요!", "사나에"),
        ("기적은 당신 옆에", "기적은 일으키는 거라고 늘 말했지만,\n당신을 만난 건 그냥 일어난 기적 같아요.\n"
         "앞으로도 잘 부탁드려요!", "코치야 사나에"),
    ],
    "remilia": [
        ("홍마관의 주인으로서", "인간에게 편지를 쓰는 건 처음이야. 영광으로 알렴.\n네 신사, 제법 마음에 들어.", "레밀리아 스칼렛"),
        ("운명의 실", "네 운명을 슬쩍 봤어. 꽤 재미있는 실이 얽혀 있더라.\n어떤 실인지는… 비밀이야.", "레밀리아"),
        ("달밤의 산책", "보름달 뜬 밤, 신사 지붕 위에서 달구경을 했어.\n네가 같이 있었으면 더 좋았을 텐데.\n"
         "…흥, 그냥 해 본 말이야.", "레밀리아"),
        ("동생에 대해", "동생이 요즘 웃는 일이 많아졌어. 네 덕분이라는 걸 알아.\n언니로서 고맙다고 해 둘게. 특별히.", "레밀리아"),
        ("초대장", "다음 보름달 밤, 홍마관의 다과회에 초대할게.\n사쿠야가 최고의 홍차를 준비할 거야.\n"
         "거절은 운명이 허락하지 않아.", "홍마관의 주인 레밀리아 스칼렛"),
    ],
    "flandre": [
        ("놀자!", "안녕! 나 플랑이야.\n너는 부서지지 않는 장난감… 아니 친구지? 다음에 같이 놀자!", "플랑"),
        ("그림을 그렸어", "너랑 언니랑 나랑 셋이서 손잡고 있는 그림이야.\n언니 얼굴은 좀 찌그러졌는데 비밀이야!", "플랑"),
        ("조심할게", "나 힘 조절 연습하고 있어. 너랑 손잡을 때 꽉 잡으면 안 되니까!\n어제는 컵을 하나도 안 깼어!", "플랑"),
        ("지하실 밖", "예전엔 지하실에만 있었는데, 요즘은 밖이 더 좋아.\n신사에 오면 네가 있으니까!", "플랑"),
        ("약속 지켰어", "너는 부수지 않겠다고 약속했잖아. 그 약속, 계속 계속 지킬 거야.\n"
         "그러니까 너도 계속 같이 놀아 줘야 해!", "플랑드르 스칼렛"),
    ],
    "youmu": [
        ("백옥루에서", "처음 편지 드립니다. 백옥루의 정원사 콘파쿠 요우무입니다.\n"
         "신사 정원이 잘 손질되어 있어 감탄했습니다.", "요우무"),
        ("유유코 님이", "유유코 님께서 신사 간식이 맛있다고 또 가자고 하십니다.\n혹시 너무 많이 드시면 말려 주세요…", "요우무"),
        ("수행 일지", "오늘은 벚꽃잎을 떨어지기 전에 백 장 베는 수행을 했습니다.\n"
         "아흔아홉 장… 하나는 당신 생각을 하다 놓쳤습니다.", "요우무"),
        ("반령", "제 반령이 요즘 자꾸 당신 쪽으로 둥실둥실 갑니다.\n"
         "반령은 제 마음을 따라간다던데… 아, 아무것도 아닙니다!", "요우무"),
        ("함께 차를", "수행이 끝나면 함께 차를 마시자던 약속, 기억하시나요?\n"
         "오늘 수행을 마쳤습니다. 백옥루 벚꽃 아래에서 기다리겠습니다.", "콘파쿠 요우무"),
    ],
    "meiling": [
        ("문지기 메이링입니다", "홍마관 문지기 홍 메이링이에요!\n신사 문도 제가 지켜 드릴게요. 졸지 않고요! …아마도요.", "메이링"),
        ("태극권 아침 체조", "아침마다 태극권을 하면 기가 맑아져요.\n같이 해 볼래요? 졸음도 싹 달아나요!", "메이링"),
        ("또 혼났어요", "또 졸다가 사쿠야 씨에게 칼을 맞을 뻔했어요.\n그래도 당신이 쓰다듬어 줘서 금방 기운 났어요!", "메이링"),
        ("화단", "홍마관 문 앞 화단에 꽃을 심었어요. 하나는 당신 몫이에요.\n피면 보러 와 주세요!", "메이링"),
        ("지키고 싶은 것", "문지기는 소중한 걸 지키는 사람이래요.\n그래서 이제 신사도, 당신도 제가 지킬게요.\n"
         "이번엔 정말 안 졸 거예요!", "홍 메이링"),
    ],
}
TOTAL = sum(len(v) for v in LETTERS.values())


def _id(key: str, n: int) -> str:
    return f"{key}:{n}"


def got(s: GameState, key: str) -> list[int]:
    return sorted(s.letters.get(key, []))


def due(s: GameState, friends: list[str]) -> list[tuple[str, int]]:
    """하트만큼 와 있어야 하는데 아직 안 온 편지."""
    out = []
    for key in friends:
        if key not in LETTERS:
            continue
        have = set(s.letters.get(key, []))
        out += [(key, n) for n in range(1, min(aff.level(s, key), len(LETTERS[key])) + 1) if n not in have]
    return out


def deliver(s: GameState, friends: list[str]) -> list[tuple[str, int]]:
    new = due(s, friends)
    for key, n in new:
        s.letters.setdefault(key, []).append(n)
    return new


def unread(s: GameState) -> list[tuple[str, int]]:
    return [(k, n) for k in LETTERS for n in got(s, k) if _id(k, n) not in s.letters_read]


def count(s: GameState) -> int:
    return sum(len(v) for k, v in s.letters.items() if k in LETTERS)


def read(s: GameState, key: str, n: int) -> str:
    """편지를 읽음 표시. 다섯 번째 편지를 처음 읽으면 선물 (그 설명을 돌려줌)."""
    lid = _id(key, n)
    if lid in s.letters_read:
        return ""
    s.letters_read.append(lid)
    if n == len(LETTERS[key]):
        s.cloth += LAST_GIFT
        return f"편지와 함께 옷감 {LAST_GIFT}장이 들어 있었다"
    return ""


class LetterNote(DiaryCard):
    """새 편지 알림. 누르면 편지(여러 통이면 편지함)를 연다."""

    def __init__(self, new: list[tuple[str, int]], on_open: Callable[[], None]):
        if len(new) == 1:
            key, n = new[0]
            title, lines = "💌 편지가 왔어요", [f"{CHARACTERS[key].name}에게서 편지가 왔어요.",
                                               f"「{LETTERS[key][n - 1][0]}」"]
        else:
            names = sorted({short_name(k) for k, _ in new})
            title, lines = f"💌 편지가 {len(new)}통 와 있어요", [", ".join(names[:6]) + (" …" if len(names) > 6 else "")]
        super().__init__(title, lines, "눌러서 읽기")
        self.on_open = on_open

    def mousePressEvent(self, _e) -> None:
        QTimer.singleShot(0, self.on_open)
        self.close()


class LetterWindow(QWidget):
    """편지지 한 장. 누르면 닫힌다."""

    W = 380

    def __init__(self, key: str, n: int, gift: str = ""):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setCursor(Qt.PointingHandCursor)
        self.key, self.n, self.gift = key, n, gift
        self.title, self.body, self.sign = LETTERS[key][n - 1]
        self.f_title = QFont("Malgun Gothic", 12)
        self.f_title.setBold(True)
        self.f_body = QFont("Malgun Gothic", 10)
        self.f_sign = QFont("Malgun Gothic", 10)
        self.f_sign.setItalic(True)
        self.f_small = QFont("Malgun Gothic", 8)
        fm = QFontMetricsF(self.f_body)
        self.body_h = fm.boundingRect(QRectF(0, 0, self.W - 64, 999), Qt.TextWordWrap, self.body).height()
        self.setFixedSize(self.W, int(118 + self.body_h + 56 + (22 if gift else 0)))

    def show_above(self, cx: float, bottom: float) -> None:
        self.move(round(cx - self.width() / 2), round(bottom - self.height() - 8))
        self.show()
        self.raise_()

    def mousePressEvent(self, _e) -> None:
        self.close()

    def paintEvent(self, _e) -> None:
        from .panel import portrait
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        path = QPainterPath()
        path.addRoundedRect(r, 6, 6)
        p.setPen(QPen(QColor(170, 140, 110, 160), 1.2))
        p.setBrush(QColor("#FFF9EC"))
        p.drawPath(path)
        p.setPen(QPen(QColor(200, 170, 140, 70), 1))                 # 편지지 줄
        for y in range(70, int(r.bottom()) - 20, 22):
            p.drawLine(QPointF(24, y), QPointF(self.W - 24, y))
        p.setPen(Qt.NoPen)                                           # 붉은 봉인
        p.setBrush(QColor(200, 16, 46, 210))
        p.drawEllipse(QPointF(self.W - 40, 36), 15, 15)
        p.setPen(QColor("#FFFFFF"))
        p.setFont(self.f_small)
        p.drawText(QRectF(self.W - 55, 21, 30, 30), Qt.AlignCenter, "♥")
        p.setPen(QColor("#8C7479"))
        p.drawText(QRectF(24, 14, self.W - 90, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{CHARACTERS[self.key].name}의 편지 · {self.n} / {len(LETTERS[self.key])}")
        p.setFont(self.f_title)
        p.setPen(QColor("#9C2A3C"))
        p.drawText(QRectF(24, 32, self.W - 90, 26), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        p.setFont(self.f_body)
        p.setPen(QColor("#3A2A2E"))
        p.drawText(QRectF(32, 74, self.W - 64, self.body_h + 4), Qt.TextWordWrap, self.body)
        y = 74 + self.body_h + 18
        p.drawPixmap(QPointF(22, y - 6), portrait(self.key, 44, False))
        p.setFont(self.f_sign)
        p.setPen(QColor("#6A4A3A"))
        p.drawText(QRectF(24, y, self.W - 48, 24), Qt.AlignRight | Qt.AlignVCenter, f"— {self.sign}")
        if self.gift:
            p.setFont(self.f_small)
            p.setPen(QColor("#B8860B"))
            p.drawText(QRectF(24, y + 30, self.W - 48, 18), Qt.AlignRight | Qt.AlignVCenter, f"🎁 {self.gift}")
        p.end()


class LetterBook(QWidget):
    """편지함: 친구마다 받은 편지 (안 읽은 것은 ●). 누르면 그 편지를 연다."""

    def __init__(self, s: GameState, friends: list[str], on_read: Callable[[str, int], None]):
        super().__init__(None, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        from .panel import STYLE, portrait
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("panel")
        self.setStyleSheet(STYLE)
        self.setFixedWidth(470)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 16)
        v.setSpacing(6)
        v.addWidget(QLabel(f"💌  편지함   {count(s)} / {TOTAL}", objectName="title"))
        tip = QLabel("친구와 하트가 하나 늘 때마다 편지가 한 통 와요. 다섯 번째 편지엔 작은 선물이 들어 있어요.",
                     objectName="goal")
        tip.setWordWrap(True)
        v.addWidget(tip)
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        self.buttons: dict[tuple[str, int], QPushButton] = {}
        row = 0
        for key in LETTERS:
            if key not in friends:
                continue
            face = QLabel()
            face.setPixmap(portrait(key, 30, False))
            grid.addWidget(face, row, 0)
            grid.addWidget(QLabel(short_name(key), objectName="name"), row, 1)
            have = got(s, key)
            for n in range(1, len(LETTERS[key]) + 1):
                new = n in have and _id(key, n) not in s.letters_read
                b = QPushButton(("● " if new else "") + str(n) if n in have else "?",
                                objectName="small" if n in have else "ghost")
                b.setEnabled(n in have)
                b.setToolTip(LETTERS[key][n - 1][0] if n in have else f"하트 {n}개가 되면 와요")
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, key=key, n=n: (self.close(), on_read(key, n)))
                grid.addWidget(b, row, 1 + n)
                self.buttons[(key, n)] = b
            row += 1
        v.addLayout(grid)

    def show_near(self, pos) -> None:
        from PySide6.QtGui import QGuiApplication
        self.adjustSize()
        sc = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        area = sc.availableGeometry()
        x = min(max(pos.x() - self.width() // 2, area.left() + 8), area.right() - self.width() - 8)
        y = min(max(pos.y() - self.height() - 10, area.top() + 8), area.bottom() - self.height() - 8)
        self.move(x, y)
        self.show()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        p.setPen(QPen(QColor(200, 16, 46, 120), 1.2))
        p.setBrush(QColor(255, 247, 248, 248))
        p.drawPath(path)
        p.end()
