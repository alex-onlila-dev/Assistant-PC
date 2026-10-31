"""Alarmes et minuteurs gérés par Jarvis lui-même : identique sur tous les OS."""
from datetime import datetime, timedelta
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler


def parse_when(when: str) -> datetime:
    """Accepte "07:30", "7h30", ou une date ISO "2026-11-02T08:00"."""
    w = when.strip().lower().replace("h", ":")
    if w.endswith(":"):
        w += "00"
    try:
        return datetime.fromisoformat(w)
    except ValueError:
        pass
    hour, minute = (int(x) for x in w.split(":")[:2])
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


class AlarmService:
    def __init__(self, memory, on_ring: Callable[[str], None]):
        self.memory = memory
        self.on_ring = on_ring
        self.scheduler = BackgroundScheduler()

    def start(self) -> None:
        self.scheduler.start()
        now = datetime.now()
        for a in self.memory.pending_alarms():
            at = datetime.fromisoformat(a["at"])
            if at > now:
                self._schedule(a["id"], at, a["label"])
            else:
                self.memory.mark_alarm_done(a["id"])

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def add(self, at: datetime, label: str) -> int:
        alarm_id = self.memory.add_alarm(at, label)
        self._schedule(alarm_id, at, label)
        return alarm_id

    def cancel(self, alarm_id: int) -> bool:
        job = self.scheduler.get_job(str(alarm_id))
        if job:
            job.remove()
        self.memory.mark_alarm_done(alarm_id)
        return job is not None

    def list(self) -> list[dict]:
        return self.memory.pending_alarms()

    def _schedule(self, alarm_id: int, at: datetime, label: str) -> None:
        def ring():
            self.memory.mark_alarm_done(alarm_id)
            self.on_ring(label)
        self.scheduler.add_job(ring, "date", run_date=at, id=str(alarm_id), replace_existing=True)
