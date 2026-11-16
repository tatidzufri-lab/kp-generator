"""Проверка текста КП по правилам голоса исполнителя.

Правила берутся из профиля (voice), так что проверка работает для любого
исполнителя. Проверяются только тексты, написанные LLM; фиксированные
тексты профиля (кейсы, условия) считаются только в общем объеме документа.

- autofix() молча исправляет то, что можно исправить механически: «ё» и эмодзи;
- lint() возвращает нарушения, которые нужно переписать. Их текст уходит
  в повторный запрос к LLM, поэтому формулировки конкретные.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from kp.models import Lang, Profile, Proposal

EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF\U00002B00-\U00002BFF️‍]"
)
LONG_DASH = "—"
WORD = re.compile(r"[\w\-]+", re.UNICODE)

# Маркеры ИИ-текста из ToV, которые ловятся регуляркой.
PATTERNS: dict[Lang, list[tuple[re.Pattern, str]]] = {
    "ru": [
        (re.compile(r"(?<!\w)не\s+[^,.;:!?\n]{1,60},\s*а\s+", re.I), "шаблон «не X, а Y»"),
        (re.compile(r"(?<!\w)дело\s+не\s+в\s+", re.I), "шаблон «дело не в X»"),
        (re.compile(r"(?<!\w)из\s+[^,.;:!?\n]{1,40}\s+—\s+в\s+", re.I), "шаблон «из X — в Y»"),
    ],
    "en": [
        (re.compile(r"\bnot\s+[^,.;:!?\n]{1,60},\s*but\s+", re.I), "pattern \"not X, but Y\""),
        (re.compile(r"\bisn't\s+(?:just\s+)?about\s+", re.I), "pattern \"it isn't about X\""),
        (re.compile(r"\bfrom\s+[^,.;:!?\n]{1,40}\s+—\s+to\s+", re.I), "pattern \"from X — to Y\""),
    ],
}


@dataclass(frozen=True)
class LintIssue:
    code: str
    message: str


def llm_strings(p: Proposal) -> Iterator[tuple[str, str]]:
    """(путь поля, текст) для всех строк, которые написала LLM."""
    yield "project_title", p.project_title
    yield "goal", p.goal
    for i, s in enumerate(p.solution_items):
        yield f"solution_items[{i}]", s
    for i, r in enumerate(p.relevant_cases):
        yield f"relevant_cases[{i}].why_relevant", r.why_relevant
    for i, st in enumerate(p.stages):
        yield f"stages[{i}].name", st.name
        yield f"stages[{i}].content", st.content
    yield "next_step.start", p.next_step.start
    for i, s in enumerate(p.next_step.client_needs):
        yield f"next_step.client_needs[{i}]", s
    for i, b in enumerate(p.optional_blocks):
        yield f"optional_blocks[{i}].detail", b.detail


def _map_strings(p: Proposal, fn) -> Proposal:
    """Копия КП с fn, примененной к каждой строке ответа LLM."""
    def walk(v):
        if isinstance(v, str):
            return fn(v)
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: (x if k in {"case_id", "block_id", "payment_option_id", "tier"} else walk(x)) for k, x in v.items()}
        return v
    return Proposal.model_validate(walk(p.model_dump()))


def autofix(p: Proposal, profile: Profile) -> Proposal:
    v = profile.voice

    def fix(s: str) -> str:
        if v.forbid_yo:
            s = s.replace("ё", "е").replace("Ё", "Е")
        if v.forbid_emoji:
            s = re.sub(r"\s{2,}", " ", EMOJI.sub("", s)).strip()
        return s

    return _map_strings(p, fix)


def document_text(p: Proposal, profile: Profile, lang: Lang) -> str:
    """Текст документа так, как его увидит клиент, — для подсчета объема."""
    parts: list[str] = [p.project_title, p.goal, *p.solution_items, ", ".join(p.stack)]
    for ref in p.relevant_cases:
        case = profile.case(ref.case_id)
        if case:
            parts += [case.title.get(lang), ref.why_relevant, *case.results.get(lang)]
    for st in p.stages:
        parts += [st.name, st.content]
    opt = profile.payment_option(p.payment_option_id)
    if opt:
        parts.append(opt.text.get(lang))
    parts += profile.terms.included.get(lang) + profile.terms.excluded.get(lang)
    parts += [p.next_step.start, *p.next_step.client_needs, *profile.terms.next_step_fixed.get(lang)]
    for ref in p.optional_blocks:
        block = profile.optional_block(ref.block_id)
        if block:
            parts += [block.title.get(lang), block.text.get(lang).replace("{detail}", ref.detail)]
    return "\n".join(parts)


def word_count(text: str) -> int:
    return len([w for w in WORD.findall(text) if any(ch.isalpha() for ch in w)])


FIRST_PERSON_RU = re.compile(r"^[А-ЯЁ][а-яё]+(?:у|ю)$")  # Сделаю, Подключу, Настрою


def _same_start(items: list[str], path: str, lang: Lang) -> list[LintIssue]:
    """ToV: пункты списка не должны быть построены одинаково."""
    if len(items) < 3:
        return []
    first = [(it.split() or [""])[0].strip(",.:;").lower() for it in items]
    top = max(set(first), key=first.count)
    if top and first.count(top) >= 3:
        return [LintIssue("same_start", f"{path}: {first.count(top)} пункта начинаются с «{top}». Начинай пункты по-разному.")]
    if lang == "ru":
        verbs = sum(bool(FIRST_PERSON_RU.match((it.split() or [""])[0])) for it in items)
        if verbs >= 3 and verbs * 2 > len(items):
            return [LintIssue(
                "same_start",
                f"{path}: {verbs} пунктов начинаются с глагола от первого лица («Сделаю», «Подключу»). "
                "Сформулируй пункты как результаты, по-разному.",
            )]
    return []


def lint(p: Proposal, profile: Profile, lang: Lang) -> list[LintIssue]:
    v = profile.voice
    issues: list[LintIssue] = []
    strings = list(llm_strings(p))
    joined = "\n".join(s for _, s in strings)

    if v.forbid_yo and re.search("[ёЁ]", joined):
        issues.append(LintIssue("yo", "Буква «ё» запрещена, пиши «е»."))
    if v.forbid_emoji and EMOJI.search(joined):
        issues.append(LintIssue("emoji", "Эмодзи запрещены."))

    dashes = joined.count(LONG_DASH)
    if dashes > v.max_long_dashes:
        issues.append(LintIssue(
            "dashes",
            f"Длинных тире «—» {dashes}, допустимо не больше {v.max_long_dashes}. Перестрой фразы без тире.",
        ))

    for path, text in strings:
        low = text.lower()
        for phrase in v.stop_phrases.get(lang):
            if re.search(r"(?<!\w)" + re.escape(phrase.lower()), low):
                issues.append(LintIssue("stop_phrase", f"{path}: стоп-фраза «{phrase}», перепиши без нее."))
        for rx, name in PATTERNS[lang]:
            if rx.search(text):
                issues.append(LintIssue("ai_pattern", f"{path}: {name} — признак ИИ-текста, перепиши прямым утверждением."))

    issues += _same_start(p.solution_items, "solution_items", lang)

    lo, hi = v.word_limit
    n = word_count(document_text(p, profile, lang))
    if n < lo:
        issues.append(LintIssue("too_short", f"Объем документа {n} слов, нужно {lo}–{hi}. Раскрой цель и решение конкретнее."))
    elif n > hi:
        issues.append(LintIssue("too_long", f"Объем документа {n} слов, нужно {lo}–{hi}. Сократи цель, пункты решения и описания этапов."))

    return issues
