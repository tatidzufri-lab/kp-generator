"""История КП на диске.

Каждое КП — папка output/<дата>_<компания>_<время>/:
brief.json, proposal.json, pricing.json, meta.json, proposal.html, proposal.pdf.
Папка output/ в .gitignore: в брифах могут быть данные клиентов.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from kp.config import ROOT

OUTPUT_DIR = ROOT / "output"
ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_[a-z0-9-]+_\d{6}(-\d+)?$")

TRANSLIT = dict(zip(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
     "u", "f", "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"],
))


def slugify(text: str, max_len: int = 40) -> str:
    s = "".join(TRANSLIT.get(ch, ch) for ch in text.lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s[:max_len].rstrip("-")) or "client"


@dataclass
class Record:
    id: str
    path: Path
    meta: dict

    @property
    def pdf(self) -> Path:
        return self.path / "proposal.pdf"

    @property
    def html(self) -> Path:
        return self.path / "proposal.html"

    def load_json(self, name: str) -> dict:
        return json.loads((self.path / f"{name}.json").read_text(encoding="utf-8"))


def new_record_dir(company: str, now: datetime | None = None, root: Path = OUTPUT_DIR) -> Path:
    now = now or datetime.now()
    rid = f"{now:%Y-%m-%d}_{slugify(company)}_{now:%H%M%S}"
    path = root / rid
    n = 1
    while path.exists():  # два КП в одну секунду
        n += 1
        path = root / f"{rid}-{n}"
    path.mkdir(parents=True)
    return path


def write_json(path: Path, name: str, data: dict) -> None:
    (path / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_record(record_id: str, root: Path = OUTPUT_DIR) -> Record | None:
    if not ID_RE.match(record_id):  # защита от ../ в адресе
        return None
    path = root / record_id
    meta_file = path / "meta.json"
    if not meta_file.exists():
        return None
    return Record(record_id, path, json.loads(meta_file.read_text(encoding="utf-8")))


def list_history(root: Path = OUTPUT_DIR) -> list[Record]:
    if not root.exists():
        return []
    records = [get_record(p.name, root) for p in root.iterdir() if p.is_dir()]
    return sorted((r for r in records if r), key=lambda r: r.meta.get("created_at", ""), reverse=True)
