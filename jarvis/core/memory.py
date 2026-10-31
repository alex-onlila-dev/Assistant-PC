"""Mémoire locale (SQLite) : historique des échanges et alarmes."""
import sqlite3
import threading
from datetime import datetime
from pathlib import Path


class Memory:
    def __init__(self, data_dir: str):
        self.path = Path(data_dir) / "jarvis.db"
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS alarms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                at TEXT NOT NULL, label TEXT NOT NULL, done INTEGER DEFAULT 0);
        """)
        self._conn.commit()

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    # --- messages ---
    def add_message(self, role: str, content: str) -> None:
        self._exec("INSERT INTO messages (ts, role, content) VALUES (?, ?, ?)",
                   (datetime.now().isoformat(timespec="seconds"), role, content))

    def recent_messages(self, limit: int = 20) -> list[dict]:
        rows = self._exec("SELECT ts, role, content FROM messages ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows.fetchall()][::-1]

    # --- alarmes ---
    def add_alarm(self, at: datetime, label: str) -> int:
        return self._exec("INSERT INTO alarms (at, label) VALUES (?, ?)",
                          (at.isoformat(timespec="seconds"), label)).lastrowid

    def pending_alarms(self) -> list[dict]:
        rows = self._exec("SELECT id, at, label FROM alarms WHERE done = 0 ORDER BY at")
        return [dict(r) for r in rows.fetchall()]

    def mark_alarm_done(self, alarm_id: int) -> None:
        self._exec("UPDATE alarms SET done = 1 WHERE id = ?", (alarm_id,))
