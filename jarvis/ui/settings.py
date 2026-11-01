"""Fenêtre Paramètres : tout ce que contient config.yaml, plus le lancement automatique et les données.

Enregistré dans ~/.jarvis/config.yaml. Cerveau, comportement, sécurité, analyse et recherche s'appliquent
tout de suite ; la voix et l'activation au prochain lancement du mode vocal (un autre programme).
"""
import copy
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPlainTextEdit,
                               QPushButton, QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from jarvis import autostart
from jarvis.config import DEFAULT_CONFIG, load_config
from jarvis.core.context import ctx
from jarvis.core.llm import LLMError, OllamaClient
from jarvis.ui.widgets import WrapLabel

VOICE_NOTE = "S'applique au prochain lancement de « Jarvis (voix) »."

# (clé dans config.yaml, type, libellé, explication, options)
SECTIONS = [
    ("Cerveau", "Le modèle local qui comprend tes demandes et y répond (Ollama).", [
        ("llm.model", "model", "Modèle principal",
         "Répond et utilise les outils. Plus gros = plus juste, mais plus lent.", {}),
        ("llm.vision_model", "model", "Modèle vision",
         "« Voit » les images, les PDF scannés et les vidéos. Vide = pas de vision.", {}),
        ("llm.options.temperature", "float", "Créativité",
         "0 = réponses stables et précises, 1 = plus variées.", {"min": 0, "max": 1.5, "step": 0.1}),
        ("llm.options.num_ctx", "choice", "Mémoire de travail",
         "Ce que le modèle garde en tête d'une conversation. Plus grand = plus de mémoire vive et plus lent.",
         {"options": [(2048, "2 048"), (4096, "4 096"), (8192, "8 192 (conseillé)"), (16384, "16 384"),
                      (32768, "32 768")]}),
        ("llm.keep_alive", "choice", "Garder le modèle chargé",
         "Après une réponse. Plus long = pas d'attente de chargement, mais la mémoire vive reste occupée.",
         {"options": [("5m", "5 minutes"), ("30m", "30 minutes"), ("2h", "2 heures"), (-1, "Toujours")]}),
        ("llm.timeout", "int", "Attente maximale d'une réponse", "Au-delà, Jarvis abandonne.",
         {"min": 30, "max": 3600, "step": 30, "suffix": " s"}),
        ("llm.host", "text", "Adresse d'Ollama", "À changer seulement si Ollama tourne sur une autre machine.", {}),
    ]),
    ("Comportement", "Comment Jarvis travaille et s'affiche.", [
        ("assistant.name", "text", "Nom", "Comment Jarvis s'appelle. Pris en compte à la prochaine conversation.", {}),
        ("interface.theme", "choice", "Thème de la fenêtre", "",
         {"options": [("auto", "Comme le système"), ("light", "Clair"), ("dark", "Sombre")]}),
        ("assistant.max_steps", "int", "Étapes max par demande",
         "Nombre d'actions (lire, chercher…) que Jarvis peut enchaîner pour une seule demande.",
         {"min": 1, "max": 50}),
        ("assistant.max_tool_output", "int", "Taille max d'un résultat d'outil",
         "Ce que Jarvis lit d'un fichier ou d'une recherche. Plus petit = réponses plus rapides.",
         {"min": 1000, "max": 50000, "step": 1000, "suffix": " caractères"}),
        ("assistant.max_history_chars", "int", "Longueur de l'historique",
         "Au-delà, les plus anciens échanges de la conversation sont oubliés.",
         {"min": 4000, "max": 200000, "step": 2000, "suffix": " caractères"}),
    ]),
    ("Voix", VOICE_NOTE, [
        ("voice.wake_word", "choice", "Mot d'activation",
         "Modèle intégré, ou chemin d'un modèle personnalisé (.onnx).",
         {"options": [("hey_jarvis", "« Hey Jarvis »"), ("alexa", "« Alexa »"), ("hey_mycroft", "« Hey Mycroft »")],
          "editable": True}),
        ("voice.wake_threshold", "float", "Exigence du mot d'activation",
         "Plus haut = moins de réveils par erreur, mais il faut parler plus distinctement.",
         {"min": 0.1, "max": 0.95, "step": 0.05}),
        ("voice.whisper_model", "choice", "Compréhension de la parole",
         "Plus gros = comprend mieux, mais met plus de temps à transcrire.",
         {"options": [("tiny", "Très rapide (tiny)"), ("base", "Rapide (base)"), ("small", "Équilibré (small)"),
                      ("medium", "Précis (medium)"), ("large-v3", "Très précis (large-v3)")]}),
        ("voice.whisper_device", "choice", "Calcul de la transcription", "Carte graphique NVIDIA = cuda.",
         {"options": [("auto", "Automatique"), ("cpu", "Processeur"), ("cuda", "Carte graphique (cuda)")]}),
        ("voice.piper_model", "file", "Voix de Jarvis (Piper)",
         "Fichier .onnx d'une voix Piper. Vide = voix du système.", {"filter": "Voix Piper (*.onnx)"}),
        ("voice.system_voice", "text", "Voix du système", "Si pas de voix Piper, ex. « Thomas ». Vide = automatique.", {}),
        ("voice.silence_seconds", "float", "Silence de fin de phrase",
         "Plus court = Jarvis répond plus vite, mais risque de te couper.",
         {"min": 0.3, "max": 3, "step": 0.1, "suffix": " s"}),
        ("voice.followup_seconds", "int", "Attente d'une suite",
         "Après une réponse, Jarvis t'écoute encore ce temps-là sans mot d'activation.",
         {"min": 0, "max": 60, "suffix": " s"}),
        ("voice.max_record_seconds", "int", "Durée max d'une phrase", "", {"min": 5, "max": 120, "suffix": " s"}),
    ]),
    ("Activation", VOICE_NOTE, [
        ("activation.modes", "multi", "Réveiller Jarvis", "",
         {"options": [("voix", "Par la voix (mot d'activation)"), ("clap", "Par claquement de mains")]}),
        ("activation.claps", "int", "Claquements nécessaires", "1 = plus réactif, mais plus de faux départs.",
         {"min": 1, "max": 4}),
        ("activation.clap_sensitivity", "float", "Sensibilité aux claquements",
         "0 = pièce bruyante, 1 = pièce calme.", {"min": 0, "max": 1, "step": 0.05}),
        ("activation.preroll_seconds", "float", "Mémoire avant le réveil",
         "Audio gardé pour capter « Jarvis, ouvre… » dit d'une traite.", {"min": 0, "max": 5, "step": 0.5, "suffix": " s"}),
    ]),
    ("Sécurité", "Toute action qui modifie quelque chose demande ta confirmation : ce n'est pas réglable, "
                 "c'est la règle d'or de Jarvis.", [
        ("security.protected_paths", "list", "Dossiers interdits",
         "Jarvis n'y écrit et n'y supprime jamais rien, même si tu confirmes. Un dossier par ligne.",
         {"folders": True}),
    ]),
    ("Fichiers", "Analyse des fichiers et recherche sur le disque.", [
        ("analysis.max_chars", "int", "Texte max lu dans un fichier", "",
         {"min": 2000, "max": 200000, "step": 1000, "suffix": " caractères"}),
        ("analysis.video_frames", "int", "Images analysées par vidéo", "Plus = description plus fine, mais plus lent.",
         {"min": 1, "max": 20}),
        ("analysis.image_max_side", "int", "Taille des images envoyées au modèle vision", "",
         {"min": 256, "max": 4096, "step": 128, "suffix": " px"}),
        ("search.max_results", "int", "Résultats max d'une recherche", "", {"min": 10, "max": 1000, "step": 10}),
        ("search.timeout_seconds", "int", "Durée max d'une recherche", "", {"min": 5, "max": 300, "suffix": " s"}),
        ("search.skip_dirs", "list", "Dossiers ignorés par la recherche", "Un nom par ligne.", {}),
    ]),
]


