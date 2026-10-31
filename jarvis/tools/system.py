"""Applications, paramètres système, web et infos machine."""
import platform
import shutil
from datetime import datetime
from pathlib import Path

import psutil

from jarvis.core.context import ctx
from jarvis.core.tools import param, registry
from jarvis.tools._paths import human_size

SETTINGS_SECTIONS = [
    "accueil", "affichage", "son", "bluetooth", "wifi", "réseau", "notifications", "alimentation",
    "batterie", "date et heure", "langue", "personnalisation", "fond d'écran", "applications",
    "confidentialité", "mises à jour", "stockage", "souris", "clavier", "imprimantes", "comptes",
]


@registry.register(
    "list_applications", "Liste les applications installées (filtrable par nom).",
    {"filter": param("string", "Texte à chercher dans le nom (optionnel)")})
def list_applications(filter: str = "") -> dict:
    apps = sorted(ctx.os.list_apps())
    if filter:
        apps = [a for a in apps if filter.lower() in a.lower()]
    return {"applications": apps[:200], "total": len(apps)}


@registry.register(
    "open_application", "Lance une application installée par son nom.",
    {"name": param("string", "Nom de l'application, ex: 'Chrome', 'VS Code', 'Spotify'")},
    ["name"], confirm=True, summary=lambda a: f"Lancer l'application « {a['name']} »")
def open_application(name: str) -> str:
    return f"Application lancée : {ctx.os.open_app(name)}"


@registry.register(
    "open_settings", "Ouvre une section des paramètres du système.",
    {"section": param("string", "Section à ouvrir", enum=SETTINGS_SECTIONS)},
    ["section"], confirm=True, summary=lambda a: f"Ouvrir les paramètres : {a['section']}")
def open_settings(section: str) -> str:
    ctx.os.open_settings(section)
    return f"Paramètres ouverts : {section}"


@registry.register(
    "open_url", "Ouvre une adresse web dans le navigateur par défaut.",
    {"url": param("string", "Adresse complète, ex: https://…")},
    ["url"], confirm=True, summary=lambda a: f"Ouvrir le site {a['url']}")
def open_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    ctx.os.open_url(url)
    return f"Ouvert : {url}"


@registry.register("system_info", "Donne l'état de l'ordinateur : OS, processeur, mémoire, disque, batterie.")
def system_info() -> dict:
    mem = psutil.virtual_memory()
    disk = shutil.disk_usage(Path.home().anchor or "/")
    info = {
        "os": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "processeur_utilisation": f"{psutil.cpu_percent(interval=0.5)} %",
        "coeurs": psutil.cpu_count(),
        "memoire": f"{human_size(mem.used)} / {human_size(mem.total)} ({mem.percent} %)",
        "disque_libre": f"{human_size(disk.free)} / {human_size(disk.total)}",
    }
    battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if battery:
        info["batterie"] = f"{battery.percent:.0f} %" + (" (en charge)" if battery.power_plugged else "")
    return info


@registry.register("get_datetime", "Donne la date et l'heure actuelles.")
def get_datetime() -> str:
    return datetime.now().strftime("%A %d %B %Y, %H:%M:%S")
