"""Système de confirmation : rien ne se modifie sans un « oui » explicite."""
import re
from abc import ABC, abstractmethod

YES = {"oui", "o", "ouais", "yes", "y", "ok", "okay", "vas-y", "vas y", "confirme", "valide", "d'accord", "go", "c'est bon"}
NO = {"non", "n", "no", "annule", "stop", "arrête", "arrete", "pas question"}


def parse_yes_no(text: str) -> bool | None:
    """Interprète une réponse libre (écrite ou vocale). None = pas compris."""
    t = re.sub(r"[^\w\s'-]", " ", (text or "").lower()).strip()
    if not t:
        return None
    words = t.split()

    def match(vocab: set[str]) -> bool:
        return any((w in words) if " " not in w else (w in t) for w in vocab)

    if match(NO):        # le « non » l'emporte toujours, par sécurité
        return False
    if match(YES):
        return True
    return None


class Confirmer(ABC):
    @abstractmethod
    def ask(self, action: str) -> bool:
        """Présente l'action à l'utilisateur et renvoie True s'il valide."""


class CLIConfirmer(Confirmer):
    def ask(self, action: str) -> bool:
        while True:
            answer = parse_yes_no(input(f"\n⚠️  {action}\n   Confirmer ? (oui/non) > "))
            if answer is not None:
                return answer
            print("   Réponds par oui ou non.")


class AutoConfirmer(Confirmer):
    """Pour les tests uniquement."""

    def __init__(self, allow: bool):
        self.allow = allow
        self.asked: list[str] = []

    def ask(self, action: str) -> bool:
        self.asked.append(action)
        return self.allow
