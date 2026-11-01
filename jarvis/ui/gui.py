"""Interface graphique : fenêtre de discussion façon assistant en ligne + icône dans la barre système (PySide6).

- Barre latérale : nouvelle conversation, conversations précédentes (gardées dans ~/.jarvis/jarvis.db)
- Fil de discussion : réponse en Markdown affichée au fil de l'eau, outils utilisés, confirmations dans le fil
- Saisie : Entrée envoie, Maj+Entrée va à la ligne
- Pièces jointes : bouton ＋, glisser-déposer n'importe où, ou Ctrl+V d'une image (capture d'écran).
  Rien n'est copié : Jarvis reçoit le chemin du fichier et le lit lui-même avec ses outils d'analyse.
- Raccourcis : Ctrl+N nouvelle conversation, Échap arrête la réponse
- Une seule fenêtre : relancer Jarvis (menu des applications, commande) ramène celle déjà ouverte
"""
import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QKeySequence, QPalette, QShortcut
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollArea, QSizePolicy, QStackedWidget, QStyle, QSystemTrayIcon, QVBoxLayout,
                               QWidget)

import jarvis.tools  # noqa: F401  (avant jarvis.analyzers : les deux s'importent l'un l'autre)
from jarvis.analyzers import ARCHIVE_EXT, AUDIO_EXT, IMAGE_EXT, OFFICE_EXT, VIDEO_EXT
from jarvis.bootstrap import create_agent
from jarvis.core.confirmation import Confirmer
from jarvis.core.context import ctx
from jarvis.core.tools import TOOL_LABELS

SERVER_NAME = "jarvis-fenetre"   # canal local par lequel un 2e lancement demande d'afficher la fenêtre
COLUMN_WIDTH = 760   # largeur max du fil de discussion, centré comme sur les assistants en ligne

LIGHT = {
    "bg": "#ffffff", "sidebar": "#f7f7f8", "text": "#1f1f1f", "muted": "#6e6e73", "border": "#e3e3e6",
    "hover": "#ececef", "selected": "#e3e3e8", "bubble": "#f1f1f3", "chip": "#f3f3f5", "accent": "#2f6fed",
    "composer": "#ffffff", "disabled": "#c9c9cf", "scroll": "#d0d0d5", "error": "#c0392b",
    "warn_bg": "#fff8ec", "warn_border": "#f0c27a", "warn_text": "#8a5300",
}
DARK = {
    "bg": "#212121", "sidebar": "#171717", "text": "#ececec", "muted": "#9b9ba1", "border": "#363636",
    "hover": "#2c2c2e", "selected": "#333336", "bubble": "#303030", "chip": "#2a2a2c", "accent": "#6a9cff",
    "composer": "#2b2b2b", "disabled": "#4a4a4d", "scroll": "#4a4a4d", "error": "#ff7b6b",
    "warn_bg": "#2e2618", "warn_border": "#8f6a2c", "warn_text": "#ffc46b",
}

SUGGESTIONS = [
    ("Que contient mon dossier Téléchargements ?", True),
    ("Comment va mon ordinateur ?", True),
    ("Lance un minuteur de 10 minutes", True),
    ("Donne ton avis sur mon projet situé dans ", False),   # à compléter par l'utilisateur
]


# Ajouté au message envoyé au cerveau, puis retiré à l'affichage pour montrer des étiquettes de fichier
ATTACH_MARK = "\n\n[Fichiers joints — lis-les avec analyze_file (ou read_file pour du texte) avant de répondre]\n"


def with_attachments(text: str, paths: list[str]) -> str:
    if not paths:
        return text
    return (text or "Analyse ce que je t'ai joint.") + ATTACH_MARK + "\n".join(f"- {p}" for p in paths)


def split_attachments(content: str) -> tuple[str, list[str]]:
    text, mark, files = content.partition(ATTACH_MARK)
    return text, [line[2:] for line in files.splitlines() if line.startswith("- ")] if mark else []


def file_icon(path: str) -> str:
    p = Path(path)
    if p.is_dir():
        return "📁"
    ext = p.suffix.lower()
    for exts, icon in ((IMAGE_EXT, "🖼"), (AUDIO_EXT, "🎵"), (VIDEO_EXT, "🎬"), (ARCHIVE_EXT, "🗜"),
                       (OFFICE_EXT, "📊"), ({".pdf"}, "📕")):
        if ext in exts:
            return icon
    return "📄"


