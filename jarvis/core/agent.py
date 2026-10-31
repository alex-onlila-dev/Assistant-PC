"""La boucle agent : penser -> agir -> observer -> recommencer."""
import json
from typing import Callable

from jarvis.core.confirmation import Confirmer
from jarvis.core.llm import LLMError, OllamaClient
from jarvis.core.prompts import build_system_prompt
from jarvis.core.tools import ToolRegistry

EventCallback = Callable[[str, dict], None]


class Agent:
    def __init__(self, llm: OllamaClient, registry: ToolRegistry, confirmer: Confirmer,
                 cfg: dict, memory=None, on_event: EventCallback | None = None, voice: bool = False):
        self.llm = llm
        self.voice = voice
        self.registry = registry
        self.confirmer = confirmer
        self.cfg = cfg
        self.memory = memory
        self.on_event = on_event or (lambda kind, data: None)
        a = cfg.get("assistant", {})
        self.max_steps = a.get("max_steps", 15)
        self.max_output = a.get("max_tool_output", 12000)
        self.max_history = a.get("max_history_chars", 40000)
        self.history: list[dict] = []
        self.reset()

    def reset(self) -> None:
        self.history = [{"role": "system", "content": build_system_prompt(self.cfg, voice=self.voice)}]

    def warm_up(self) -> None:
        """Fait lire au cerveau ses consignes et ses outils dès le démarrage.

        Ollama garde en cache le début de conversation déjà lu : la première vraie question n'a plus
        à relire ces milliers de mots (sinon plusieurs dizaines de secondes sur une petite machine).
        """
        try:
            self.llm.chat(self.history + [{"role": "user", "content": "Bonjour"}],
                          tools=self.registry.schemas(), options={"num_predict": 1})
        except LLMError:
            pass

    # ------------------------------------------------------------------
    def run(self, user_text: str, on_delta: Callable[[str], None] | None = None) -> str:
        """on_delta reçoit le texte de la réponse au fur et à mesure (pour parler sans attendre la fin)."""
        self.history.append({"role": "user", "content": user_text})
        self._log("user", user_text)

        for _ in range(self.max_steps):
            self._trim()
            try:
                if on_delta:
                    msg = self.llm.chat(self.history, tools=self.registry.schemas(), on_delta=on_delta)
                else:
                    msg = self.llm.chat(self.history, tools=self.registry.schemas())
            except LLMError as e:
                return f"Problème avec le cerveau local : {e}"

            calls = msg.get("tool_calls") or []
            self.history.append({"role": "assistant", "content": msg.get("content", ""),
                                 **({"tool_calls": calls} if calls else {})})

            if not calls:
                answer = msg.get("content", "").strip()
                self._log("assistant", answer)
                return answer

            for call in calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                result = self._execute(name, args)
                self.history.append({"role": "tool", "tool_name": name, "content": result})

        return "J'ai atteint la limite d'étapes sans terminer. Reformule ou découpe la demande."

    # ------------------------------------------------------------------
    def _execute(self, name: str, args: dict) -> str:
        tool = self.registry.get(name)
        if tool is None:
            return json.dumps({"erreur": f"Outil inconnu : {name}"}, ensure_ascii=False)

        if tool.confirm:
            action = tool.describe(args)
            self.on_event("confirm_request", {"tool": name, "action": action})
            if not self.confirmer.ask(action):
                self.on_event("cancelled", {"tool": name})
                return json.dumps({"statut": "annulé par l'utilisateur"}, ensure_ascii=False)

        self.on_event("tool_start", {"tool": name, "args": args})
        try:
            result = tool.func(**args)
            payload = {"statut": "ok", "resultat": result}
        except TypeError as e:
            payload = {"statut": "erreur", "message": f"Arguments invalides : {e}"}
        except Exception as e:  # l'erreur est renvoyée au cerveau pour qu'il s'adapte
            payload = {"statut": "erreur", "message": f"{type(e).__name__}: {e}"}

        text = json.dumps(payload, ensure_ascii=False, default=str)
        if len(text) > self.max_output:
            text = text[: self.max_output] + '… [tronqué]"}'
        self.on_event("tool_result", {"tool": name, "result": payload})
        return text

    def _trim(self) -> None:
        """Oublie les plus anciens échanges quand l'historique dépasse max_history_chars.

        Les consignes système et l'échange en cours sont toujours gardés : sinon Ollama tronquerait
        lui-même le début de la conversation, consignes comprises. On coupe uniquement au début
        d'une demande de l'utilisateur, pour ne jamais séparer un appel d'outil de son résultat.
        """
        def size(msgs: list[dict]) -> int:
            return sum(len(str(m.get("content", ""))) + len(str(m.get("tool_calls", ""))) for m in msgs)

        system, rest = self.history[:1], self.history[1:]
        while size(rest) > self.max_history:
            starts = [i for i, m in enumerate(rest) if m["role"] == "user" and i > 0]
            if not starts:
                break
            rest = rest[starts[0]:]
        self.history = system + rest

    def _log(self, role: str, content: str) -> None:
        if self.memory:
            self.memory.add_message(role, content)
