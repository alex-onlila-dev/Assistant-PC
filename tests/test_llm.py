"""Les trois cerveaux : choix automatique, traduction de l'historique, lecture des réponses."""
import json

import jarvis.tools  # noqa: F401  (enregistre les outils)
from jarvis.core import llm as llm_mod
from jarvis.core.agent import Agent
from jarvis.core.confirmation import AutoConfirmer
from jarvis.core.llm import LLMError, OllamaClient, create_llm, resolve_provider
from jarvis.core.llm.claude import ClaudeClient, from_claude, to_claude
from jarvis.core.llm.openai_compat import OpenAICompatClient, read_sse, to_openai
from jarvis.core.tools import registry

SYSTEM = {"role": "system", "content": "Consignes"}
CALL = {"role": "assistant", "content": "",
        "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "a.txt"}}},
                       {"function": {"name": "file_info", "arguments": '{"path": "b.txt"}'}}]}
RESULTS = [{"role": "tool", "tool_name": "read_file", "content": '{"statut": "ok", "resultat": "x"}'},
           {"role": "tool", "tool_name": "file_info", "content": '{"statut": "erreur", "message": "absent"}'}]
HISTORY = [SYSTEM, {"role": "user", "content": "Lis a et b"}, CALL, *RESULTS,
           {"role": "assistant", "content": "a contient x, b n'existe pas."}]


# ---------------------------------------------------------------- choix du cerveau
def test_auto_prefers_ollama_then_claude_then_openai(config, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    installed = {"ollama": True}
    monkeypatch.setattr(OllamaClient, "installed", staticmethod(lambda host="": installed["ollama"]))
    assert config["llm"]["provider"] == "auto"
    assert resolve_provider(config) == "ollama"

    installed["ollama"] = False
    config["llm"]["openai"]["api_key"] = "sk-autre"
    assert resolve_provider(config) == "openai"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert resolve_provider(config) == "claude"

    config["llm"]["provider"] = "ollama"            # un choix explicite l'emporte toujours
    assert resolve_provider(config) == "ollama"


def test_create_llm_builds_each_provider(config, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config["llm"]["provider"] = "claude"
    config["llm"]["claude"]["api_key"] = "sk-ant-test"
    claude = create_llm(config)
    assert isinstance(claude, ClaudeClient) and claude.model == "claude-opus-5-5" and claude.ensure_running()

    config["llm"]["provider"] = "openai"
    config["llm"]["openai"].update(base_url="https://api.mistral.ai/v1/", model="mistral-small")
    other = create_llm(config)
    assert isinstance(other, OpenAICompatClient) and other.label == "Mistral" and other.ensure_running()

    config["llm"]["openai"]["model"] = ""
    assert not create_llm(config).ensure_running()  # pas de modèle : on explique quoi faire au lieu de planter
    assert "modèle" in create_llm(config).setup_hint


def test_claude_without_key_explains_what_to_do(config, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("HOME", "/nonexistent")       # aucun profil « ant auth login »
    monkeypatch.setenv("USERPROFILE", "/nonexistent")
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", "/nonexistent")
    client = ClaudeClient(api_key="")
    assert not client.ensure_running()                # le SDK ne le dirait qu'à la première question
    assert "clé API" in client.setup_hint
    try:
        client.chat([{"role": "user", "content": "x"}])
    except LLMError as e:                             # une erreur que la boucle agent sait annoncer
        assert "clé API" in str(e)
    else:
        raise AssertionError("chat() aurait dû échouer")


# ---------------------------------------------------------------- Claude
def test_history_to_claude_pairs_results_with_calls():
    system, msgs = to_claude(HISTORY)
    assert system == "Consignes"
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    uses = msgs[1]["content"]
    assert [b["type"] for b in uses] == ["tool_use", "tool_use"]
    assert uses[1]["input"] == {"path": "b.txt"}           # arguments en texte JSON -> objet
    results = msgs[2]["content"]                            # résultats des deux outils dans un seul message
    assert [r["tool_use_id"] for r in results] == [u["id"] for u in uses]
    assert "is_error" not in results[0] and results[1]["is_error"] is True


def test_claude_reply_is_replayed_verbatim():
    blocks = [{"type": "thinking", "thinking": "", "signature": "sig"},
              {"type": "text", "text": "Je regarde."},
              {"type": "tool_use", "id": "toolu_1", "name": "read_file", "input": {"path": "a.txt"}}]
    msg = from_claude(blocks, "tool_use")
    assert msg["content"] == "Je regarde."
    assert msg["tool_calls"] == [{"id": "toolu_1", "function": {"name": "read_file", "arguments": {"path": "a.txt"}}}]
    history = [SYSTEM, {"role": "user", "content": "Lis a"}, msg,
               {"role": "tool", "tool_call_id": "toolu_1", "content": "{}"}]
    _, msgs = to_claude(history)
    assert msgs[1]["content"] == blocks                     # réflexion signée comprise, à l'identique
    assert msgs[2]["content"][0]["tool_use_id"] == "toolu_1"


def test_claude_fallback_drops_what_the_first_model_prepared():
    blocks = [{"type": "thinking", "thinking": "", "signature": "s1"},
              {"type": "text", "text": "Je "},
              {"type": "tool_use", "id": "abandonne", "name": "read_file", "input": {}},
              {"type": "fallback", "from": {"model": "a"}, "to": {"model": "b"}},
              {"type": "text", "text": "reprends."}]
    msg = from_claude(blocks, "end_turn")
    kept = msg["native"]["content"]
    assert [b["type"] for b in kept] == ["text", "fallback", "text"]
    assert msg["content"] == "Je reprends." and "tool_calls" not in msg


def test_claude_truncated_tool_call_is_not_run():
    msg = from_claude([{"type": "tool_use", "id": "t", "name": "create_file", "input": {"path": "x"}}], "max_tokens")
    assert "tool_calls" not in msg and "native" not in msg
    assert "refusé" in from_claude([], "refusal")["content"]


# ---------------------------------------------------------------- services compatibles OpenAI
def test_history_to_openai():
    msgs = to_openai(HISTORY + [{"role": "user", "content": "Et ça ?", "images": ["QUJD"]}])
    assert msgs[0] == {"role": "system", "content": "Consignes"}
    calls = msgs[2]["tool_calls"]
    assert json.loads(calls[0]["function"]["arguments"]) == {"path": "a.txt"}
    assert [m["tool_call_id"] for m in msgs[3:5]] == [c["id"] for c in calls]
    assert msgs[-1]["content"][1]["image_url"]["url"] == "data:image/jpeg;base64,QUJD"


def test_openai_stream_assembles_text_and_tool_calls():
    pieces = []
    lines = [
        'data: {"choices":[{"delta":{"content":"Bon"}}]}',
        'data: {"choices":[{"delta":{"content":"jour"}}]}',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"read_file","arguments":"{\\"pa"}}]}}]}',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"th\\": \\"a\\"}"}}]}}]}',
        ": commentaire ignoré",
        "data: [DONE]",
    ]
    msg = read_sse(lines, pieces.append)
    assert pieces == ["Bon", "jour"] and msg["content"] == "Bonjour"
    assert msg["tool_calls"] == [{"id": "c1", "function": {"name": "read_file", "arguments": '{"path": "a"}'}}]