def stylesheet(t: dict) -> str:
    return f"""
    QMainWindow, #chatPage, #column, #welcome, #header {{ background: {t['bg']}; }}
    QWidget {{ color: {t['text']}; font-size: 14px; }}
    QToolTip {{ background: {t['bubble']}; color: {t['text']}; border: 1px solid {t['border']}; }}
    QScrollArea {{ background: {t['bg']}; border: none; }}

    #sidebar {{ background: {t['sidebar']}; border-right: 1px solid {t['border']}; }}
    #brand {{ font-size: 16px; font-weight: 700; padding: 4px 6px; }}
    #newChat {{ text-align: left; padding: 9px 12px; border: 1px solid {t['border']}; border-radius: 10px;
                background: {t['bg']}; }}
    #newChat:hover {{ background: {t['hover']}; }}
    #section {{ color: {t['muted']}; font-size: 12px; padding: 14px 6px 4px; }}
    #chatList {{ background: transparent; border: none; outline: none; }}
    #chatList::item {{ padding: 8px 10px; border-radius: 8px; color: {t['text']}; }}
    #chatList::item:hover {{ background: {t['hover']}; }}
    #chatList::item:selected {{ background: {t['selected']}; }}
    #footer {{ color: {t['muted']}; font-size: 12px; padding: 6px; }}

    #title {{ font-size: 15px; font-weight: 600; }}
    #iconButton {{ border: none; border-radius: 8px; padding: 5px 10px; background: transparent; font-size: 17px; }}
    #iconButton:hover {{ background: {t['hover']}; }}

    #welcomeTitle {{ font-size: 28px; font-weight: 600; }}
    #welcomeText {{ color: {t['muted']}; font-size: 15px; }}
    #suggestion {{ text-align: left; padding: 14px; border: 1px solid {t['border']}; border-radius: 12px;
                   background: {t['bg']}; }}
    #suggestion:hover {{ background: {t['hover']}; }}

    #userBubble {{ background: {t['bubble']}; border-radius: 18px; padding: 10px 16px; font-size: 15px; }}
    #avatar {{ background: {t['accent']}; color: #ffffff; border-radius: 13px; font-weight: 700; font-size: 13px; }}
    #name {{ font-weight: 600; }}
    #body {{ font-size: 15px; }}
    #thinking {{ color: {t['muted']}; font-size: 15px; }}
    #step {{ color: {t['muted']}; background: {t['chip']}; border-radius: 8px; padding: 4px 10px; font-size: 12px; }}
    #stepError {{ color: {t['error']}; background: {t['chip']}; border-radius: 8px; padding: 4px 10px;
                  font-size: 12px; }}
    #notice {{ color: {t['error']}; border: 1px solid {t['error']}; border-radius: 10px; padding: 10px 14px; }}
    #copy {{ border: none; color: {t['muted']}; background: transparent; padding: 3px 8px; border-radius: 6px;
             font-size: 12px; }}
    #copy:hover {{ background: {t['hover']}; color: {t['text']}; }}

    #confirmCard {{ background: {t['warn_bg']}; border: 1px solid {t['warn_border']}; border-radius: 12px; }}
    #confirmTitle {{ color: {t['warn_text']}; font-weight: 600; }}
    #confirmAction {{ font-weight: 600; }}
    #preview {{ font-family: monospace; font-size: 12px; background: {t['bg']}; border: 1px solid {t['border']};
                border-radius: 8px; padding: 8px; }}
    #confirmStatus {{ color: {t['muted']}; font-size: 13px; }}
    #primary {{ background: {t['text']}; color: {t['bg']}; border: none; border-radius: 8px; padding: 7px 16px;
                font-weight: 600; }}
    #secondary {{ background: transparent; border: 1px solid {t['border']}; border-radius: 8px; padding: 7px 16px; }}
    #secondary:hover {{ background: {t['hover']}; }}

    #composerBox {{ background: {t['composer']}; border: 1px solid {t['border']}; border-radius: 22px; }}
    #composer {{ background: transparent; border: none; font-size: 15px;
                 selection-background-color: {t['accent']}; selection-color: #ffffff; }}
    #send {{ background: {t['text']}; color: {t['bg']}; border: none; border-radius: 17px; font-size: 16px;
             font-weight: 700; }}
    #send:disabled {{ background: {t['disabled']}; }}
    #hint {{ color: {t['muted']}; font-size: 12px; }}
    #fileChip {{ background: {t['chip']}; border: 1px solid {t['border']}; border-radius: 10px; }}
    #fileName {{ font-size: 13px; }}
    #fileKind {{ color: {t['muted']}; font-size: 11px; }}
    #chipClose {{ border: none; background: transparent; color: {t['muted']}; font-size: 13px; padding: 0 4px; }}
    #chipClose:hover {{ color: {t['text']}; }}
    #dropHint {{ color: {t['accent']}; font-size: 13px; }}

    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t['scroll']}; border-radius: 3px; min-height: 30px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    QMenu {{ background: {t['bg']}; border: 1px solid {t['border']}; padding: 4px; }}
    QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {t['hover']}; }}
    """


