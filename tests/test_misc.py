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
