"""Модели данных: бриф клиента, профиль исполнителя, КП.

Три группы:
- Brief — то, что вводит пользователь в форме;
- Profile и его части — YAML-профиль исполнителя;
- Proposal — схема ответа LLM (Structured Outputs). В ней нет ни часов,
  ни денег: модель только относит этапы к уровню S/M/L, остальное
  считает код (kp/pricing.py).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Lang = Literal["ru", "en"]
Tier = Literal["S", "M", "L"]


# --------------------------------------------------------------------------
# Локализованные значения
# --------------------------------------------------------------------------

class L10n(BaseModel):
    """Строка на двух языках."""

    model_config = ConfigDict(extra="forbid")

    ru: str = Field(min_length=1)
    en: str = Field(min_length=1)

    def get(self, lang: Lang) -> str:
        return getattr(self, lang)


class L10nList(BaseModel):
    """Список строк на двух языках."""

    model_config = ConfigDict(extra="forbid")

    ru: list[str] = Field(min_length=1)
    en: list[str] = Field(min_length=1)

    def get(self, lang: Lang) -> list[str]:
        return getattr(self, lang)


# --------------------------------------------------------------------------
# Бриф
# --------------------------------------------------------------------------

class Brief(BaseModel):
    """Бриф клиента из веб-формы или CLI."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    company: str = Field(min_length=1, max_length=200, description="Компания или имя заказчика")
    contact_name: str | None = Field(default=None, max_length=200)
    industry: str = Field(min_length=1, max_length=200)
    task: str = Field(min_length=20, max_length=5000, description="Задача и боль своими словами")
    budget: str | None = Field(default=None, max_length=200, description="Ориентир бюджета, свободный текст")
    deadline: str | None = Field(default=None, max_length=200, description="Желаемые сроки, свободный текст")
    notes: str | None = Field(default=None, max_length=3000, description="Что еще прозвучало на созвоне")
    language: Lang = "ru"


# --------------------------------------------------------------------------
# Профиль исполнителя
# --------------------------------------------------------------------------

class Contacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    site: str | None = None
    cases_url: L10n | None = None
    telegram: str | None = None


class Executor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: L10n
    title: L10n
    tagline: L10n
    contacts: Contacts


class Brand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    accent: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    background: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    text: str = Field(default="#1A1A1A", pattern=r"^#[0-9A-Fa-f]{6}$")
    heading_font: str = "Space Grotesk"
    body_font: str = "Inter"


class Voice(BaseModel):
    """Тон и правила текста. Идут в промпт и в tov_lint."""

    model_config = ConfigDict(extra="forbid")

    tone: L10n
    rules: L10nList
    stop_phrases: L10nList
    forbid_yo: bool = False
    forbid_emoji: bool = True
    max_long_dashes: int = Field(default=2, ge=0)
    word_limit: tuple[int, int] = (250, 400)

    @field_validator("word_limit")
    @classmethod
    def _limit_order(cls, v: tuple[int, int]) -> tuple[int, int]:
        if v[0] >= v[1]:
            raise ValueError("word_limit: минимум должен быть меньше максимума")
        return v


class TierGuide(BaseModel):
    """Что означает уровень сложности — подсказка для LLM."""

    model_config = ConfigDict(extra="forbid")

    S: L10n
    M: L10n
    L: L10n

    def get(self, tier: Tier) -> L10n:
        return getattr(self, tier)


class PaymentOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    text: L10n
    hint: str = Field(description="Когда выбирать — для LLM")


class Terms(BaseModel):
    model_config = ConfigDict(extra="forbid")

    included: L10nList
    excluded: L10nList
    payment_options: list[PaymentOption] = Field(min_length=1)
    next_step_fixed: L10nList = Field(description="Постоянные пункты блока «Следующий шаг»")


class OptionalBlock(BaseModel):
    """Опциональный блок КП. Текст фиксированный, LLM только решает,
    включать ли его, и заполняет {detail}, если он есть в тексте."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    title: L10n
    text: L10n
    when: str = Field(description="Когда включать — для LLM")

    @property
    def needs_detail(self) -> bool:
        return "{detail}" in self.text.ru or "{detail}" in self.text.en


class Case(BaseModel):
    """Кейс из портфолио исполнителя. Цифры результатов берутся отсюда,
    LLM их не переписывает."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9-]+$")
    number: int | None = None
    study_project: bool = False
    title: L10n
    summary: L10n
    results: L10nList
    stack: list[str] = Field(default_factory=list)
    when_to_use: str = Field(default="", description="Ниши и типы задач — для подбора кейса")
    url: L10n | None = None
    demo_url: str | None = None


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    demo: bool = Field(default=False, description="Вымышленный профиль: в КП ставится пометка «Демо»")
    executor: Executor
    brand: Brand
    voice: Voice
    services: L10nList
    skills: list[str] = Field(default_factory=list, description="Технологии, с которыми исполнитель уже работает, помимо стека кейсов")
    tiers: TierGuide
    terms: Terms
    optional_blocks: list[OptionalBlock] = Field(default_factory=list)
    cases: list[Case] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> Profile:
        for name, items in (
            ("cases", self.cases),
            ("optional_blocks", self.optional_blocks),
            ("payment_options", self.terms.payment_options),
        ):
            ids = [i.id for i in items]
            dupes = {i for i in ids if ids.count(i) > 1}
            if dupes:
                raise ValueError(f"{name}: повторяются id {sorted(dupes)}")
        return self

    def case(self, case_id: str) -> Case | None:
        return next((c for c in self.cases if c.id == case_id), None)

    def optional_block(self, block_id: str) -> OptionalBlock | None:
        return next((b for b in self.optional_blocks if b.id == block_id), None)

    def payment_option(self, option_id: str) -> PaymentOption | None:
        return next((p for p in self.terms.payment_options if p.id == option_id), None)