def get_path(cfg: dict, key: str, default=None):
    node = cfg
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def set_path(cfg: dict, key: str, value) -> None:
    *parents, last = key.split(".")
    node = cfg
    for part in parents:
        node = node.setdefault(part, {})
    node[last] = value


def _help(text: str, name: str = "help") -> QLabel:
    lab = WrapLabel(text)
    lab.setObjectName(name)
    lab.setWordWrap(True)
    return lab


class PullWorker(QThread):
    progress = Signal(str)
    finished_with = Signal(str)   # message d'erreur, vide si tout s'est bien passé

    def __init__(self, host: str, name: str):
        super().__init__()
        self.host, self.name = host, name

    def run(self):
        def report(status: str, ratio: float | None) -> None:
            self.progress.emit(f"{status} {ratio:.0%}" if ratio is not None else status)
        try:
            OllamaClient(self.host, self.name).pull(self.name, report)
            self.finished_with.emit("")
        except LLMError as e:
            self.finished_with.emit(str(e))


class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, parent=None, on_chats_cleared=None):
        super().__init__(parent)
        self.setObjectName("settings")
        self.setWindowTitle("Paramètres de Jarvis")
        self.resize(900, 640)
        self.cfg = copy.deepcopy(cfg)
        self.result_cfg: dict | None = None
        self.on_chats_cleared = on_chats_cleared
        self.fields: dict[str, tuple] = {}   # clé -> (lire, écrire)
        self.model_boxes: list[QComboBox] = []
        self.pull: PullWorker | None = None
        self.models = self._installed_models(get_path(cfg, "llm.host", "http://localhost:11434"))

        body = QHBoxLayout()
        body.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(200)
        self.pages = QStackedWidget()
        for title, intro, fields in SECTIONS:
            self._add_page(title, intro, self._build_fields(fields), top=self._ollama_bar() if title == "Cerveau" else None)
        self._add_page("Démarrage et données", "Lancement de Jarvis et conversations enregistrées.", self._build_data())
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)
        body.addWidget(self.nav)
        body.addWidget(self.pages, 1)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(16, 10, 16, 14)
        defaults = QPushButton("Valeurs par défaut")
        defaults.setObjectName("secondary")
        defaults.setToolTip("Remet les réglages d'origine dans le formulaire (rien n'est enregistré avant « Enregistrer »)")
        defaults.clicked.connect(self._load_defaults)
        cancel = QPushButton("Annuler")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Enregistrer")
        save.setObjectName("primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons.addWidget(defaults)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(save)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addLayout(body, 1)
        root.addLayout(buttons)

    # ------------------------------------------------------------ pages
    def _add_page(self, title: str, intro: str, content: QWidget, top: QWidget | None = None) -> None:
        self.nav.addItem(title)
        page = QWidget()
        page.setObjectName("settingsPage")
        v = QVBoxLayout(page)
        v.setContentsMargins(28, 22, 28, 22)
        v.setSpacing(6)
        head = QLabel(title)
        head.setObjectName("settingsTitle")
        v.addWidget(head)
        if intro:
            v.addWidget(_help(intro, "note" if intro == VOICE_NOTE or title == "Sécurité" else "settingsIntro"))
        if top:
            v.addSpacing(8)
            v.addWidget(top)
        v.addSpacing(12)
        v.addWidget(content)
        v.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        self.pages.addWidget(scroll)

    def _build_fields(self, specs: list) -> QWidget:
        box = QWidget()
        form = QFormLayout(box)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(16)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
        for key, kind, label, help_text, opts in specs:
            widget, read, write = self._make(kind, opts)
            write(get_path(self.cfg, key))
            self.fields[key] = (read, write)
            cell = QWidget()
            v = QVBoxLayout(cell)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(4)
            v.addWidget(widget)
            if help_text:
                v.addWidget(_help(help_text))
            name = WrapLabel(label)
            name.setObjectName("fieldLabel")
            name.setWordWrap(True)
            name.setFixedWidth(190)
            form.addRow(name, cell)
        return box

    def _make(self, kind: str, opts: dict):
        """Crée le champ et ses fonctions (lire la valeur, afficher une valeur)."""
        if kind == "text":
            w = QLineEdit()
            return w, lambda: w.text().strip(), lambda v: w.setText("" if v is None else str(v))
        if kind == "int":
            w = QSpinBox()
            w.setRange(opts.get("min", 0), opts.get("max", 10 ** 6))
            w.setSingleStep(opts.get("step", 1))
            w.setSuffix(opts.get("suffix", ""))
            w.setMaximumWidth(220)
            return w, w.value, lambda v: w.setValue(int(v or 0))
        if kind == "float":
            w = QDoubleSpinBox()
            w.setRange(opts.get("min", 0), opts.get("max", 100))
            w.setSingleStep(opts.get("step", 0.1))
            w.setDecimals(2)
            w.setSuffix(opts.get("suffix", ""))
            w.setMaximumWidth(220)
            return w, lambda: round(w.value(), 2), lambda v: w.setValue(float(v or 0))
        if kind == "choice":
            return self._make_choice(opts)
        if kind == "model":
            return self._make_model()
        if kind == "file":
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit()
            browse = QPushButton("Parcourir…")
            browse.setObjectName("secondary")

            def pick():
                path, _ = QFileDialog.getOpenFileName(self, "Choisir un fichier", edit.text() or str(Path.home()),
                                                      opts.get("filter", ""))
                if path:
                    edit.setText(path)

            browse.clicked.connect(pick)
            h.addWidget(edit, 1)
            h.addWidget(browse)
            return row, lambda: edit.text().strip(), lambda v: edit.setText(v or "")
        if kind == "list":
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(0, 0, 0, 0)
            edit = QPlainTextEdit()
            edit.setObjectName("listEdit")
            edit.setFixedHeight(150)
            v.addWidget(edit)
            if opts.get("folders"):
                add = QPushButton("Ajouter un dossier…")
                add.setObjectName("secondary")

                def add_folder():
                    path = QFileDialog.getExistingDirectory(self, "Choisir un dossier", str(Path.home()))
                    if path:
                        edit.appendPlainText(path)

                add.clicked.connect(add_folder)
                v.addWidget(add, 0, Qt.AlignLeft)
            return (w, lambda: [line.strip() for line in edit.toPlainText().splitlines() if line.strip()],
                    lambda val: edit.setPlainText("\n".join(str(x) for x in (val or []))))
        if kind == "multi":
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(0, 0, 0, 0)
            boxes = []
            for value, text in opts["options"]:
                cb = QCheckBox(text)
                v.addWidget(cb)
                boxes.append((value, cb))

            def write(val):
                for value, cb in boxes:
                    cb.setChecked(value in (val or []))

            return w, lambda: [value for value, cb in boxes if cb.isChecked()], write
        raise ValueError(kind)

    def _make_choice(self, opts: dict):
        w = QComboBox()
        w.setEditable(opts.get("editable", False))
        w.setMinimumWidth(260)
        for value, text in opts["options"]:
            w.addItem(text, value)

        def read():
            i = w.currentIndex()
            if w.isEditable() and (i < 0 or w.currentText() != w.itemText(i)):
                return w.currentText().strip()       # valeur tapée à la main
            return w.itemData(i)

        def write(v):
            i = w.findData(v)
            if i < 0:                                 # valeur hors liste (réglée à la main dans le fichier)
                w.addItem(str(v), v)
                i = w.count() - 1
            w.setCurrentIndex(i)

        return w, read, write

    def _make_model(self):
        row = QWidget()
        v = QVBoxLayout(row)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        h = QHBoxLayout()
        combo = QComboBox()
        combo.setEditable(True)
        combo.setMinimumWidth(260)
        combo.addItems(self.models)
        self.model_boxes.append(combo)
        download = QPushButton("Télécharger")
        download.setObjectName("secondary")
        # Mise en page fixe : l'avertissement garde sa ligne, le bouton reste en place (grisé si inutile).
        # Faire apparaître des éléments après coup écrase les champs voisins dans un formulaire Qt.
        warn = QLabel(" ")
        warn.setObjectName("warn")

        def check(text: str):
            name = text.strip()
            missing = bool(name) and self.models is not None and name not in self.models \
                and f"{name}:latest" not in self.models
            warn.setText(f"⚠ « {name} » n'est pas installé : clique sur Télécharger." if missing else " ")
            download.setEnabled(missing)
            download.setToolTip("Télécharge ce modèle avec Ollama (plusieurs Go)" if missing else "Déjà installé")

        combo.currentTextChanged.connect(check)
        download.clicked.connect(lambda: self._pull(combo.currentText().strip()))
        h.addWidget(combo, 1)
        h.addWidget(download)
        v.addLayout(h)
        v.addWidget(warn)

        def write(value):
            combo.setEditText(value or "")
            check(value or "")

        return row, lambda: combo.currentText().strip(), write

    # ------------------------------------------------------------ Ollama
    @staticmethod
    def _installed_models(host: str) -> list[str] | None:
        try:
            return sorted(OllamaClient(host, "").installed_models())
        except Exception:
            return None

    def _ollama_bar(self) -> QWidget:
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        self.ollama_status = _help("")
        test = QPushButton("Tester la connexion")
        test.setObjectName("secondary")
        test.clicked.connect(self._refresh_models)
        h.addWidget(self.ollama_status, 1)
        h.addWidget(test)
        self._show_ollama_status()
        return bar

    def _show_ollama_status(self) -> None:
        if self.models is None:
            self.ollama_status.setText("● Ollama ne répond pas à cette adresse.")
            self.ollama_status.setObjectName("warn")
        else:
            n = len(self.models)
            self.ollama_status.setText(f"● Ollama connecté — {n} modèle{'s' if n > 1 else ''} installé{'s' if n > 1 else ''}")
            self.ollama_status.setObjectName("ok")
        self.ollama_status.style().unpolish(self.ollama_status)
        self.ollama_status.style().polish(self.ollama_status)

    def _refresh_models(self) -> None:
        self.models = self._installed_models(self.fields["llm.host"][0]())
        for combo in self.model_boxes:
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(self.models or [])
            combo.blockSignals(False)
            combo.setEditText(current)
            combo.currentTextChanged.emit(current)
        self._show_ollama_status()

    def _pull(self, name: str) -> None:
        if not name or (self.pull and self.pull.isRunning()):
            return
        self.pull = PullWorker(self.fields["llm.host"][0](), name)
        self.pull.progress.connect(lambda text: self.ollama_status.setText(f"⬇ {name} : {text}"))
        self.pull.finished_with.connect(lambda err: self._pulled(name, err))
        self.ollama_status.setText(f"⬇ {name} : démarrage…")
        self.pull.start()

    def _pulled(self, name: str, error: str) -> None:
        self._refresh_models()
        if error:
            QMessageBox.warning(self, "Téléchargement", f"Impossible de télécharger {name} :\n{error}")

    # ------------------------------------------------------------ démarrage et données
    def _build_data(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        self.autostart_box = QCheckBox("Lancer Jarvis (voix) à l'ouverture de session")
        self.autostart_box.setChecked(autostart.enabled())
        self.autostart_box.setEnabled(autostart.available())
        v.addWidget(self.autostart_box)
        if not autostart.available():
            v.addWidget(_help("Disponible après une installation avec l'installateur."))
        v.addSpacing(18)

        data_dir = ctx.cfg.get("data_dir", "")
        v.addWidget(_help(f"Configuration, historique et journal : {data_dir}"))
        row = QHBoxLayout()
        open_dir = QPushButton("Ouvrir le dossier")
        open_dir.setObjectName("secondary")
        open_dir.clicked.connect(lambda: ctx.os.open_file(Path(data_dir)))
        clear = QPushButton("Effacer toutes les conversations")
        clear.setObjectName("danger")
        clear.clicked.connect(self._clear_chats)
        row.addWidget(open_dir)
        row.addWidget(clear)
        row.addStretch()
        v.addLayout(row)
        return box

    def _clear_chats(self) -> None:
        if QMessageBox.question(self, "Effacer", "Effacer définitivement toutes les conversations enregistrées ?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        ctx.memory.delete_all_chats()
        if self.on_chats_cleared:
            self.on_chats_cleared()

    # ------------------------------------------------------------ enregistrement
    def _load_defaults(self) -> None:
        defaults = load_config(str(DEFAULT_CONFIG))
        for key, (_, write) in self.fields.items():
            write(get_path(defaults, key))

    def _save(self) -> None:
        new = copy.deepcopy(self.cfg)
        for key, (read, _) in self.fields.items():
            set_path(new, key, read())
        if not new["activation"]["modes"]:
            QMessageBox.warning(self, "Activation", "Choisis au moins une façon de réveiller Jarvis.")
            return
        if not new["llm"]["model"]:
            QMessageBox.warning(self, "Cerveau", "Choisis un modèle principal.")
            return
        if self.autostart_box.isEnabled() and self.autostart_box.isChecked() != autostart.enabled():
            try:
                autostart.set_enabled(self.autostart_box.isChecked())
            except OSError as e:
                QMessageBox.warning(self, "Lancement automatique", f"Impossible de modifier le réglage :\n{e}")
        self.result_cfg = new
        self.accept()
