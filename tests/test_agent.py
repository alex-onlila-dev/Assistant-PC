"""Vérifie la règle d'or : rien ne se modifie sans confirmation."""
import jarvis.tools  # noqa: F401  (enregistre les outils)
import jarvis.tools.files as files_mod
from jarvis.core.agent import Agent
from jarvis.core.confirmation import AutoConfirmer
from jarvis.core.tools import registry


class FakeLLM:
    """Cerveau factice : rejoue un scénario d'appels d'outils."""

    def __init__(self, steps):
        self.steps = list(steps)

    def chat(self, messages, tools=None, model=None):
        return self.steps.pop(0)


def call(name, **args):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}


def reply(text):
    return {"role": "assistant", "content": text}


def make_agent(llm, allow, cfg):
    confirmer = AutoConfirmer(allow)
    return Agent(llm=llm, registry=registry, confirmer=confirmer, cfg=cfg), confirmer


def test_read_needs_no_confirmation(tmp_path, config):
    f = tmp_path / "note.txt"
    f.write_text("bonjour", encoding="utf-8")
    agent, conf = make_agent(FakeLLM([call("read_file", path=str(f)), reply("Il contient bonjour.")]), False, config)
    assert agent.run("lis la note") == "Il contient bonjour."
    assert conf.asked == []
    assert "bonjour" in agent.history[-2]["content"]


def test_delete_refused_keeps_file(tmp_path, config):
    f = tmp_path / "a_garder.txt"
    f.write_text("x")
    agent, conf = make_agent(FakeLLM([call("delete_file", path=str(f)), reply("Annulé.")]), False, config)
    agent.run("supprime le fichier")
    assert f.exists()
    assert len(conf.asked) == 1 and "corbeille" in conf.asked[0]
    assert "annulé" in agent.history[-2]["content"]


def test_delete_confirmed_goes_to_trash(tmp_path, config, monkeypatch):
    trashed = []
    monkeypatch.setattr(files_mod, "send2trash", lambda p: trashed.append(p))
    f = tmp_path / "a_jeter.txt"
    f.write_text("x")
    agent, _ = make_agent(FakeLLM([call("delete_file", path=str(f)), reply("Fait.")]), True, config)
    agent.run("supprime le fichier")
    assert trashed == [str(f.resolve())]


def test_create_file_confirmed(tmp_path, config):
    target = tmp_path / "nouveau" / "idee.md"
    agent, conf = make_agent(FakeLLM([call("create_file", path=str(target), content="# Idée"), reply("Créé.")]),
                             True, config)
    agent.run("crée un fichier")
    assert target.read_text(encoding="utf-8") == "# Idée"
    assert "Créer le fichier" in conf.asked[0]


def test_protected_path_blocked_even_if_confirmed(config):
    config["security"]["protected_paths"] = ["/etc"]
    agent, _ = make_agent(FakeLLM([call("delete_file", path="/etc/hosts"), reply("Refusé.")]), True, config)
    agent.run("supprime /etc/hosts")
    assert "Dossier protégé" in agent.history[-2]["content"]


def test_unknown_tool(config):
    agent, _ = make_agent(FakeLLM([call("hack_the_planet"), reply("ok")]), True, config)
    agent.run("?")
    assert "Outil inconnu" in agent.history[-2]["content"]


def test_copy_never_overwrites(tmp_path, config):
    src, dst = tmp_path / "a.txt", tmp_path / "b.txt"
    src.write_text("nouveau")
    dst.write_text("précieux")
    agent, _ = make_agent(FakeLLM([call("copy_file", source=str(src), destination=str(dst)), reply("ok")]),
                          True, config)
    agent.run("copie a sur b")
    assert dst.read_text() == "précieux"
    assert "existe déjà" in agent.history[-2]["content"]


def test_copy_into_directory(tmp_path, config):
    src, folder = tmp_path / "a.txt", tmp_path / "dossier"
    src.write_text("x")
    folder.mkdir()
    (folder / "a.txt").write_text("déjà là")
    agent, _ = make_agent(FakeLLM([call("copy_file", source=str(src), destination=str(folder)), reply("ok")]),
                          True, config)
    agent.run("copie a dans dossier")
    assert (folder / "a.txt").read_text() == "déjà là"


