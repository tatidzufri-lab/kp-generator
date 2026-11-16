"""Импорт кейсов портфолио в YAML для профиля исполнителя.

Источники:
- сайт-портфолио (Flask): config.py — slug, номер, стек, ссылка на демо;
  i18n/cases_ru.json и i18n/cases_en.json — публичные тексты кейсов на двух
  языках, уже приведенные к Tone of Voice, и флаг study_project;
- справочник кейсов (Markdown) — только поле «Когда упоминать», оно нужно
  для подбора кейса под бриф.

Переносятся только публичные поля. «Формулировка для письма» и «Контекст»
из справочника не переносятся.

Пример:
    python scripts/import_cases.py \\
        --site-dir ~/path/to/Site \\
        --cases-md ~/path/to/Kejsy_Polnoe_Opisanie_v3.md \\
        --out profiles/tatiana.cases.yaml
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from datetime import date
from pathlib import Path

import yaml

SITE_URL = "https://tatidzufri.com"
STUDY_MARK = re.compile(r"\s*\((?:учебный проект|learning project|study project)\)", re.IGNORECASE)


def read_site_cases(site_dir: Path) -> list[dict]:
    """CASES из config.py без выполнения кода сайта."""
    tree = ast.parse((site_dir / "config.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "CASES" for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit("В config.py не найден список CASES")


def read_when_to_use(cases_md: Path) -> dict[int, str]:
    """{номер кейса: текст «Когда упоминать»} из справочника."""
    text = cases_md.read_text(encoding="utf-8")
    result: dict[int, str] = {}
    for m in re.finditer(r"^## КЕЙС №(\d+).*?(?=^## |\Z)", text, re.M | re.S):
        num = int(m.group(1))
        w = re.search(r"^\*\*Когда упоминать:\*\*\s*(.+)$", m.group(0), re.M)
        if w:
            # ToV: буква «ё» не используется нигде
            result[num] = w.group(1).strip().replace("ё", "е").replace("Ё", "Е")
    return result


def clean_title(title: str) -> str:
    return STUDY_MARK.sub("", title).strip()


def build_cases(site_dir: Path, cases_md: Path) -> list[dict]:
    site_cases = read_site_cases(site_dir)
    ru = json.loads((site_dir / "i18n" / "cases_ru.json").read_text(encoding="utf-8"))
    en = json.loads((site_dir / "i18n" / "cases_en.json").read_text(encoding="utf-8"))
    when = read_when_to_use(cases_md)

    out = []
    for c in sorted(site_cases, key=lambda c: c["id"]):
        slug = c["slug"]
        if slug not in ru or slug not in en:
            print(f"! пропускаю {slug}: нет текстов в i18n", file=sys.stderr)
            continue
        r, e = ru[slug], en[slug]
        if c["id"] not in when:
            print(f"! кейс №{c['id']} ({slug}): нет «Когда упоминать» в справочнике", file=sys.stderr)
        out.append({
            "id": slug,
            "number": c["id"],
            "study_project": bool(e.get("study_project") or r.get("study_project")),
            "title": {"ru": clean_title(r["title"]), "en": clean_title(e["title"])},
            "summary": {"ru": r["short_desc"], "en": e["short_desc"]},
            "results": {"ru": list(r["results"]), "en": list(e["results"])},
            "stack": list(c.get("tech", [])),
            "when_to_use": when.get(c["id"], ""),
            "url": {"ru": f"{SITE_URL}/case/{slug}", "en": f"{SITE_URL}/en/case/{slug}"},
            "demo_url": c.get("demo_link"),
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site-dir", type=Path, required=True, help="папка сайта-портфолио (config.py, i18n/)")
    ap.add_argument("--cases-md", type=Path, required=True, help="справочник кейсов .md")
    ap.add_argument("--out", type=Path, default=Path("profiles/tatiana.cases.yaml"))
    args = ap.parse_args()

    cases = build_cases(args.site_dir.expanduser(), args.cases_md.expanduser())
    header = (
        "# Сгенерировано scripts/import_cases.py — руками не править, перезапустить скрипт.\n"
        f"# Источник: сайт tatidzufri.com (тексты RU/EN) + справочник кейсов (когда упоминать).\n"
        f"# Дата импорта: {date.today().isoformat()}\n"
    )
    body = yaml.safe_dump({"cases": cases}, allow_unicode=True, sort_keys=False, width=1000)
    args.out.write_text(header + body, encoding="utf-8")
    study = sum(c["study_project"] for c in cases)
    print(f"Записано кейсов: {len(cases)} (учебных: {study}) → {args.out}")


if __name__ == "__main__":
    main()
