"""Генерация КП: OpenAI или заготовленные ответы (mock).

generate() — общий конвейер для веба, CLI и скилла:
черновик → автоисправления → проверка структуры и голоса → при нарушениях
один повтор со списком нарушений → результат или понятная ошибка.
"""

from __future__ import annotations

import json
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import openai
from openai import OpenAI

from kp import prompts
from kp.config import ROOT, Settings
from kp.models import Brief, Profile, Proposal, check_proposal
from kp.tov_lint import autofix, lint

FIXTURES_DIR = ROOT / "fixtures"
MAX_ATTEMPTS = 2


class GenerationError(Exception):
    """Ошибка, которую можно показать пользователю как есть."""

    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.details = details or []


@dataclass
class Usage:
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0

    def add(self, other: Usage) -> None:
        self.input_tokens += other.input_tokens
        self.cached_tokens += other.cached_tokens
        self.output_tokens += other.output_tokens


@dataclass
class GenerationResult:
    proposal: Proposal
    mode: str  # "live" | "mock"
    model: str
    attempts: int
    warnings: list[str] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)


class Drafter(Protocol):
    mode: str
    model: str

    def draft(self, brief: Brief, profile: Profile, feedback: list[str] | None) -> tuple[Proposal, Usage]: ...


# --------------------------------------------------------------------------
# OpenAI
# --------------------------------------------------------------------------

class OpenAIDrafter:
    mode = "live"

    def __init__(self, api_key: str, model: str, timeout: float = 120):
        if not model:
            raise GenerationError("Не задана модель: укажите OPENAI_MODEL в .env.")
        self.model = model
        # SDK сам повторяет 408/409/429/5xx и обрывы связи с паузой.
        self.client = OpenAI(api_key=api_key, timeout=timeout, max_retries=3)

    def draft(self, brief: Brief, profile: Profile, feedback: list[str] | None) -> tuple[Proposal, Usage]:
        try:
            resp = self.client.responses.parse(
                model=self.model,
                instructions=prompts.system_prompt(profile, brief.language),
                input=prompts.user_prompt(brief, feedback),
                text_format=Proposal,
            )
        except openai.AuthenticationError as e:
            raise GenerationError("OpenAI отклонил ключ. Проверьте OPENAI_API_KEY в .env.") from e
        except openai.NotFoundError as e:
            raise GenerationError(f"Модель «{self.model}» недоступна на этом аккаунте. Проверьте OPENAI_MODEL.") from e
        except openai.RateLimitError as e:
            raise GenerationError("Превышен лимит запросов или закончился баланс OpenAI. Попробуйте позже.") from e
        except (openai.APITimeoutError, openai.APIConnectionError) as e:
            raise GenerationError("Нет связи с OpenAI. Проверьте интернет и попробуйте еще раз.") from e
        except openai.BadRequestError as e:
            raise GenerationError(f"OpenAI отклонил запрос: {e.message}") from e
        except openai.APIStatusError as e:
            raise GenerationError(f"Ошибка OpenAI ({e.status_code}). Попробуйте позже.") from e

        if resp.output_parsed is None:
            refusal = next(
                (c.refusal for item in resp.output for c in getattr(item, "content", []) or []
                 if getattr(c, "type", "") == "refusal"),
                None,
            )
            raise GenerationError(
                "Модель отказалась отвечать." if refusal else "Модель вернула ответ не по схеме.",
                [refusal] if refusal else [],
            )

        u = resp.usage
        usage = Usage(
            input_tokens=u.input_tokens if u else 0,
            cached_tokens=(u.input_tokens_details.cached_tokens if u and u.input_tokens_details else 0) or 0,
            output_tokens=u.output_tokens if u else 0,
        )
        return resp.output_parsed, usage


# --------------------------------------------------------------------------
# Mock
# --------------------------------------------------------------------------

class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class MockDrafter:
    """Заготовленный ответ из fixtures/mock_<profile>_<lang>.json.

    В строках можно использовать {company}, {contact}, {industry} — они
    заменяются данными брифа. Остальной текст фиксированный: mock показывает
    работу конвейера, а не качество генерации.
    """

    mode = "mock"
    model = "mock"

    def __init__(self, fixtures_dir: Path = FIXTURES_DIR):
        self.fixtures_dir = fixtures_dir

    def draft(self, brief: Brief, profile: Profile, feedback: list[str] | None) -> tuple[Proposal, Usage]:
        path = self.fixtures_dir / f"mock_{profile.id}_{brief.language}.json"
        if not path.exists():
            raise GenerationError(f"Для mock-режима нет заготовки {path.name}.")
        values = _SafeDict(
            company=brief.company,
            contact=brief.contact_name or brief.company,
            industry=brief.industry,
        )
        fmt = string.Formatter()

        def fill(v):
            if isinstance(v, str):
                return fmt.vformat(v, (), values)
            if isinstance(v, list):
                return [fill(x) for x in v]
            if isinstance(v, dict):
                return {k: fill(x) for k, x in v.items()}
            return v

        data = fill(json.loads(path.read_text(encoding="utf-8")))
        return Proposal.model_validate(data), Usage()


# --------------------------------------------------------------------------
# Конвейер
# --------------------------------------------------------------------------

def make_drafter(settings: Settings, force_mock: bool = False) -> Drafter:
    if force_mock or settings.mock:
        return MockDrafter()
    return OpenAIDrafter(settings.openai_api_key, settings.openai_model)


def generate(brief: Brief, profile: Profile, drafter: Drafter) -> GenerationResult:
    total = Usage()
    feedback: list[str] | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        proposal, usage = drafter.draft(brief, profile, feedback)
        total.add(usage)
        proposal = autofix(proposal, profile)

        errors = check_proposal(proposal, profile)
        style = [i.message for i in lint(proposal, profile, brief.language)]
        if not errors and not style:
            return GenerationResult(proposal, drafter.mode, drafter.model, attempt, [], total)

        if attempt == MAX_ATTEMPTS:
            if errors:
                raise GenerationError("КП не прошло проверку структуры после повтора.", errors + style)
            # Стиль не блокирует: КП отдается с предупреждениями для ручной правки.
            return GenerationResult(proposal, drafter.mode, drafter.model, attempt, style, total)

        feedback = errors + style

    raise AssertionError("unreachable")
