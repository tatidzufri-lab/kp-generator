"""Командная строка.

    python -m kp.cli generate --brief examples/brief_ru.json --profile tatiana [--mock] [--lang en]
    python -m kp.cli profiles

На macOS запускать через make или с DYLD_FALLBACK_LIBRARY_PATH (см. README).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from kp.config import load_settings
from kp.generator import GenerationError
from kp.models import Brief
from kp.profiles import ProfileError, list_profiles, load_profile
from kp.service import create_proposal
from kp.storage import OUTPUT_DIR


def cmd_generate(args: argparse.Namespace) -> int:
    try:
        brief = Brief.model_validate_json(Path(args.brief).read_text(encoding="utf-8"))
        if args.lang:
            brief = brief.model_copy(update={"language": args.lang})
        record = create_proposal(
            brief, args.profile, load_settings(),
            force_mock=args.mock, output_root=Path(args.out) if args.out else OUTPUT_DIR,
        )
    except FileNotFoundError as e:
        print(f"Файл не найден: {e.filename}", file=sys.stderr)
        return 2
    except ValidationError as e:
        print(f"Бриф не прошел проверку:\n{e}", file=sys.stderr)
        return 2
    except (ProfileError, GenerationError) as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        for d in getattr(e, "details", []):
            print(f"  - {d}", file=sys.stderr)
        return 1

    m = record.meta
    print(f"Режим: {m['mode']} ({m['model']}), попыток: {m['attempts']}")
    if m["mode"] == "live":
        u = m["usage"]
        print(f"Токены: вход {u['input_tokens']} (из кэша {u['cached_tokens']}), выход {u['output_tokens']}")
    price = f"{m['total_price']:,}".replace(",", " ")
    print(f"Итого: {price} {m['currency']}, {m['total_days']} раб. дн.")
    for w in m["warnings"]:
        print(f"Предупреждение: {w}")
    print(f"PDF: {record.pdf}")
    print(f"JSON: {record.path / 'proposal.json'}")
    return 0


def cmd_profiles(_: argparse.Namespace) -> int:
    for pid in list_profiles():
        p = load_profile(pid)
        mark = " (демо)" if p.demo else ""
        print(f"{pid}: {p.executor.name.ru}{mark}, кейсов: {len(p.cases)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kp", description="Генератор КП по брифу")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="сгенерировать КП")
    g.add_argument("--brief", required=True, help="JSON с брифом (поля модели Brief)")
    g.add_argument("--profile", required=True, help="id профиля исполнителя")
    g.add_argument("--lang", choices=["ru", "en"], help="переопределить язык брифа")
    g.add_argument("--mock", action="store_true", help="без запросов к OpenAI")
    g.add_argument("--out", help="корневая папка истории (по умолчанию output/)")
    g.set_defaults(func=cmd_generate)

    p = sub.add_parser("profiles", help="список профилей")
    p.set_defaults(func=cmd_profiles)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
