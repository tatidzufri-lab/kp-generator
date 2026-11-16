"""Стоимость и сроки КП (формула — в README, «Как считается стоимость»).

LLM относит каждый этап к уровню S/M/L. Здесь уровень превращается в часы,
деньги и рабочие дни по коэффициентам из .env:

    часы  = часы агента × множитель тестов + часы коммуникации и деплоя
    цена  = часы × ставка + токены агента по API-тарифу
    дни   = часы ÷ часов на проект клиента в день (вверх)
    итого дней = сумма дней этапов + 1 день на согласование
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from kp.config import Settings
from kp.models import Lang, Proposal

APPROVAL_DAYS = 1


@dataclass
class StageCost:
    name: str
    tier: str
    hours: float
    tokens_usd: float
    price: int
    days: int


@dataclass
class Pricing:
    currency: str  # RUB | USD
    rate: float
    stages: list[StageCost]
    total_price: int
    total_hours: float
    total_tokens_usd: float
    total_days: int

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Pricing:
        return cls(**{**d, "stages": [StageCost(**s) for s in d["stages"]]})


def _round_up(value: float, step: int) -> int:
    return int(math.ceil(value / step) * step)


def calculate(proposal: Proposal, settings: Settings, lang: Lang) -> Pricing:
    rub = lang == "ru"
    rate = settings.rate_rub if rub else settings.rate_usd
    fx = settings.usd_rub if rub else 1.0
    step = 500 if rub else 10

    stages: list[StageCost] = []
    for st in proposal.stages:
        t = settings.tiers[st.tier]
        hours = t.agent_hours * settings.test_multiplier + t.comm_hours
        price = _round_up(hours * rate + t.tokens_usd * fx, step)
        days = max(1, math.ceil(hours / settings.hours_per_client_day))
        stages.append(StageCost(st.name, st.tier, round(hours, 2), t.tokens_usd, price, days))

    return Pricing(
        currency="RUB" if rub else "USD",
        rate=rate,
        stages=stages,
        total_price=sum(s.price for s in stages),
        total_hours=round(sum(s.hours for s in stages), 2),
        total_tokens_usd=round(sum(s.tokens_usd for s in stages), 2),
        total_days=sum(s.days for s in stages) + APPROVAL_DAYS,
    )


def format_money(value: int, currency: str) -> str:
    if currency == "RUB":
        return f"{value:,}".replace(",", " ") + " ₽"
    return f"${value:,}"
