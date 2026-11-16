"""Настройки из .env.

Ставки, коэффициенты и ключ живут только в .env (в git не попадает).
Значения по умолчанию совпадают с .env.example.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class TierCost:
    agent_hours: float
    comm_hours: float
    tokens_usd: float


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError as e:
        raise ValueError(f".env: {name}={raw!r} — ожидается число") from e


def _tier(name: str, default: str) -> TierCost:
    raw = (os.getenv(name) or default).strip()
    try:
        a, c, t = (float(x) for x in raw.split(","))
    except ValueError as e:
        raise ValueError(f".env: {name}={raw!r} — ожидается «часы_агента,часы_коммуникации,токены_$»") from e
    return TierCost(a, c, t)


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = ""
    openai_model: str = ""
    mock_forced: bool = False
    rate_rub: float = 500
    rate_usd: float = 12
    usd_rub: float = 80
    hours_per_client_day: float = 4
    test_multiplier: float = 3
    tiers: dict[str, TierCost] = field(default_factory=dict)

    @property
    def mock(self) -> bool:
        """Mock-режим: явно включен или нет ключа."""
        return self.mock_forced or not self.openai_api_key


def load_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "").strip(),
        mock_forced=os.getenv("KP_MOCK", "").strip() in {"1", "true", "yes"},
        rate_rub=_float("KP_RATE_RUB", 500),
        rate_usd=_float("KP_RATE_USD", 12),
        usd_rub=_float("KP_USD_RUB", 80),
        hours_per_client_day=_float("KP_HOURS_PER_CLIENT_DAY", 4),
        test_multiplier=_float("KP_TEST_MULTIPLIER", 3),
        tiers={
            "S": _tier("KP_TIER_S", "1,2,10"),
            "M": _tier("KP_TIER_M", "2.5,3,30"),
            "L": _tier("KP_TIER_L", "6,5,75"),
        },
    )