def is_dark(app: QApplication) -> bool:
    scheme = getattr(app.styleHints(), "colorScheme", lambda: None)()   # Qt 6.5+
    if scheme == Qt.ColorScheme.Dark:
        return True
    if scheme == Qt.ColorScheme.Light:
        return False
    return app.palette().color(QPalette.Window).lightness() < 128


class WrapLabel(QLabel):
    """QLabel à retour à la ligne qui réclame toujours la hauteur de son texte.

    Sans cela, Qt calcule parfois la hauteur pour une autre largeur et coupe la fin du texte
    (ex. une conversation rouverte, dessinée avant que la fenêtre ait sa taille).
    """

    def resizeEvent(self, e):
        super().resizeEvent(e)
        h = self.heightForWidth(self.width())
        if h > 0 and h != self.minimumHeight():
            self.setMinimumHeight(h)

    def setText(self, text: str) -> None:
        super().setText(text)
        h = self.heightForWidth(self.width())
        if h > 0:
            self.setMinimumHeight(h)


def _label(text: str = "", name: str = "", fmt=Qt.PlainText, selectable: bool = False) -> QLabel:
    lab = WrapLabel(text)
    lab.setObjectName(name)
    lab.setTextFormat(fmt)
    lab.setWordWrap(True)
    if selectable:
        lab.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        lab.setOpenExternalLinks(True)
    return lab


# ---------------------------------------------------------------------------------------------- fil de l'agent
class Bridge(QObject):
    """Fait passer les événements du fil de l'agent vers le fil de l'interface."""
    delta = Signal(str)
    event = Signal(str, object)
    confirm_requested = Signal(str)


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

    def __init__(self, agent, text: str, bridge: Bridge):
        super().__init__()
        self.agent, self.text, self.bridge = agent, text, bridge

    def run(self):
        try:
            self.finished_with.emit(self.agent.run(self.text, on_delta=self.bridge.delta.emit))
        except Exception as e:
            self.finished_with.emit(f"Erreur : {e}")


# ---------------------------------------------------------------------------------------------- messages
class FileChip(QFrame):
    """Un fichier joint : icône, nom, dossier ; avec une croix pour le retirer avant l'envoi."""

    def __init__(self, path: str, on_remove=None):
        super().__init__()
        self.setObjectName("fileChip")
        self.setToolTip(path)
        p = Path(path)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 6 if on_remove else 12, 6)
        row.setSpacing(8)
        icon = QLabel(file_icon(path))
        icon.setStyleSheet("font-size: 20px;")
        row.addWidget(icon)
        names = QVBoxLayout()
        names.setSpacing(0)
        name = QLabel(p.name if len(p.name) <= 32 else p.name[:29] + "…")
        name.setObjectName("fileName")
        kind = QLabel("Dossier" if p.is_dir() else (p.suffix[1:].upper() or "Fichier") if p.exists() else "Introuvable")
        kind.setObjectName("fileKind")
        names.addWidget(name)
        names.addWidget(kind)
        row.addLayout(names)
        if on_remove:
            close = QPushButton("✕")
            close.setObjectName("chipClose")
            close.setCursor(Qt.PointingHandCursor)
            close.setToolTip("Retirer")
            close.clicked.connect(lambda: on_remove(path))
            row.addWidget(close, 0, Qt.AlignTop)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)


class UserMessage(QWidget):
    def __init__(self, text: str, files: list[str] | None = None):
        super().__init__()
        files = files or []
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        for path in files:
            line = QHBoxLayout()
            line.addStretch()
            line.addWidget(FileChip(path))
            column.addLayout(line)
        if not text.strip():
            return
        bubble = _label(text, "userBubble", selectable=True)
        widest = int(COLUMN_WIDTH * 0.75)
        bubble.setMaximumWidth(widest)
        # Largeur naturelle du texte : sinon un QLabel à retour à la ligne se replie bien trop tôt
        bubble.ensurePolished()
        natural = max((bubble.fontMetrics().horizontalAdvance(line) for line in text.splitlines() or [""]), default=0)
        bubble.setMinimumWidth(min(natural + 48, widest))
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(bubble)
        column.addLayout(row)