def test_confirmation_shows_real_path_and_content(tmp_path, config, monkeypatch):
    monkeypatch.setattr(files_mod.Path, "home", lambda: tmp_path)
    import jarvis.tools._paths as paths_mod
    monkeypatch.setattr(paths_mod.Path, "home", lambda: tmp_path)
    agent, conf = make_agent(FakeLLM([call("create_file", path="notes.txt", content="ligne secrète"),
                                      reply("Annulé.")]), False, config)
    agent.run("crée notes.txt")
    assert str((tmp_path / "notes.txt").resolve()) in conf.asked[0]
    assert "ligne secrète" in conf.asked[0]


def test_history_is_trimmed_but_keeps_system_and_current_turn(config):
    config["assistant"]["max_history_chars"] = 1000
    agent, _ = make_agent(FakeLLM([reply("a" * 600), reply("b" * 600), reply("c")]), True, config)
    agent.run("première")
    agent.run("deuxième")
    agent.run("troisième")
    assert agent.history[0]["role"] == "system"
    contents = [m["content"] for m in agent.history]
    assert "première" not in contents
    assert "troisième" in contents and "c" in contents


def test_answer_is_streamed_to_on_delta(config):
    class StreamLLM:
        def chat(self, messages, tools=None, model=None, on_delta=None):
            for piece in ("Il est ", "midi."):
                on_delta(piece)
            return reply("Il est midi.")

    agent, _ = make_agent(StreamLLM(), True, config)
    pieces = []
    assert agent.run("quelle heure ?", on_delta=pieces.append) == "Il est midi."
    assert pieces == ["Il est ", "midi."]


def test_voice_mode_asks_for_short_answers(config):
    from jarvis.core.agent import Agent
    agent = Agent(llm=None, registry=registry, confirmer=AutoConfirmer(True), cfg=config, voice=True)
    assert "Mode vocal" in agent.history[0]["content"]


def test_stop_keeps_partial_answer_in_history(config):
    class StreamLLM:
        def chat(self, messages, tools=None, model=None, on_delta=None):
            on_delta("Voici ")
            agent.cancel()            # l'utilisateur clique sur « Arrêter » pendant la réponse
            on_delta("la suite")
            return reply("Voici la suite")

    agent, _ = make_agent(StreamLLM(), True, config)
    assert agent.run("raconte", on_delta=lambda p: None) == "Voici "
    assert agent.history[-1] == {"role": "assistant", "content": "Voici [interrompu]"}


def test_load_restores_conversation_with_fresh_system_prompt(config):
    agent, _ = make_agent(FakeLLM([]), True, config)
    agent.load([{"role": "system", "content": "vieux"}, {"role": "user", "content": "a"},
                {"role": "assistant", "content": "b"}])
    assert agent.history[0]["role"] == "system" and agent.history[0]["content"] != "vieux"
    assert [m["content"] for m in agent.history[1:]] == ["a", "b"]


def test_tool_call_written_as_text_is_retried(config):
    llm = FakeLLM([reply("Voici comment procéder :\n\n```json\n"),       # appel avalé par Ollama
                   call("get_datetime"), reply("Il est midi.")])
    agent, _ = make_agent(llm, True, config)
    events = []
    agent.on_event = lambda kind, data: events.append(kind)
    assert agent.run("quelle heure ?") == "Il est midi."
    assert events[0] == "retry" and "tool_start" in events


def test_retry_happens_only_once(config):
    llm = FakeLLM([reply("Lance search_files toi-même."), reply("Utilise search_files.")])
    agent, _ = make_agent(llm, True, config)
    assert agent.run("cherche") == "Utilise search_files."


def test_search_finds_git_folders_without_entering_them(config, tmp_path):
    for name in ("projet-a", "projet-b"):
        (tmp_path / name / ".git" / "objects").mkdir(parents=True)
        (tmp_path / name / ".gitignore").write_text("")
    found = files_mod.search_files(".git", root=str(tmp_path), exact=True)["resultats"]
    assert sorted(found) == [str(tmp_path / "projet-a" / ".git"), str(tmp_path / "projet-b" / ".git")]
