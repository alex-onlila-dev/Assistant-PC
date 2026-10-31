"""Alarmes et minuteurs."""
from datetime import datetime, timedelta

from jarvis.core.alarms import parse_when
from jarvis.core.context import ctx
from jarvis.core.tools import param, registry


@registry.register(
    "set_alarm", "Programme une alarme à une heure précise.",
    {"time": param("string", "Heure 'HH:MM' ou date ISO 'AAAA-MM-JJTHH:MM'"),
     "label": param("string", "Motif de l'alarme")},
    ["time"], confirm=True,
    summary=lambda a: f"Programmer une alarme à {a['time']} ({a.get('label') or 'Alarme'})")
def set_alarm(time: str, label: str = "Alarme") -> dict:
    at = parse_when(time)
    alarm_id = ctx.alarms.add(at, label)
    return {"id": alarm_id, "heure": at.strftime("%d/%m/%Y %H:%M"), "motif": label}


@registry.register(
    "set_timer", "Lance un minuteur.",
    {"minutes": param("number", "Durée en minutes"), "label": param("string", "Motif")},
    ["minutes"], confirm=True,
    summary=lambda a: f"Lancer un minuteur de {a['minutes']} minute(s) ({a.get('label') or 'Minuteur'})")
def set_timer(minutes: float, label: str = "Minuteur") -> dict:
    at = datetime.now() + timedelta(minutes=float(minutes))
    alarm_id = ctx.alarms.add(at, label)
    return {"id": alarm_id, "sonne_a": at.strftime("%H:%M:%S"), "motif": label}


@registry.register("list_alarms", "Liste les alarmes et minuteurs en attente.")
def list_alarms() -> list[dict]:
    return ctx.alarms.list()


@registry.register(
    "cancel_alarm", "Annule une alarme ou un minuteur.",
    {"alarm_id": param("integer", "Identifiant de l'alarme")}, ["alarm_id"], confirm=True,
    summary=lambda a: f"Annuler l'alarme n°{a['alarm_id']}")
def cancel_alarm(alarm_id: int) -> str:
    ctx.alarms.cancel(int(alarm_id))
    return f"Alarme {alarm_id} annulée."
