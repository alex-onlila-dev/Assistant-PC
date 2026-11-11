"""Conversation vocale : fin de conversation, découpage des phrases, réponse en continu."""
import json

from jarvis.core.llm.ollama import _read_stream
from jarvis.voice.session import is_end_of_conversation, is_quit_command
from jarvis.voice.tts import split_sentences


def test_end_of_conversation_phrases():
    for t in ["C'est tout.", "On s'arrête là", "c'est bon", "Non merci, c'est tout Jarvis", "Merci beaucoup !",
              "Ok c'est bon merci", "Ce sera tout pour l'instant", "Au revoir", "c'est terminé"]:
        assert is_end_of_conversation(t), t


def test_real_requests_keep_the_conversation_going():
    for t in ["C'est bon, maintenant ouvre Chrome", "Merci, et quelle heure est-il ?",
              "Cherche le fichier c'est tout.docx dans mes documents", "Rien de grave, lis mes notes",
              "Ouvre les paramètres Bluetooth"]:
        assert not is_end_of_conversation(t), t


def test_quit_only_when_whole_sentence():
    assert is_quit_command("Éteins-toi !")
    assert is_quit_command("quitte")
    assert not is_quit_command("quitte l'application Spotify")
    assert not is_quit_command("au revoir")      # au revoir = fin de conversation, Jarvis reste en veille


def test_split_sentences_keeps_unfinished_part():
    ready, rest = split_sentences("Il est dix heures et quart. Tu as une réunion à onze")
    assert ready == ["Il est dix heures et quart."]
    assert rest == "Tu as une réunion à onze"


def test_split_sentences_groups_tiny_sentences():
    ready, rest = split_sentences("Oui. D'accord. Je lance le minuteur de cinq minutes. ")
    assert ready == ["Oui. D'accord. Je lance le minuteur de cinq minutes."]
    assert rest == ""


def test_stream_assembles_text_and_tool_calls():
    lines = [json.dumps({"message": {"content": "Je "}}), json.dumps({"message": {"content": "regarde."}}),
             json.dumps({"message": {"content": "", "tool_calls": [{"function": {"name": "system_info",
                                                                                  "arguments": {}}}]}}),
             json.dumps({"done": True, "message": {"content": ""}})]
    pieces = []
    msg = _read_stream(lines, pieces.append)
    assert pieces == ["Je ", "regarde."]
    assert msg["content"] == "Je regarde."
    assert msg["tool_calls"][0]["function"]["name"] == "system_info"


def test_voice_session_picks_up_brain_chosen_in_settings(tmp_path, monkeypatch, config):
    """La fenêtre Paramètres est un autre programme : le mode vocal relit le cerveau à chaque conversation."""
    import jarvis.config as jconfig
    import jarvis.voice.session as session_mod
    from jarvis.core.llm.claude import ClaudeClient
    from jarvis.voice.session import VoiceSession

    user = tmp_path / "config.yaml"
    monkeypatch.setattr(jconfig, "USER_CONFIG", user)
    monkeypatch.setattr(session_mod, "USER_CONFIG", user)
    monkeypatch.setattr(session_mod, "load_config", jconfig.load_config)
    s = object.__new__(VoiceSession)          # sans micro ni modèles : seulement ce qui sert ici
    s.cfg, s.agent, s._config_mtime = config, type("A", (), {"llm": None})(), 0.0

    s._refresh_brain()
    assert s.agent.llm is None                # pas de config utilisateur : rien ne change
    user.write_text("llm:\n  provider: claude\n  claude:\n    api_key: sk-ant-test\n", encoding="utf-8")
    s._refresh_brain()
    assert isinstance(s.agent.llm, ClaudeClient) and s.agent.llm.ensure_running()
    first = s.agent.llm
    s._refresh_brain()
    assert s.agent.llm is first               # fichier inchangé : on garde le même cerveau
