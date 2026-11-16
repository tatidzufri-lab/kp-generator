"""Загрузка YAML-профилей исполнителей.

Профиль лежит в profiles/<id>.yaml. Кейсы можно держать в отдельном файле
(ключ cases_file) — так их можно перегенерировать скриптом, не трогая
написанную руками часть профиля с комментариями.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from kp.models import Profile

PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"


class ProfileError(Exception):
    pass


def _read_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ProfileError(f"Файл не найден: {path}") from e
    except yaml.YAMLError as e:
        raise ProfileError(f"Ошибка YAML в {path.name}: {e}") from e
    if not isinstance(data, dict):
        raise ProfileError(f"{path.name}: ожидается словарь на верхнем уровне")
    return data


def load_profile(profile_id: str, profiles_dir: Path = PROFILES_DIR) -> Profile:
    path = profiles_dir / f"{profile_id}.yaml"
    data = _read_yaml(path)

    cases_file = data.pop("cases_file", None)
    if cases_file:
        cases_data = _read_yaml(profiles_dir / cases_file)
        data["cases"] = list(data.get("cases") or []) + list(cases_data.get("cases") or [])

    try:
        profile = Profile.model_validate(data)
    except ValidationError as e:
        raise ProfileError(f"Профиль «{profile_id}» не прошел проверку:\n{e}") from e
    if profile.id != profile_id:
        raise ProfileError(f"{path.name}: id внутри файла «{profile.id}» не совпадает с именем файла")
    return profile


def list_profiles(profiles_dir: Path = PROFILES_DIR) -> list[str]:
    """id всех профилей. Файлы *.cases.yaml — это кейсы, не профили."""
    return sorted(
        p.stem for p in profiles_dir.glob("*.yaml") if not p.name.endswith(".cases.yaml")
    )
