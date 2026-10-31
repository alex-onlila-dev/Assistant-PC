"""Bulle vocale à l'écran, façon assistant vocal : elle apparaît quand on parle à Jarvis.

- J'écoute    : orbe bleu qui respire avec ta voix
- Je réfléchis: cerveau qui pulse, entouré de points qui tournent
- Je parle    : barres qui suivent la voix de Jarvis
- Confirmation: orbe ambré, l'action à valider est affichée

Toucher la bulle termine la conversation. Icône dans la barre des menus : « Parler à Jarvis », « Quitter ».
"""
import math
import sys
import threading
import time

from PySide6.QtCore import QEasingCurve, QObject, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import (QApplication, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QMenu, QStyle,
                               QSystemTrayIcon, QVBoxLayout, QWidget)

from jarvis.core.context import ctx
from jarvis.voice.session import SessionUI, VoiceSession

STATUS = {"listening": "J'écoute…", "thinking": "Je réfléchis…", "speaking": "", "confirm": "Dis « oui » ou « non »"}
ACCENT = {"listening": "#5ac8fa", "thinking": "#bf8cff", "speaking": "#ff7eb6", "confirm": "#ffb340", "idle": "#8e8e93"}


class Bridge(QObject):
    """Fait passer les événements du fil vocal vers le fil de l'interface (signaux Qt = sans risque)."""
    show = Signal()
    hide = Signal()
    state = Signal(str, str)
    level = Signal(float)
    user_text = Signal(str)
    answer_reset = Signal()
    answer_delta = Signal(str)
    ready = Signal(str)


class QtSessionUI(SessionUI):
    def __init__(self, bridge: Bridge):
        self.b = bridge

    def ready(self, how): self.b.ready.emit(how)
    def show(self): self.b.show.emit()
    def hide(self): self.b.hide.emit()
    def state(self, name, detail=""): self.b.state.emit(name, detail)
    def level(self, value): self.b.level.emit(float(value))
    def user_text(self, text): self.b.user_text.emit(text)
    def answer_reset(self): self.b.answer_reset.emit()
    def answer_delta(self, piece): self.b.answer_delta.emit(piece)


