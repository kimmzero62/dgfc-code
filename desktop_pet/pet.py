"""바탕화면 펫 — 움직이는 GIF 한 장으로 화면 위를 돌아다니는 펫을 띄운다.

실행:  python pet.py                  (assets 폴더의 GIF마다 펫 하나씩)
       python pet.py a.gif b.gif      (지정한 GIF만)

조작:  클릭 = 반응 / 드래그 = 옮기기(놓으면 떨어짐) / 오른쪽 클릭 = 메뉴
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageSequence
from PySide6.QtCore import QPoint, QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import (QAction, QActionGroup, QColor, QFont, QIcon, QImage,
                           QPainter, QPainterPath, QPen, QPixmap, QTransform)
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
DEFAULT_GIF = ASSETS / "pet.gif"  # 예전 방식 호환

# ── 설정 ────────────────────────────────────────────────
SCALES = {"작게": 0.30, "보통": 0.42, "크게": 0.60}
DEFAULT_SCALE = "보통"
WALK_SPEED = 70          # 초당 이동 픽셀 (크기 '보통' 기준)
SLEEP_AFTER_SEC = 120    # 이 시간 동안 건드리지 않으면 잠듦
REMIND_EVERY_MIN = 50    # 쉬는 시간 알림 간격(분). 0이면 끔
TICK_MS = 33
REMOVE_HEARTS = True     # 그림에 떠 있는 분홍 하트 지우기

# 9프레임 GIF의 프레임별 동작 (우사기 GIF 기준)
# 파일 이름이 아래 중 하나일 때만 동작별로 나눠 쓰고, 나머지 GIF는 통째로 반복 재생한다.
POSED_NAMES = {"pet", "usagi", "우사기"}
POSE = {"idle": 0, "wave": 1, "jump": 2, "love": 3, "wiggle": 4,
        "surprise": 5, "back": 6, "sleep": 7, "shy": 8}

CLICK_LINES = {
    # 말은 안 하고 소리만 냄
    "love": ["우나", "우나…"],
    "shy": ["우나…", "뿌릣"],
    "wave": ["이야!", "우나!"],
    "jump": ["이야!!", "이야하!"],
}
REMIND_LINES = ["뿌릣!", "우나!", "이야!"]  # 쉬는 시간 신호 (소리만)


# ── 프레임 불러오기 ─────────────────────────────────────
def _drop_thin_rows(img: Image.Image, max_h: int = 3) -> Image.Image:
    """그림 본체와 떨어진 얇은 가로줄(잘린 테두리 같은 잡티)을 지운다."""
    alpha = img.getchannel("A")
    w, h = img.size
    filled = [alpha.crop((0, y, w, y + 1)).getbbox() is not None for y in range(h)]
    runs, start = [], None
    for y, f in enumerate(filled + [False]):
        if f and start is None:
            start = y
        elif not f and start is not None:
            runs.append((start, y))
            start = None
    if len(runs) <= 1:
        return img
    out = img.copy()
    for a, b in runs:
        if b - a <= max_h:
            out.paste((0, 0, 0, 0), (0, a, w, b))
    return out


def _is_pink(c) -> bool:
    r, g, b, a = c
    return a > 0 and r > 200 and g < 170 and b < 200


def _drop_hearts(img: Image.Image, max_px: int = 3000) -> Image.Image:
    """몸통과 떨어져 떠 있는 분홍 덩어리(하트)를 지운다.
    볼터치·귀 안쪽처럼 몸통에 붙은 분홍은 그대로 둔다."""
    w, h = img.size
    out = img.copy()
    px = out.load()
    state = bytearray(w * h)  # 0=미방문 1=방문 2=몸통(큰 덩어리)
    for sy in range(h):
        for sx in range(w):
            if state[sy * w + sx] or not _is_pink(px[sx, sy]):
                continue
            stack, region, big = [(sx, sy)], [], False
            state[sy * w + sx] = 1
            while stack:
                x, y = stack.pop()
                region.append((x, y))
                if len(region) > max_px:
                    big = True
                    break
                for nx in (x - 1, x, x + 1):
                    for ny in (y - 1, y, y + 1):
                        if not (0 <= nx < w and 0 <= ny < h) or px[nx, ny][3] == 0:
                            continue
                        s = state[ny * w + nx]
                        if s == 2:
                            big = True
                        elif s == 0:
                            state[ny * w + nx] = 1
                            stack.append((nx, ny))
                if big:
                    break
            if big:
                for x, y in region + stack:
                    state[y * w + x] = 2
                continue
            pink = sum(1 for p in region if _is_pink(px[p]))
            if pink >= 0.8 * len(region):
                for p in region:
                    px[p] = (0, 0, 0, 0)
    return out


def load_frames(path: Path) -> tuple[list[Image.Image], list[int]]:
    im = Image.open(path)
    frames, durations = [], []
    for fr in ImageSequence.Iterator(im):
        img = _drop_thin_rows(fr.convert("RGBA"))
        if REMOVE_HEARTS:
            img = _drop_hearts(img)
        frames.append(img)
        durations.append(max(60, fr.info.get("duration", 200)))
    return frames, durations


def to_pixmap(img: Image.Image) -> QPixmap:
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, img.width * 4, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


# ── 펫 창 ───────────────────────────────────────────────
class Pet(QWidget):
    TOP_SPACE = 80  # 말풍선·점프용 위쪽 여백
    SIDE = 35       # 말풍선이 잘리지 않게 양옆 여백

    def __init__(self, gif: Path, index: int = 0):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("바탕화면 펫")

        self.raw, self.durations = load_frames(gif)
        self.name = gif.stem
        self.index = index
        self.posed = (len(self.raw) == len(POSE)
                      and gif.stem.lower() in POSED_NAMES)
        # 발바닥 아래 빈 공간 → 바닥에 딱 붙이기 위해
        self.foot_gap_raw = self.raw[0].height - max(
            (f.getbbox() or (0, 0, 0, f.height))[3] for f in self.raw)

        self.settings = QSettings("desktop_pet", "pet")
        self.settings.beginGroup(self.name)  # 펫마다 크기·설정 따로 저장
        self.scale_name = self.settings.value("scale", DEFAULT_SCALE)
        if self.scale_name not in SCALES:
            self.scale_name = DEFAULT_SCALE
        self.walk_on = self.settings.value("walk", True, type=bool)
        self.remind_on = self.settings.value("remind", REMIND_EVERY_MIN > 0, type=bool)

        self.state = "idle"
        self.state_t = 0.0
        self.state_dur = 3.0
        self.pose = "idle"
        self.dir = 1
        self.offset_y = 0.0
        self.vy = 0.0
        self.anim_t = 0.0
        self.calm_t = 0.0          # 마지막으로 건드린 뒤 지난 시간
        self.remind_t = 0.0
        self.bubble = ""
        self.bubble_t = 0.0
        self.dragging = False
        self.press_global: QPoint | None = None
        self.drag_off = QPoint()

        self._build_pixmaps()
        self._build_menu()
        self._place_initial()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(TICK_MS)

    # ── 크기 / 위치 ──
    @property
    def scale(self) -> float:
        return SCALES[self.scale_name]

    def _build_pixmaps(self):
        s = self.scale
        w0, h0 = self.raw[0].size
        size = (max(1, round(w0 * s)), max(1, round(h0 * s)))
        self.pix = [to_pixmap(f.resize(size, Image.LANCZOS)) for f in self.raw]
        flip = QTransform().scale(-1, 1)
        self.pix_flip = [p.transformed(flip) for p in self.pix]
        self.foot_gap = round(self.foot_gap_raw * s)
        self.setFixedSize(size[0] + 2 * self.SIDE, size[1] + self.TOP_SPACE)

    def set_scale(self, name: str):
        bottom = self.y() + self.height()
        cx = self.x() + self.width() // 2
        self.scale_name = name
        self.settings.setValue("scale", name)
        self._build_pixmaps()
        self.move(cx - self.width() // 2, bottom - self.height())
        self.fx = float(self.x())
        self.update()

    def screen_area(self):
        center = self.geometry().center()
        scr = QApplication.screenAt(center) or QApplication.primaryScreen()
        return scr.availableGeometry()

    def ground_y(self) -> int:
        return self.screen_area().bottom() + 1 - self.height() + self.foot_gap

    def _place_initial(self):
        area = QApplication.primaryScreen().availableGeometry()
        frac = (0.75 - 0.22 * self.index) % 0.9 + 0.05  # 펫끼리 겹치지 않게
        x = area.left() + int(area.width() * frac) - self.width() // 2
        self.move(x, area.bottom() + 1 - self.height() + self.foot_gap)
        self.fx = float(self.x())

    # ── 상태 전환 ──
    def set_state(self, state: str, pose: str = "idle", dur: float = 2.0, say: str = ""):
        self.state, self.pose, self.state_dur = state, pose, dur
        self.state_t = 0.0
        self.offset_y = 0.0
        if say:
            self.say(say)

    def say(self, text: str, sec: float = 2.5):
        self.bubble, self.bubble_t = text, sec

    def choose_next(self):
        r = random.random()
        if self.walk_on and r < 0.55:
            self.dir = random.choice((-1, 1))
            self.set_state("walk", dur=random.uniform(3, 8))
        elif r < 0.68:
            self.set_state("pose", "wiggle", random.uniform(1.5, 3))
        elif r < 0.78:
            self.set_state("pose", "back", random.uniform(1.5, 3))
        elif r < 0.85:
            self.set_state("pose", "wave", 1.5)
        else:
            self.set_state("idle", dur=random.uniform(3, 7))

    # ── 매 틱 ──
    def tick(self):
        dt = TICK_MS / 1000
        self.state_t += dt
        self.anim_t += dt
        self.calm_t += dt
        if self.bubble_t > 0:
            self.bubble_t -= dt
            if self.bubble_t <= 0:
                self.bubble = ""

        if self.remind_on and REMIND_EVERY_MIN > 0:
            self.remind_t += dt
            if self.remind_t >= REMIND_EVERY_MIN * 60 and not self.dragging:
                self.remind_t = 0
                self.calm_t = 0
                self.set_state("pose", "wave", 4)
                self.say(random.choice(REMIND_LINES), 6)

        if not self.dragging:
            getattr(self, "_tick_" + self.state)(dt)
        self.update()

    def _tick_idle(self, dt):
        if self.calm_t > SLEEP_AFTER_SEC:
            self.set_state("sleep", "sleep", 1e9)
        elif self.state_t > self.state_dur:
            self.choose_next()

    def _tick_pose(self, dt):
        if self.state_t > self.state_dur:
            self.set_state("idle", dur=random.uniform(2, 5))

    def _tick_sleep(self, dt):
        pass

    def _tick_walk(self, dt):
        area = self.screen_area()
        self.fx += self.dir * WALK_SPEED * (self.scale / SCALES["보통"]) * dt
        lo, hi = area.left(), area.right() + 1 - self.width()
        if self.fx < lo or self.fx > hi:
            self.fx = min(max(self.fx, lo), hi)
            self.dir *= -1
        self.move(int(self.fx), self.ground_y())
        self.pose = "idle" if int(self.state_t * 4) % 2 == 0 else "wiggle"
        self.offset_y = -abs(math.sin(self.state_t * math.pi * 3)) * 6 * self.scale / 0.42
        if self.state_t > self.state_dur:
            self.set_state("idle", dur=random.uniform(2, 5))

    def _tick_jump(self, dt):
        p = min(1.0, self.state_t / self.state_dur)
        self.offset_y = -4 * 45 * p * (1 - p)
        if p >= 1:
            self.set_state("idle", dur=random.uniform(2, 4))

    def _tick_fall(self, dt):
        self.vy += 2200 * dt
        y = self.y() + self.vy * dt
        g = self.ground_y()
        if y >= g:
            self.move(self.x(), g)
            self.vy = 0
            self.set_state("jump", "jump", 0.5)
        else:
            self.move(self.x(), int(y))

    # ── 그리기 ──
    def current_frame(self) -> int:
        if self.posed:
            return POSE[self.pose]
        total = sum(self.durations)
        t = (self.anim_t * 1000) % total
        for i, d in enumerate(self.durations):
            if t < d:
                return i
            t -= d
        return 0

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        i = self.current_frame()
        # 원본은 꼬리가 오른쪽 → 오른쪽으로 걸을 때 좌우 반전
        mirror = self.state == "walk" and self.dir > 0
        pm = (self.pix_flip if mirror else self.pix)[i]
        p.drawPixmap(self.SIDE, self.height() - pm.height() + int(self.offset_y), pm)
        if self.bubble:
            self._draw_bubble(p)

    def _draw_bubble(self, p: QPainter):
        font = QFont()
        font.setFamilies(["Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans CJK KR"])
        font.setPointSize(10)
        font.setBold(True)
        p.setFont(font)
        fm = p.fontMetrics()
        maxw = self.width() - 16
        flags = Qt.AlignCenter | Qt.TextWordWrap
        tr = fm.boundingRect(0, 0, maxw - 20, 200, flags, self.bubble)
        bw, bh = tr.width() + 20, tr.height() + 12
        x = (self.width() - bw) / 2
        y = max(2, self.TOP_SPACE - bh - 14)
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y, bw, bh), 10, 10)
        tail = QPainterPath()
        cx = self.width() / 2
        tail.moveTo(cx - 6, y + bh - 1)
        tail.lineTo(cx, y + bh + 8)
        tail.lineTo(cx + 6, y + bh - 1)
        path = path.united(tail)
        p.setPen(QPen(QColor("#3a2a20"), 2))
        p.setBrush(QColor("#fffaf2"))
        p.drawPath(path)
        p.setPen(QColor("#3a2a20"))
        p.drawText(QRectF(x, y, bw, bh), flags, self.bubble)

    # ── 마우스 ──
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.press_global = e.globalPosition().toPoint()
            self.drag_off = self.press_global - self.pos()

    def mouseMoveEvent(self, e):
        if self.press_global is None or not (e.buttons() & Qt.LeftButton):
            return
        g = e.globalPosition().toPoint()
        if not self.dragging and (g - self.press_global).manhattanLength() > 5:
            self.dragging = True
            self.calm_t = 0
            self.state, self.pose, self.offset_y = "drag", "surprise", 0
            self.say("야다!!", 1.5)
        if self.dragging:
            self.move(g - self.drag_off)
            self.fx = float(self.x())

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self.press_global is None:
            return
        self.press_global = None
        self.calm_t = 0
        if self.dragging:
            self.dragging = False
            self.vy = 0
            self.set_state("fall", "surprise", 1e9)
            return
        self.react()

    def react(self):
        if self.state == "sleep":
            self.set_state("pose", "surprise", 1.5, "하?")
            return
        kind = random.choice(list(CLICK_LINES))
        line = random.choice(CLICK_LINES[kind])
        if kind == "jump":
            self.set_state("jump", "jump", 0.6, line)
        else:
            self.set_state("pose", kind, 2.0, line)

    def contextMenuEvent(self, e):
        self.menu.exec(e.globalPos())

    # ── 메뉴 / 트레이 ──
    def _build_menu(self):
        m = QMenu()
        size_menu = m.addMenu("크기")
        group = QActionGroup(size_menu)
        for name in SCALES:
            a = QAction(name, size_menu, checkable=True, checked=(name == self.scale_name))
            a.triggered.connect(lambda _=False, n=name: self.set_scale(n))
            group.addAction(a)
            size_menu.addAction(a)

        walk = QAction("돌아다니기", m, checkable=True, checked=self.walk_on)
        walk.toggled.connect(self._set_walk)
        m.addAction(walk)

        remind = QAction(f"쉬는 시간 알림 ({REMIND_EVERY_MIN}분마다)", m,
                         checkable=True, checked=self.remind_on)
        remind.toggled.connect(self._set_remind)
        remind.setEnabled(REMIND_EVERY_MIN > 0)
        m.addAction(remind)

        m.addSeparator()
        m.addAction("재우기", lambda: self.set_state("sleep", "sleep", 1e9))
        m.addAction("깨우기", lambda: (setattr(self, "calm_t", 0),
                                      self.set_state("pose", "wave", 1.5, "하?")))
        m.addAction("화면 가운데로", self._recall)
        m.addSeparator()
        m.addAction("종료", QApplication.quit)
        self.menu = m

        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(QIcon(self.pix[0]), self)
            self.tray.setToolTip(f"바탕화면 펫 - {self.name}")
            self.tray.setContextMenu(m)
            self.tray.activated.connect(
                lambda r: self._recall() if r == QSystemTrayIcon.Trigger else None)
            self.tray.show()

    def _set_walk(self, on: bool):
        self.walk_on = on
        self.settings.setValue("walk", on)
        if not on and self.state == "walk":
            self.set_state("idle")

    def _set_remind(self, on: bool):
        self.remind_on = on
        self.remind_t = 0
        self.settings.setValue("remind", on)

    def _recall(self):
        area = QApplication.primaryScreen().availableGeometry()
        self.move(area.center().x() - self.width() // 2, self.y())
        self.move(self.x(), self.ground_y())
        self.fx = float(self.x())
        self.calm_t = 0
        self.set_state("pose", "wave", 1.5, "이야!")
        self.raise_()


def main():
    if len(sys.argv) > 1:
        gifs = [Path(a) for a in sys.argv[1:]]
    else:
        gifs = sorted(ASSETS.glob("*.gif"))  # assets 폴더의 GIF마다 펫 하나씩
    missing = [g for g in gifs if not g.exists()]
    if not gifs or missing:
        sys.exit(f"그림 파일이 없습니다: {missing or ASSETS}\n"
                 f"움직이는 GIF를 {ASSETS} 폴더에 넣거나, 경로를 인자로 주세요.")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    pets = [Pet(g, i) for i, g in enumerate(gifs)]
    for p in pets:
        p.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
