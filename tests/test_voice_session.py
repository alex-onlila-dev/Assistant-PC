"""Conversation vocale : fin de conversation, découpage des phrases, réponse en continu."""
import json

from jarvis.core.llm import _read_stream
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
