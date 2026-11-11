import zipfile
from datetime import datetime

from jarvis.analyzers import analyze, detect_kind
from jarvis.core.alarms import parse_when
from jarvis.core.confirmation import parse_yes_no
from jarvis.os_adapters import get_adapter
from jarvis.os_adapters.base import OSAdapter


def test_yes_no():
    assert parse_yes_no("Oui vas-y") is True
    assert parse_yes_no("ok") is True
    assert parse_yes_no("non, annule") is False
    assert parse_yes_no("oui... euh non") is False   # le non l'emporte
    assert parse_yes_no("peut-être") is None
    assert parse_yes_no("") is None


def test_parse_when():
    t = parse_when("7h30")
    assert (t.hour, t.minute) == (7, 30) and t > datetime.now()
    assert parse_when("2030-01-02T08:15") == datetime(2030, 1, 2, 8, 15)


def test_adapter_and_app_matching():
    assert isinstance(get_adapter(), OSAdapter)
    apps = {"Google Chrome": "a", "Visual Studio Code": "b", "Calculatrice": "c"}
    assert OSAdapter.find_app("chrome", apps) == "Google Chrome"
    assert OSAdapter.find_app("visual studio", apps) == "Visual Studio Code"
    assert OSAdapter.find_app("calculatrise", apps) == "Calculatrice"
    assert OSAdapter.find_app("photoshop", apps) is None


def test_detect_and_analyze(tmp_path):
    code = tmp_path / "app.py"
    code.write_text("print('salut')\n", encoding="utf-8")
    assert detect_kind(code) == "texte"
    assert "salut" in analyze(code)["contenu"]

    archive = tmp_path / "pack.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("dossier/doc.txt", "abc")
    result = analyze(archive)
    assert result["type"] == "archive" and result["nombre_elements"] == 1

    mystery = tmp_path / "sans_extension"
    mystery.write_bytes(b"\x00\x01\x02binaire")
    assert detect_kind(mystery) == "binaire"


def test_chats_are_saved_and_reloaded(tmp_path):
    from jarvis.core.memory import Memory
    mem = Memory(str(tmp_path))
    history = [{"role": "user", "content": "salut"},
               {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "get_datetime"}}]}]
    chat_id = mem.save_chat(None, "Salut", history)
    mem.save_chat(chat_id, "Salut !", history + [{"role": "assistant", "content": "Bonjour"}])
    assert [c["title"] for c in mem.list_chats()] == ["Salut !"]
    title, loaded = mem.load_chat(chat_id)
    assert title == "Salut !" and loaded[-1]["content"] == "Bonjour"
    mem.delete_chat(chat_id)
    assert mem.list_chats() == []


def test_user_config_is_completed_by_defaults_and_saved(tmp_path, monkeypatch):
    import yaml
    import jarvis.config as config
    user = tmp_path / "config.yaml"
    user.write_text("llm:\n  model: mon-modele\n", encoding="utf-8")   # vieille config : réglages manquants
    monkeypatch.setattr(config, "USER_CONFIG", user)
    cfg = config.load_config()
    assert cfg["llm"]["model"] == "mon-modele"
    assert cfg["llm"]["host"] == "http://localhost:11434"     # complété par les valeurs par défaut
    assert cfg["interface"]["theme"] == "auto"

    cfg["assistant"]["max_steps"] = 7
    config.save_config(cfg)
    saved = yaml.safe_load(user.read_text(encoding="utf-8"))
    assert saved["assistant"]["max_steps"] == 7 and "data_dir" not in saved
    assert (tmp_path / "config.yaml.bak").read_text(encoding="utf-8").startswith("llm:")
    assert config.load_config()["assistant"]["max_steps"] == 7


def test_installer_brain_choice_is_saved_and_key_file_erased(tmp_path, monkeypatch):
    import yaml
    import jarvis.config as config
    from jarvis import setup_brain
    user = tmp_path / "config.yaml"
    user.write_text("llm:\n  model: qwen2.5:3b\n", encoding="utf-8")
    monkeypatch.setattr(config, "USER_CONFIG", user)
    monkeypatch.setattr(setup_brain, "USER_CONFIG", user)
    monkeypatch.setattr(setup_brain, "load_config", config.load_config)
    monkeypatch.setattr(setup_brain, "save_config", config.save_config)
    key_file = tmp_path / "cle.txt"
    key_file.write_text("sk-ant-secret\n", encoding="utf-8")
    monkeypatch.setenv("JARVIS_BRAIN", "claude")
    monkeypatch.setenv("JARVIS_API_KEY_FILE", str(key_file))
    assert setup_brain.main() == 0
    saved = yaml.safe_load(user.read_text(encoding="utf-8"))["llm"]
    assert saved["provider"] == "claude" and saved["claude"]["api_key"] == "sk-ant-secret"
    assert saved["claude"]["model"] == "claude-opus-5-5" and saved["model"] == "qwen2.5:3b"   # le reste est gardé
    assert not key_file.exists()

    cfg = setup_brain.apply({"llm": {}}, "openai", "k", "https://api.mistral.ai/v1/", "mistral-small")
    assert cfg["llm"]["openai"] == {"api_key": "k", "base_url": "https://api.mistral.ai/v1", "model": "mistral-small"}
    monkeypatch.setenv("JARVIS_BRAIN", "gpt")
    assert setup_brain.main() == 2


def test_autostart_follows_installed_menu_entry(tmp_path, monkeypatch):
    import sys
    from jarvis import autostart
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert not autostart.available()
    entry = tmp_path / "data/applications/jarvis.desktop"
    entry.parent.mkdir(parents=True)
    entry.write_text("[Desktop Entry]\nName=Jarvis (voix)\n")
    assert autostart.available() and not autostart.enabled()
    autostart.set_enabled(True)
    assert (tmp_path / "config/autostart/jarvis.desktop").read_text() == entry.read_text()
    autostart.set_enabled(False)
    assert not autostart.enabled()