class ConfirmCard(QFrame):
    """L'action à valider, dans le fil : rien ne se fait tant qu'on n'a pas cliqué."""

    def __init__(self, action: str, on_answer):
        super().__init__()
        self.setObjectName("confirmCard")
        self.on_answer = on_answer
        first, _, rest = action.partition("\n")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        lay.addWidget(_label("⚠  Confirmation requise", "confirmTitle"))
        lay.addWidget(_label(first, "confirmAction", selectable=True))
        if rest.strip():
            lay.addWidget(_label(rest, "preview", selectable=True))

        self.buttons = QWidget()
        row = QHBoxLayout(self.buttons)
        row.setContentsMargins(0, 4, 0, 0)
        yes, no = QPushButton("Autoriser"), QPushButton("Refuser")
        yes.setObjectName("primary")
        no.setObjectName("secondary")
        for b in (yes, no):
            b.setCursor(Qt.PointingHandCursor)
        yes.clicked.connect(lambda: self.answer(True))
        no.clicked.connect(lambda: self.answer(False))
        row.addWidget(yes)
        row.addWidget(no)
        row.addStretch()
        lay.addWidget(self.buttons)
        self.status = _label("", "confirmStatus")
        self.status.hide()
        lay.addWidget(self.status)

    def answer(self, ok: bool) -> None:
        if self.on_answer is None:
            return
        callback, self.on_answer = self.on_answer, None
        self.buttons.hide()
        self.status.setText("✓ Autorisé" if ok else "✕ Refusé")
        self.status.show()
        callback(ok)


class AssistantMessage(QWidget):
    def __init__(self):
        super().__init__()
        self.text = ""
        self._dirty = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        header = QHBoxLayout()
        avatar = QLabel("J")
        avatar.setObjectName("avatar")
        avatar.setFixedSize(26, 26)
        avatar.setAlignment(Qt.AlignCenter)
        header.addWidget(avatar)
        header.addWidget(_label("Jarvis", "name"))
        header.addStretch()
        lay.addLayout(header)

        self.steps = QVBoxLayout()            # outils utilisés et confirmations, dans l'ordre
        self.steps.setSpacing(6)
        lay.addLayout(self.steps)
        self.body = _label("", "body", Qt.MarkdownText, selectable=True)
        self.body.hide()
        lay.addWidget(self.body)
        self.thinking = _label("Réflexion", "thinking")
        self.thinking.hide()
        lay.addWidget(self.thinking)

        self.actions = QWidget()
        row = QHBoxLayout(self.actions)
        row.setContentsMargins(0, 4, 0, 0)
        copy = QPushButton("Copier")
        copy.setObjectName("copy")
        copy.setCursor(Qt.PointingHandCursor)
        copy.clicked.connect(lambda: (QApplication.clipboard().setText(self.text), copy.setText("Copié ✓"),
                                      QTimer.singleShot(1500, lambda: copy.setText("Copier"))))
        row.addWidget(copy)
        row.addStretch()
        self.actions.hide()
        lay.addWidget(self.actions)

        self._dots = 0
        self._dot_timer = QTimer(self)
        self._dot_timer.timeout.connect(self._animate)

    def start_thinking(self) -> None:
        self.thinking.show()
        self._dot_timer.start(400)

    def _animate(self) -> None:
        self._dots = (self._dots + 1) % 4
        self.thinking.setText("Réflexion" + "." * self._dots)

    def add_step(self, text: str, error: bool = False) -> None:
        chip = _label(text, "stepError" if error else "step")
        chip.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self.steps.addWidget(chip)

    def add_widget(self, widget: QWidget) -> None:
        self.steps.addWidget(widget)

    def append(self, piece: str) -> None:
        self.text += piece
        self._dirty = True

    def set_text(self, text: str) -> None:
        self.text = text
        self._dirty = True
        self.render()

    def render(self) -> None:
        """Appelé à intervalle régulier : re-dessiner le Markdown à chaque mot serait trop lent."""
        if not self._dirty:
            return
        self._dirty = False
        self.body.setText(self.text)
        self.body.setVisible(bool(self.text.strip()))
        if self.text.strip():
            self._dot_timer.stop()
            self.thinking.hide()

    def finish(self) -> None:
        self.render()
        self._dot_timer.stop()
        self.thinking.hide()
        self.actions.setVisible(bool(self.text.strip()))


# ---------------------------------------------------------------------------------------------- saisie
class Composer(QPlainTextEdit):
    submitted = Signal()
    files_added = Signal(list)
    MAX_LINES = 8

    def __init__(self):
        super().__init__()
        self.setObjectName("composer")
        self.setPlaceholderText("Écris à Jarvis…")
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.document().documentLayout().documentSizeChanged.connect(self._fit)
        self._fit()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not e.modifiers() & Qt.ShiftModifier:
            self.submitted.emit()
            return
        super().keyPressEvent(e)

    def canInsertFromMimeData(self, source):
        return source.hasImage() or source.hasUrls() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        """Fichier glissé ou collé : il devient une pièce jointe. Image collée : enregistrée puis jointe."""
        paths = [u.toLocalFile() for u in source.urls() if u.isLocalFile()] if source.hasUrls() else []
        if paths:
            self.files_added.emit(paths)
        elif source.hasImage():
            folder = Path(ctx.cfg.get("data_dir", Path.home() / ".jarvis")) / "uploads"
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / f"image-collee-{datetime.now():%Y%m%d-%H%M%S}.png"
            if source.imageData().save(str(target)):
                self.files_added.emit([str(target)])
        else:
            super().insertFromMimeData(source)

    def _fit(self, *_):
        lines = max(1, min(self.MAX_LINES, int(self.document().documentLayout().documentSize().height())))
        margin = int(self.document().documentMargin() * 2) + 6
        self.setFixedHeight(self.fontMetrics().lineSpacing() * lines + margin)