# ---------------------------------------------------------------- boucle agent
class ScriptedLLM:
    nudge = False

    def __init__(self, steps):
        self.steps, self.seen = list(steps), []

    def chat(self, messages, tools=None, model=None):
        self.seen.append(list(messages))
        return self.steps.pop(0)


def test_agent_keeps_ids_and_native_reply(tmp_path, config):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    native = {"provider": "claude", "content": [{"type": "text", "text": "…"}]}
    llm = ScriptedLLM([
        {"role": "assistant", "content": "", "native": native,
         "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": str(f)}}}]},
        {"role": "assistant", "content": "Il contient x. Avec read_file."},   # pas de relance : nudge = False
    ])
    agent = Agent(llm=llm, registry=registry, confirmer=AutoConfirmer(False), cfg=config)
    assert agent.run("lis a") == "Il contient x. Avec read_file."
    call, result = agent.history[2], agent.history[3]
    assert call["native"] == native and call["tool_calls"][0]["id"]
    assert result["tool_call_id"] == call["tool_calls"][0]["id"]


def test_ollama_does_not_receive_other_brains_replies(monkeypatch):
    sent = {}

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"role": "assistant", "content": "ok"}}

    monkeypatch.setattr(llm_mod.ollama.httpx, "post", lambda url, json, timeout: sent.update(json) or Resp())
    OllamaClient("http://localhost:11434", "m").chat(
        [{"role": "assistant", "content": "a", "native": {"provider": "claude", "content": []}}])
    assert sent["messages"] == [{"role": "assistant", "content": "a"}]