# ---------------------------------------------------------------------------------------------- orbe
class Orb(QWidget):
    """L'animation : redessinée 60 fois par seconde, le volume est lissé pour un mouvement fluide."""

    def __init__(self, size: int = 84):
        super().__init__()
        self.setFixedSize(size, size)
        self.mode = "idle"
        self.target = 0.0
        self.level = 0.0
        self.t0 = time.monotonic()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def set_mode(self, mode: str) -> None:
        self.mode = mode

    def set_level(self, value: float) -> None:
        self.target = max(0.0, min(1.0, value))

    def _tick(self) -> None:
        # monte vite, redescend doucement (comme un vumètre)
        k = 0.45 if self.target > self.level else 0.12
        self.level += (self.target - self.level) * k
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = time.monotonic() - self.t0
        c = QPointF(self.width() / 2, self.height() / 2)
        r = self.width() * 0.30
        getattr(self, f"_paint_{self.mode}", self._paint_idle)(p, c, r, t)
        p.end()

    @staticmethod
    def _glow(p: QPainter, c: QPointF, radius: float, inner: str, outer: str, alpha: int = 255) -> None:
        g = QRadialGradient(c, radius)
        ci, co = QColor(inner), QColor(outer)
        ci.setAlpha(alpha)
        co.setAlpha(0)
        g.setColorAt(0.0, ci)
        g.setColorAt(0.55, QColor(ci.red(), ci.green(), ci.blue(), int(alpha * 0.55)))
        g.setColorAt(1.0, co)
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(c, radius, radius)

    def _paint_idle(self, p, c, r, t):
        self._glow(p, c, r, "#8e8e93", "#000000", 120)

    def _paint_listening(self, p, c, r, t):
        lv = self.level
        for i in range(3):                       # ondes qui s'éloignent
            phase = (t * 0.9 + i / 3) % 1.0
            rr = r * (1.0 + phase * (0.55 + lv * 0.6))
            col = QColor("#5ac8fa")
            col.setAlpha(int((1 - phase) * (60 + 140 * lv)))
            p.setPen(QPen(col, 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(c, rr, rr)
        breathe = 1 + 0.04 * math.sin(t * 3)
        self._glow(p, c, r * (0.85 + lv * 0.45) * breathe * 1.25, "#7fe0ff", "#0a84ff")
        self._glow(p, c, r * 0.55, "#ffffff", "#5ac8fa", 200)

    def _paint_thinking(self, p, c, r, t):
        pulse = 0.5 + 0.5 * math.sin(t * 4)
        self._glow(p, c, r * (1.25 + 0.15 * pulse), "#bf8cff", "#5e2bff", int(140 + 80 * pulse))
        for i in range(3):                       # points qui tournent autour du cerveau
            a = t * 2.6 + i * 2 * math.pi / 3
            d = r * 1.28
            pt = QPointF(c.x() + d * math.cos(a), c.y() + d * math.sin(a))
            col = QColor("#e6d4ff")
            col.setAlpha(int(140 + 115 * math.sin(t * 5 + i) ** 2))
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawEllipse(pt, 3.2, 3.2)
        font = QFont()
        font.setPixelSize(int(r * 1.25))
        p.setFont(font)
        p.setPen(QColor("white"))
        s = r * 1.6
        p.drawText(QRectF(c.x() - s / 2, c.y() - s / 2 + 1, s, s), Qt.AlignCenter, "🧠")

    def _paint_speaking(self, p, c, r, t):
        lv = self.level
        self._glow(p, c, r * (1.25 + lv * 0.35), "#ff7eb6", "#7d2bff", int(150 + 100 * lv))
        bars, w = 5, r * 0.20
        for i in range(bars):                    # barres qui suivent la voix
            wobble = 0.55 + 0.45 * math.sin(t * 9 + i * 1.3)
            h = r * (0.25 + 1.25 * lv * wobble * (1 - abs(i - 2) * 0.18))
            x = c.x() + (i - (bars - 1) / 2) * w * 1.7 - w / 2
            path = QPainterPath()
            path.addRoundedRect(QRectF(x, c.y() - h / 2, w, h), w / 2, w / 2)
            p.fillPath(path, QColor(255, 255, 255, 235))

    def _paint_confirm(self, p, c, r, t):
        pulse = 0.5 + 0.5 * math.sin(t * 3)
        self._glow(p, c, r * (1.2 + 0.12 * pulse), "#ffd60a", "#ff9f0a", 230)
        font = QFont()
        font.setPixelSize(int(r * 1.1))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#3a2600"))
        s = r * 1.6
        p.drawText(QRectF(c.x() - s / 2, c.y() - s / 2, s, s), Qt.AlignCenter, "?")


# ---------------------------------------------------------------------------------------------- bulle
class Bubble(QWidget):
    WIDTH = 500

    def __init__(self, on_click):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus)
        self.on_click = on_click
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedWidth(self.WIDTH)
        self.answer = ""

        self.card = QWidget(self)
        self.card.setObjectName("card")
        self.card.setStyleSheet("""
            #card { background: rgba(22, 22, 28, 232); border: 1px solid rgba(255,255,255,30); border-radius: 26px; }
            QLabel { background: transparent; }
        """)
        shadow = QGraphicsDropShadowEffect(blurRadius=40, xOffset=0, yOffset=8)
        shadow.setColor(QColor(0, 0, 0, 150))
        self.card.setGraphicsEffect(shadow)

        self.orb = Orb()
        self.status = QLabel()
        self.status.setStyleSheet("font-size: 12px; font-weight: 600; letter-spacing: 0.3px;")
        self.you = QLabel()
        self.you.setWordWrap(True)
        self.you.setStyleSheet("color: rgba(235,235,245,150); font-size: 13px;")
        self.reply = QLabel()
        self.reply.setWordWrap(True)
        self.reply.setStyleSheet("color: white; font-size: 16px; font-weight: 500;")

        text = QVBoxLayout()
        text.setSpacing(4)
        text.addWidget(self.status)
        text.addWidget(self.you)
        text.addWidget(self.reply)
        text.addStretch()
        row = QHBoxLayout(self.card)
        row.setContentsMargins(16, 14, 22, 14)
        row.setSpacing(14)
        row.addWidget(self.orb, 0, Qt.AlignTop)
        row.addLayout(text, 1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 12, 20, 28)   # place pour l'ombre
        outer.addWidget(self.card)

        self.fade = QPropertyAnimation(self, b"windowOpacity", self)
        self.fade.setDuration(180)
        self.fade.setEasingCurve(QEasingCurve.OutCubic)
        self.fade.finished.connect(lambda: self.windowOpacity() == 0 and super(Bubble, self).hide())
        self.set_state("idle")

    # --- contenu
    def set_state(self, name: str, detail: str = "") -> None:
        self.orb.set_mode(name)
        accent = ACCENT.get(name, "#8e8e93")
        label = detail if detail and detail != "…" and name != "confirm" else STATUS.get(name, "")
        self.status.setText(label)
        self.status.setStyleSheet(f"color: {accent}; font-size: 12px; font-weight: 600;")
        self.status.setVisible(bool(label))
        if name == "confirm" and detail:
            self.reply.setText(detail)
        self._relayout()

    def set_user(self, text: str) -> None:
        self.you.setText(f"« {text} »" if text else "")
        self.you.setVisible(bool(text))
        self._relayout()

    def reset_answer(self) -> None:
        self.answer = ""
        self.reply.setText("")
        self._relayout()

    def add_answer(self, piece: str) -> None:
        self.answer += piece
        shown = self.answer.strip()
        if len(shown) > 320:                    # on garde la fin visible, comme des sous-titres
            shown = "…" + shown[-320:].split(" ", 1)[-1]
        self.reply.setText(shown)
        self._relayout()

    # --- apparition
    def _relayout(self) -> None:
        self.reply.setVisible(bool(self.reply.text()))
        self.adjustSize()
        self._place()

    def _place(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.bottom() - self.height() - 24)

    def appear(self) -> None:
        self._relayout()
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            super().show()
            self.raise_()
        self.fade.stop()
        self.fade.setStartValue(self.windowOpacity())
        self.fade.setEndValue(1.0)
        self.fade.start()

    def disappear(self) -> None:
        if not self.isVisible():
            return
        self.fade.stop()
        self.fade.setStartValue(self.windowOpacity())
        self.fade.setEndValue(0.0)
        self.fade.start()

    def mousePressEvent(self, _):
        self.on_click()


# ---------------------------------------------------------------------------------------------- lancement
def _hide_dock_icon() -> None:
    """macOS : Jarvis vit dans la barre des menus, sans icône dans le Dock."""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        pass


def run_overlay(cfg: dict) -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    _hide_dock_icon()

    bridge = Bridge()
    print("Chargement de la voix…")
    session = VoiceSession(cfg, QtSessionUI(bridge))
    if not ctx.llm.ensure_running():
        print("⚠️  Ollama ne répond pas. Lance « ollama serve » puis relance Jarvis.")
        return 1

    def end_by_click():
        bubble.disappear()
        session.end_conversation()

    bubble = Bubble(on_click=end_by_click)
    bridge.show.connect(bubble.appear)
    bridge.hide.connect(bubble.disappear)
    bridge.state.connect(bubble.set_state)
    bridge.level.connect(bubble.orb.set_level)
    bridge.user_text.connect(bubble.set_user)
    bridge.answer_reset.connect(bubble.reset_answer)
    bridge.answer_delta.connect(bubble.add_answer)

    tray = QSystemTrayIcon(app.style().standardIcon(QStyle.SP_MediaVolume), app)
    tray.setToolTip("Jarvis")
    menu = QMenu()
    talk = QAction("Parler à Jarvis", menu)
    talk.triggered.connect(session.wake_now)
    menu.addAction(talk)
    menu.addSeparator()
    quit_action = QAction("Quitter Jarvis", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    tray.show()

    def ready(how: str):
        print(f"Jarvis est prêt. Pour me parler, {how} (ou menu Jarvis > Parler à Jarvis).")
        tray.showMessage("Jarvis est prêt", f"Pour me parler, {how}.", QSystemTrayIcon.Information, 3000)
    bridge.ready.connect(ready)

    worker = threading.Thread(target=session.run, daemon=True)
    worker.start()
    code = app.exec()
    session.shutdown()
    worker.join(timeout=2)
    return code
