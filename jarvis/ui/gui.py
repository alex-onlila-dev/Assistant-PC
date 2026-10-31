"""Interface graphique : icône dans la barre système + fenêtre de discussion (PySide6)."""
import html
import sys
import threading

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
                               QPushButton, QStyle, QSystemTrayIcon, QTextBrowser, QVBoxLayout, QWidget)

from jarvis.bootstrap import create_agent
from jarvis.core.confirmation import Confirmer
from jarvis.core.context import ctx


class Bridge(QObject):
    """Fait passer les événements du fil de l'agent vers le fil de l'interface."""
    confirm_requested = Signal(str)
    event = Signal(str, object)


class QtConfirmer(Confirmer):
    def __init__(self, bridge: Bridge):
        self.bridge = bridge
        self._done = threading.Event()
        self._result = False

    def ask(self, action: str) -> bool:      # appelé depuis le fil de l'agent
        self._done.clear()
        self.bridge.confirm_requested.emit(action)
        self._done.wait()
        return self._result

    def resolve(self, ok: bool) -> None:     # appelé depuis l'interface
        self._result = ok
        self._done.set()


class AgentWorker(QThread):
    finished_with = Signal(str)

    def __init__(self, agent, text: str):
        super().__init__()
        self.agent, self.text = agent, text

    def run(self):
        try:
            self.finished_with.emit(self.agent.run(self.text))
        except Exception as e:
            self.finished_with.emit(f"Erreur : {e}")


class MainWindow(QWidget):
    def __init__(self, agent, confirmer: QtConfirmer, bridge: Bridge):
        super().__init__()
        self.agent, self.confirmer = agent, confirmer
        self.worker: AgentWorker | None = None
        self.setWindowTitle("Jarvis")
        self.resize(560, 680)

        self.log = QTextBrowser()
        self.log.setOpenExternalLinks(True)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Demande quelque chose à Jarvis…")
        self.input.returnPressed.connect(self.send)
        self.send_btn = QPushButton("Envoyer")
        self.send_btn.clicked.connect(self.send)
        reset_btn = QPushButton("Nouvelle conversation")
        reset_btn.clicked.connect(self.reset)
        self.status = QLabel(f"{ctx.os.name} · cerveau : {ctx.llm.model}")

        row = QHBoxLayout()
        row.addWidget(self.input)
        row.addWidget(self.send_btn)
        layout = QVBoxLayout(self)
        layout.addWidget(self.log)
        layout.addLayout(row)
        bottom = QHBoxLayout()
        bottom.addWidget(self.status)
        bottom.addStretch()
        bottom.addWidget(reset_btn)
        layout.addLayout(bottom)

        bridge.confirm_requested.connect(self.on_confirm)
        bridge.event.connect(self.on_event)

        if not ctx.llm.ping():
            self.append("Système", "Ollama ne répond pas. Lance « ollama serve » puis redémarre Jarvis.", "#c0392b")

    def append(self, who: str, text: str, color: str = "#222") -> None:
        safe = html.escape(text).replace("\n", "<br>")
        self.log.append(f'<p><b style="color:{color}">{who}</b><br>{safe}</p>')

    def send(self) -> None:
        text = self.input.text().strip()
        if not text or (self.worker and self.worker.isRunning()):
            return
        self.input.clear()
        self.append("Toi", text, "#2c3e50")
        self.set_busy(True)
        self.worker = AgentWorker(self.agent, text)
        self.worker.finished_with.connect(self.on_answer)
        self.worker.start()

    def on_answer(self, answer: str) -> None:
        self.append("Jarvis", answer, "#1a5276")
        self.set_busy(False)

    def on_confirm(self, action: str) -> None:
        self.show()
        self.activateWindow()
        reply = QMessageBox.question(self, "Confirmation requise", f"{action}\n\nConfirmer ?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        self.confirmer.resolve(reply == QMessageBox.Yes)

    def on_event(self, kind: str, data: dict) -> None:
        if kind == "tool_start":
            self.log.append(f'<p style="color:#888">⚙️ {html.escape(data["tool"])}…</p>')
        elif kind == "cancelled":
            self.log.append('<p style="color:#888">✖ Action annulée.</p>')

    def set_busy(self, busy: bool) -> None:
        self.input.setEnabled(not busy)
        self.send_btn.setEnabled(not busy)
        self.status.setText("Jarvis réfléchit…" if busy else f"{ctx.os.name} · cerveau : {ctx.llm.model}")
        if not busy:
            self.input.setFocus()

    def reset(self) -> None:
        self.agent.reset()
        self.log.clear()

    def closeEvent(self, event):   # fermer = réduire dans la barre système
        event.ignore()
        self.hide()


def run_gui(cfg: dict) -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    bridge = Bridge()
    confirmer = QtConfirmer(bridge)
    agent = create_agent(cfg, confirmer)
    agent.on_event = lambda kind, data: bridge.event.emit(kind, data)

    window = MainWindow(agent, confirmer, bridge)

    tray = QSystemTrayIcon(app.style().standardIcon(QStyle.SP_ComputerIcon), app)
    tray.setToolTip("Jarvis")
    menu = QMenu()
    menu.addAction("Ouvrir Jarvis", window.show)
    menu.addSeparator()
    menu.addAction("Quitter", app.quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: window.show() if reason == QSystemTrayIcon.Trigger else None)
    tray.show()

    window.show()
    code = app.exec()
    ctx.alarms.stop()
    return code
