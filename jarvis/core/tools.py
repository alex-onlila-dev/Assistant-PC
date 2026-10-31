"""Registre des outils que le cerveau peut appeler.

Chaque outil déclare s'il exige une confirmation (confirm=True).
La boucle agent bloque l'exécution tant que l'utilisateur n'a pas validé.
"""
from dataclasses import dataclass
from typing import Any, Callable


def param(type_: str, description: str, enum: list | None = None, items: dict | None = None) -> dict:
    p: dict[str, Any] = {"type": type_, "description": description}
    if enum:
        p["enum"] = enum
    if items:
        p["items"] = items
    return p


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    required: list[str]
    func: Callable[..., Any]
    confirm: bool = False
    summary: Callable[[dict], str] | None = None

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": self.required,
                },
            },
        }

    def describe(self, args: dict) -> str:
        """Phrase lisible présentée à l'utilisateur pour la confirmation."""
        if self.summary:
            try:
                return self.summary(args)
            except Exception:
                pass
        return f"{self.name}({args})"


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, description: str, params: dict | None = None,
                 required: list[str] | None = None, confirm: bool = False,
                 summary: Callable[[dict], str] | None = None):
        def deco(fn):
            self._tools[name] = Tool(name, description, params or {}, required or [], fn, confirm, summary)
            return fn
        return deco

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


registry = ToolRegistry()