# --------------------------------------------------------------------------
# КП — схема ответа LLM
# --------------------------------------------------------------------------
# Совместима со strict-режимом Structured Outputs: все поля обязательные,
# без значений по умолчанию, без dict. Ограничения на количество элементов
# проверяются в check_proposal(), а не в схеме.

class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaseRef(_Strict):
    case_id: str = Field(description="id кейса из профиля исполнителя")
    why_relevant: str = Field(description="Одно предложение: чем кейс похож на задачу клиента")


class Stage(_Strict):
    name: str = Field(description="Название этапа, например «MVP»")
    content: str = Field(description="Что входит в этап — конкретно, по задаче клиента")
    tier: Tier = Field(description="Уровень сложности этапа по шкале профиля")
    tier_reason: str = Field(description="Почему выбран этот уровень, одно предложение")


class OptionalBlockRef(_Strict):
    block_id: str = Field(description="id опционального блока из профиля")
    detail: str = Field(description="Чем заполнить {detail} в тексте блока; пустая строка, если подстановки нет")
    reason: str = Field(description="Почему блок нужен этому клиенту, одно предложение")


class NextStep(_Strict):
    start: str = Field(description="Когда исполнитель готов приступить")
    client_needs: list[str] = Field(description="Что нужно от клиента для старта: доступы, данные, ключи")


class Proposal(_Strict):
    project_title: str = Field(description="Короткое название проекта")
    goal: str = Field(description="Цель: боль клиента его словами и что изменится, 2–3 предложения")
    solution_items: list[str] = Field(description="Что будет сделано: 4–7 конкретных модулей или функций")
    stack: list[str] = Field(description="Технологии")
    relevant_cases: list[CaseRef] = Field(description="1–3 кейса из профиля")
    stages: list[Stage] = Field(description="2–4 этапа; последний — тестирование и сдача")
    payment_option_id: str = Field(description="id варианта оплаты из профиля")
    next_step: NextStep
    optional_blocks: list[OptionalBlockRef] = Field(description="0–2 опциональных блока из профиля")


def check_proposal(p: Proposal, profile: Profile) -> list[str]:
    """Проверки, которые не выражаются в strict-схеме.

    Возвращает список нарушений на русском — он же уходит в повторный
    запрос к LLM, поэтому формулировки конкретные.
    """
    errors: list[str] = []

    def count(name: str, items: list, lo: int, hi: int) -> None:
        if not lo <= len(items) <= hi:
            errors.append(f"{name}: нужно от {lo} до {hi} элементов, сейчас {len(items)}")

    count("solution_items", p.solution_items, 4, 7)
    count("relevant_cases", p.relevant_cases, 1, 3)
    count("stages", p.stages, 2, 4)
    count("optional_blocks", p.optional_blocks, 0, 2)
    count("next_step.client_needs", p.next_step.client_needs, 1, 5)

    known_cases = {c.id for c in profile.cases}
    seen: set[str] = set()
    for ref in p.relevant_cases:
        if ref.case_id not in known_cases:
            errors.append(f"relevant_cases: кейса «{ref.case_id}» нет в профиле, выбирай из: {sorted(known_cases)}")
        if ref.case_id in seen:
            errors.append(f"relevant_cases: кейс «{ref.case_id}» указан дважды")
        seen.add(ref.case_id)

    if profile.payment_option(p.payment_option_id) is None:
        ids = [o.id for o in profile.terms.payment_options]
        errors.append(f"payment_option_id: «{p.payment_option_id}» нет в профиле, выбирай из: {ids}")

    for ref in p.optional_blocks:
        block = profile.optional_block(ref.block_id)
        if block is None:
            ids = [b.id for b in profile.optional_blocks]
            errors.append(f"optional_blocks: блока «{ref.block_id}» нет в профиле, выбирай из: {ids}")
        elif block.needs_detail and not ref.detail.strip():
            errors.append(f"optional_blocks: блоку «{ref.block_id}» нужен detail")

    for i, st in enumerate(p.stages, 1):
        if not st.name.strip() or not st.content.strip():
            errors.append(f"stages[{i}]: пустое название или содержание")
    if p.stages and p.stages[-1].tier != "S":
        errors.append(
            "stages: последний этап (тестирование и сдача) всегда уровня S — "
            "время на тесты уже заложено в часы каждого этапа"
        )

    known = {t.lower() for t in profile.skills}
    for c in profile.cases:
        known |= {t.lower() for t in c.stack}
    for ref in p.optional_blocks:
        if ref.block_id == "limitations" and ref.detail.strip():
            named = [x.strip() for x in re.split(r",| и | and ", ref.detail) if x.strip()]
            familiar = [x for x in named if any(k in x.lower() or x.lower() in k for k in known)]
            if familiar:
                errors.append(
                    f"optional_blocks: «limitations» называет знакомые исполнителю технологии ({', '.join(familiar)}). "
                    "Убери блок или назови только то, чего нет в стеке и навыках"
                )

    return errors