# ---------------------------------------------------------------------------------------------- fenêtre
class ChatWindow(QMainWindow):
    def __init__(self, agent, confirmer: QtConfirmer, bridge: Bridge):
        super().__init__()
        self.agent, self.confirmer, self.bridge = agent, confirmer, bridge
        self.worker: AgentWorker | None = None
        self.current: AssistantMessage | None = None
        self.pending: ConfirmCard | None = None
        self.chat_id: int | None = None
        self.chat_title = ""
        self.attachments: list[str] = []
        self.following = True     # le fil suit la réponse, sauf si l'utilisateur est remonté le lire

        self.setWindowTitle("Jarvis")
        self.resize(1120, 780)
        self.setMinimumSize(720, 520)
        self.setAcceptDrops(True)

        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.sidebar = self._build_sidebar()
        h.addWidget(self.sidebar)
        h.addWidget(self._build_main(), 1)
        self.setCentralWidget(root)

        bridge.delta.connect(self.on_delta)
        bridge.event.connect(self.on_event)
        bridge.confirm_requested.connect(self.on_confirm)
        QShortcut(QKeySequence.New, self, activated=self.new_chat)
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.stop)

        self.render_timer = QTimer(self)
        self.render_timer.timeout.connect(lambda: self.current and self.current.render())
        self.render_timer.start(50)

        self.refresh_chats()
        self.composer.setFocus()
        if not ctx.llm.ensure_running():
            self.notice("Ollama ne répond pas. Lance « ollama serve » puis redémarre Jarvis.")
        else:   # lit consignes et outils pendant que tu tapes ta première question
            threading.Thread(target=agent.warm_up, daemon=True).start()

    # ------------------------------------------------------------ construction
    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(260)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(12, 14, 12, 10)
        lay.setSpacing(6)
        lay.addWidget(_label("Jarvis", "brand"))
        self.new_btn = QPushButton("＋   Nouvelle conversation")
        self.new_btn.setObjectName("newChat")
        self.new_btn.setCursor(Qt.PointingHandCursor)
        self.new_btn.clicked.connect(self.new_chat)
        lay.addWidget(self.new_btn)
        lay.addWidget(_label("Récentes", "section"))
        self.chat_list = QListWidget()
        self.chat_list.setObjectName("chatList")
        self.chat_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chat_list.setTextElideMode(Qt.ElideRight)
        self.chat_list.itemClicked.connect(lambda it: self.open_chat(it.data(Qt.UserRole)))
        self.chat_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.chat_list.customContextMenuRequested.connect(self._chat_menu)
        lay.addWidget(self.chat_list, 1)
        lay.addWidget(_label(f"● Local · {ctx.llm.model} · {ctx.os.name}", "footer"))
        return side

    def _build_main(self) -> QWidget:
        main = QWidget()
        main.setObjectName("chatPage")
        v = QVBoxLayout(main)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        header = QWidget()
        header.setObjectName("header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(10, 8, 16, 8)
        toggle = QPushButton("☰")
        toggle.setObjectName("iconButton")
        toggle.setToolTip("Afficher / masquer les conversations")
        toggle.setCursor(Qt.PointingHandCursor)
        toggle.clicked.connect(lambda: self.sidebar.setVisible(not self.sidebar.isVisible()))
        self.title = _label("Nouvelle conversation", "title")
        self.title.setWordWrap(False)
        hl.addWidget(toggle)
        hl.addWidget(self.title, 1)
        v.addWidget(header)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_welcome())
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        holder.setObjectName("column")
        outer = QHBoxLayout(holder)
        outer.setContentsMargins(24, 16, 24, 24)
        column = QWidget()
        column.setObjectName("column")
        column.setMaximumWidth(COLUMN_WIDTH)
        self.messages = QVBoxLayout(column)
        self.messages.setContentsMargins(0, 0, 0, 0)
        self.messages.setSpacing(22)
        self.messages.addStretch()
        outer.addStretch()
        outer.addWidget(column, 100)
        outer.addStretch()
        self.scroll.setWidget(holder)
        bar = self.scroll.verticalScrollBar()
        bar.rangeChanged.connect(lambda _lo, hi: self.following and bar.setValue(hi))
        bar.valueChanged.connect(lambda val: setattr(self, "following", val >= bar.maximum() - 40))
        self.stack.addWidget(self.scroll)
        v.addWidget(self.stack, 1)
        v.addWidget(self._build_composer())
        return main

    def _build_welcome(self) -> QWidget:
        page = QWidget()
        page.setObjectName("welcome")
        v = QVBoxLayout(page)
        v.addStretch(2)
        title = _label("Que puis-je faire pour toi ?", "welcomeTitle")
        title.setAlignment(Qt.AlignCenter)
        text = _label("Je lis et range tes fichiers, ouvre tes applications, règle des alarmes et donne mon avis "
                      "sur tes projets. Tout reste sur ton ordinateur.", "welcomeText")
        text.setAlignment(Qt.AlignCenter)
        text.setMaximumWidth(560)
        v.addWidget(title)
        v.addSpacing(6)
        centered = QHBoxLayout()
        centered.addStretch()
        centered.addWidget(text, 100)
        centered.addStretch()
        v.addLayout(centered)
        v.addSpacing(24)
        grid = QGridLayout()
        grid.setSpacing(10)
        for i, (prompt, send_now) in enumerate(SUGGESTIONS):
            b = QPushButton(prompt.strip() + ("" if send_now else "…"))
            b.setObjectName("suggestion")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, p=prompt, s=send_now: self.send(p) if s else self._prefill(p))
            grid.addWidget(b, i // 2, i % 2)
        row = QHBoxLayout()
        row.addStretch()
        box = QWidget()
        box.setMaximumWidth(COLUMN_WIDTH)
        box.setLayout(grid)
        row.addWidget(box, 100)
        row.addStretch()
        v.addLayout(row)
        v.addStretch(3)
        return page

    def _build_composer(self) -> QWidget:
        area = QWidget()
        area.setObjectName("chatPage")
        outer = QVBoxLayout(area)
        outer.setContentsMargins(24, 4, 24, 12)
        outer.setSpacing(6)

        box = QFrame()
        box.setObjectName("composerBox")
        box.setMaximumWidth(COLUMN_WIDTH)
        inside = QVBoxLayout(box)
        inside.setContentsMargins(8, 8, 8, 8)
        inside.setSpacing(6)
        self.attach_bar = QWidget()
        self.attach_row = QHBoxLayout(self.attach_bar)
        self.attach_row.setContentsMargins(4, 2, 4, 0)
        self.attach_row.setSpacing(8)
        self.attach_row.addStretch()
        self.attach_bar.hide()
        inside.addWidget(self.attach_bar)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        inside.addLayout(row)

        attach = QPushButton("＋")
        attach.setObjectName("iconButton")
        attach.setFixedSize(34, 34)
        attach.setCursor(Qt.PointingHandCursor)
        attach.setToolTip("Joindre des fichiers (ou glisse-les dans la fenêtre)")
        attach.clicked.connect(self.pick_files)
        row.addWidget(attach, 0, Qt.AlignBottom)
        self.composer = Composer()
        self.composer.submitted.connect(self.send)
        self.composer.textChanged.connect(self._update_send)
        self.composer.files_added.connect(self.add_attachments)
        self.send_btn = QPushButton("↑")
        self.send_btn.setObjectName("send")
        self.send_btn.setFixedSize(34, 34)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.clicked.connect(lambda: self.stop() if self.busy else self.send())
        row.addWidget(self.composer, 1)
        row.addWidget(self.send_btn, 0, Qt.AlignBottom)

        hint = _label("Jarvis tourne sur ton ordinateur et demande ton accord avant toute modification.", "hint")
        hint.setAlignment(Qt.AlignCenter)
        for w in (box, hint):
            line = QHBoxLayout()
            line.addStretch()
            line.addWidget(w, 100)
            line.addStretch()
            outer.addLayout(line)
        self._update_send()
        return area

    # ------------------------------------------------------------ conversation
    @property
    def busy(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def send(self, text: str | None = None) -> None:
        text = (text or self.composer.toPlainText()).strip()
        files = list(self.attachments)
        if not (text or files) or self.busy:
            return
        self.composer.clear()
        self._clear_attachments()
        self.stack.setCurrentWidget(self.scroll)
        if self.chat_id is None and not self.chat_title:
            first = text or ", ".join(Path(f).name for f in files)
            self.chat_title = first if len(first) <= 48 else first[:47].rstrip() + "…"
            self.title.setText(self.chat_title)
        self.following = True
        self._add(UserMessage(text, files))
        self.current = AssistantMessage()
        self._add(self.current)
        self.current.start_thinking()

        self.worker = AgentWorker(self.agent, with_attachments(text, files), self.bridge)
        self.worker.finished_with.connect(self.on_answer)
        self.worker.start()
        self._set_busy(True)

    # ------------------------------------------------------------ pièces jointes
    def pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Joindre des fichiers", str(Path.home()))
        self.add_attachments(paths)

    def add_attachments(self, paths: list[str]) -> None:
        for path in paths:
            if path and path not in self.attachments:
                self.attachments.append(path)
                self.attach_row.insertWidget(self.attach_row.count() - 1, FileChip(path, self.remove_attachment))
        self.attach_bar.setVisible(bool(self.attachments))
        self._update_send()
        self.composer.setFocus()

    def remove_attachment(self, path: str) -> None:
        paths = [p for p in self.attachments if p != path]
        self._clear_attachments()
        self.add_attachments(paths)

    def _clear_attachments(self) -> None:
        self.attachments = []
        while self.attach_row.count() > 1:
            w = self.attach_row.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.attach_bar.hide()
        self._update_send()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.add_attachments([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])
        e.acceptProposedAction()

    def stop(self) -> None:
        if not self.busy:
            return
        self.agent.cancel()
        if self.pending:
            self.pending.answer(False)

    def on_delta(self, piece: str) -> None:
        if self.current:
            self.current.append(piece)

    def on_event(self, kind: str, data: dict) -> None:
        if not self.current:
            return
        if kind == "retry":                 # le cerveau a écrit un appel au lieu de le faire : on efface et il recommence
            self.current.set_text("")
            self.current.start_thinking()
        elif kind == "tool_start":
            self.current.add_step(TOOL_LABELS.get(data["tool"], f"Outil : {data['tool']}"))
        elif kind == "cancelled":
            self.current.add_step("✕ Action refusée")
        elif kind == "tool_result" and data["result"].get("statut") == "erreur":
            self.current.add_step(f"⚠ {data['result'].get('message', 'Erreur')}"[:160], error=True)

    def on_confirm(self, action: str) -> None:
        self.reveal()

        def answered(ok: bool) -> None:
            self.pending = None
            self.confirmer.resolve(ok)

        self.pending = ConfirmCard(action, answered)
        if self.current:
            self.current.add_widget(self.pending)
        self.following = True

    def on_answer(self, answer: str) -> None:
        if self.current:
            if answer and not self.current.text.strip():   # erreur, ou réponse non diffusée
                self.current.set_text(answer)
            self.current.finish()
        self.current = None
        self._set_busy(False)
        self._save()

    # ------------------------------------------------------------ conversations enregistrées
    def new_chat(self) -> None:
        if self.busy:
            return
        self.agent.reset()
        self.chat_id, self.chat_title = None, ""
        self._clear()
        self.title.setText("Nouvelle conversation")
        self.stack.setCurrentIndex(0)
        self.chat_list.clearSelection()
        self.composer.setFocus()

    def open_chat(self, chat_id: int) -> None:
        if self.busy or chat_id == self.chat_id:
            return
        try:
            title, history = ctx.memory.load_chat(chat_id)
        except KeyError:
            self.refresh_chats()
            return
        self.agent.load(history)
        self.chat_id, self.chat_title = chat_id, title
        self.title.setText(title)
        self._clear()
        self._replay(history)
        self.stack.setCurrentWidget(self.scroll)
        self.following = True
        self.composer.setFocus()

    def delete_chat(self, chat_id: int) -> None:
        if self.busy:
            return
        if QMessageBox.question(self, "Supprimer", "Supprimer cette conversation ?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        ctx.memory.delete_chat(chat_id)
        if chat_id == self.chat_id:
            self.new_chat()
        self.refresh_chats()

    def refresh_chats(self) -> None:
        self.chat_list.clear()
        for chat in ctx.memory.list_chats():
            item = QListWidgetItem(chat["title"])
            item.setData(Qt.UserRole, chat["id"])
            item.setToolTip(chat["title"])
            self.chat_list.addItem(item)
            if chat["id"] == self.chat_id:
                item.setSelected(True)

    def _save(self) -> None:
        self.chat_id = ctx.memory.save_chat(self.chat_id, self.chat_title or "Conversation", self.agent.history[1:])
        self.refresh_chats()

    def _replay(self, history: list[dict]) -> None:
        """Redessine une conversation enregistrée : une demande, puis tout ce que Jarvis a fait pour y répondre."""
        msg: AssistantMessage | None = None
        for m in history:
            role = m.get("role")
            if role == "system":
                continue
            if role == "user":
                if msg:
                    msg.finish()
                    msg = None
                self._add(UserMessage(*split_attachments(m.get("content", ""))))
                continue
            if msg is None:
                msg = AssistantMessage()
                self._add(msg)
            if role == "assistant":
                if not m.get("tool_calls") and self.agent._unsent_call(m.get("content", "")):
                    continue                # réponse ratée, relancée juste après
                for call in m.get("tool_calls") or []:
                    name = call.get("function", {}).get("name", "")
                    msg.add_step(TOOL_LABELS.get(name, f"Outil : {name}"))
                if m.get("content"):
                    msg.set_text((msg.text + "\n\n" + m["content"]).strip())
            elif role == "tool" and "annulé par l'utilisateur" in m.get("content", ""):
                msg.add_step("✕ Action refusée")
        if msg:
            msg.finish()

    def _chat_menu(self, pos) -> None:
        item = self.chat_list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        menu.addAction("Supprimer", lambda: self.delete_chat(item.data(Qt.UserRole)))
        menu.exec(self.chat_list.mapToGlobal(pos))

    # ------------------------------------------------------------ utilitaires
    def notice(self, text: str) -> None:
        self.stack.setCurrentWidget(self.scroll)
        self._add(_label(text, "notice"))

    def _add(self, widget: QWidget) -> None:
        self.messages.insertWidget(self.messages.count() - 1, widget)

    def _clear(self) -> None:
        while self.messages.count() > 1:
            w = self.messages.takeAt(0).widget()
            if w:
                w.deleteLater()

    def _prefill(self, text: str) -> None:
        self.composer.setPlainText(text)
        cursor = self.composer.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.composer.setTextCursor(cursor)
        self.composer.setFocus()

    def _set_busy(self, busy: bool) -> None:
        self.new_btn.setEnabled(not busy)
        self.chat_list.setEnabled(not busy)
        self.send_btn.setText("■" if busy else "↑")
        self.send_btn.setToolTip("Arrêter (Échap)" if busy else "Envoyer (Entrée)")
        self._update_send()
        if not busy:
            self.composer.setFocus()

    def _update_send(self) -> None:
        self.send_btn.setEnabled(self.busy or bool(self.composer.toPlainText().strip() or self.attachments))

    def reveal(self) -> None:
        """Ramène la fenêtre, même cachée, réduite ou derrière d'autres fenêtres.

        Sous Wayland, une application ne peut pas se mettre d'elle-même au premier plan : on la ré-affiche,
        ce qui la fait réapparaître par-dessus.
        """
        if self.isVisible() and not self.isActiveWindow():
            self.hide()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):   # fermer = cacher dans la barre système (ou quitter s'il n'y en a pas)
        if QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide()
        else:
            QApplication.quit()


def _show_running_instance() -> bool:
    """Si Jarvis est déjà ouvert, lui demande d'afficher sa fenêtre et renvoie True."""
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(500):
        return False
    sock.write(b"show")
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


def _listen_for_instances(app: QApplication, window: ChatWindow) -> QLocalServer:
    server = QLocalServer(app)
    QLocalServer.removeServer(SERVER_NAME)   # reste d'un Jarvis qui aurait planté
    server.listen(SERVER_NAME)

    def on_connection():
        conn = server.nextPendingConnection()
        conn.disconnected.connect(conn.deleteLater)
        window.reveal()

    server.newConnection.connect(on_connection)
    return server


def run_gui(cfg: dict) -> int:
    app = QApplication(sys.argv)
    if _show_running_instance():
        print("Jarvis est déjà ouvert : sa fenêtre est ramenée au premier plan.")
        return 0
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    apply_theme = lambda *_: app.setStyleSheet(stylesheet(DARK if is_dark(app) else LIGHT))  # noqa: E731
    apply_theme()
    if hasattr(app.styleHints(), "colorSchemeChanged"):
        app.styleHints().colorSchemeChanged.connect(apply_theme)

    bridge = Bridge()
    confirmer = QtConfirmer(bridge)
    agent = create_agent(cfg, confirmer)
    agent.on_event = lambda kind, data: bridge.event.emit(kind, data)

    window = ChatWindow(agent, confirmer, bridge)
    server = _listen_for_instances(app, window)  # noqa: F841  (doit vivre aussi longtemps que l'application)

    tray = QSystemTrayIcon(app.style().standardIcon(QStyle.SP_ComputerIcon), app)
    tray.setToolTip("Jarvis")
    menu = QMenu()
    menu.addAction("Ouvrir Jarvis", window.reveal)
    menu.addAction("Nouvelle conversation", lambda: (window.reveal(), window.new_chat()))
    menu.addSeparator()
    menu.addAction("Quitter", app.quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: window.reveal() if reason == QSystemTrayIcon.Trigger else None)
    tray.show()

    window.show()
    code = app.exec()
    ctx.alarms.stop()
    return code
