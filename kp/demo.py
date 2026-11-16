"""Публичный режим демо: лимиты на живые генерации.

Сессионный лимит хранится в cookie-сессии Flask, дневной — в JSON-файле
с блокировкой, потому что под gunicorn работают несколько процессов.
Генерации без API (заготовки) лимиты не расходуют.
"""

from __future__ import annotations

import fcntl
import json
from datetime import date
from pathlib import Path


class DailyCounter:
    def __init__(self, path: Path, limit: int):
        self.path = path
        self.limit = limit

    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        f = open(self.path, "a+", encoding="utf-8")
        fcntl.flock(f, fcntl.LOCK_EX)
        return f

    @staticmethod
    def _read(f) -> dict:
        f.seek(0)
        try:
            data = json.loads(f.read() or "{}")
        except json.JSONDecodeError:
            data = {}
        return data if isinstance(data, dict) else {}

    def used(self) -> int:
        with self._locked() as f:
            return int(self._read(f).get(date.today().isoformat(), 0))

    def left(self) -> int:
        return max(0, self.limit - self.used())

    def add(self) -> None:
        with self._locked() as f:
            data = self._read(f)
            today = date.today().isoformat()
            data = {today: int(data.get(today, 0)) + 1}  # старые дни не храним
            f.seek(0)
            f.truncate()
            f.write(json.dumps(data))
