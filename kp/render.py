"""HTML и PDF из КП.

Один шаблон для PDF и для превью в браузере. Отличаются только адреса
шрифтов: для PDF — файлы на диске, для веба — маршрут /fonts/.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from kp.config import ROOT
from kp.models import Brief, Lang, Profile, Proposal
from kp.pricing import Pricing, format_money

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
FONTS_DIR = ROOT / "fonts"

# Шрифты в репозитории (OFL). cyrillic=False — шрифт без кириллицы,
# в русском КП заголовки тогда набираются основным шрифтом.
FONTS = {
    "Inter": {
        "cyrillic": True,
        "faces": {400: "inter/Inter-Regular.ttf", 500: "inter/Inter-Medium.ttf",
                  600: "inter/Inter-SemiBold.ttf", 700: "inter/Inter-Bold.ttf"},
    },
    "Space Grotesk": {
        "cyrillic": False,
        "faces": {500: "space-grotesk/SpaceGrotesk-Medium.ttf", 700: "space-grotesk/SpaceGrotesk-Bold.ttf"},
    },
}

MONTHS_RU = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
             "августа", "сентября", "октября", "ноября", "декабря"]

LABELS = {
    "ru": {
        "doc_title": "Коммерческое предложение",
        "for": "Для", "from": "От", "date": "Дата", "project": "Проект",
        "goal": "Цель", "solution": "Решение", "what": "Что будет сделано", "stack": "Стек",
        "cases": "Релевантный опыт", "study": "учебный проект", "case_link": "Подробнее о кейсе",
        "all_cases": "Все кейсы",
        "timeline": "Сроки", "stage": "Этап", "content": "Содержание", "term": "Срок",
        "approval": "Согласование и старт", "total": "Итого",
        "cost": "Стоимость", "price": "Стоимость", "payment": "Порядок оплаты",
        "included": "Что входит", "excluded": "Что не входит",
        "next": "Следующий шаг", "start": "Старт", "needs": "Для старта нужно",
        "questions": "Вопросы", "demo": "Демо-профиль: исполнитель и кейсы вымышленные, документ показывает работу генератора.",
        "tier": "уровень",
    },
    "en": {
        "doc_title": "Project proposal",
        "for": "For", "from": "From", "date": "Date", "project": "Project",
        "goal": "Goal", "solution": "Solution", "what": "Deliverables", "stack": "Stack",
        "cases": "Relevant experience", "study": "learning project", "case_link": "Read the case",
        "all_cases": "All cases",
        "timeline": "Timeline", "stage": "Stage", "content": "Scope", "term": "Time",
        "approval": "Agreement and kickoff", "total": "Total",
        "cost": "Pricing", "price": "Price", "payment": "Payment",
        "included": "Included", "excluded": "Not included",
        "next": "Next step", "start": "Start", "needs": "To get started, we need",
        "questions": "Questions", "demo": "Demo profile: the company and its cases are fictional. This document shows how the generator works.",
        "tier": "tier",
    },
}


def mix(color: str, base: str, share: float) -> str:
    """Цвет color с долей share поверх base (аналог CSS color-mix,
    которого нет в WeasyPrint)."""
    a = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(base[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * share + y * (1 - share)):02x}" for x, y in zip(a, b))


def css_string(text: str) -> str:
    """Строка для CSS content: экранирование кавычек и обратных слэшей."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def days_label(n: int, lang: Lang) -> str:
    if lang == "en":
        return f"{n} business day" + ("" if n == 1 else "s")
    if n % 10 == 1 and n % 100 != 11:
        word = "рабочий день"
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = "рабочих дня"
    else:
        word = "рабочих дней"
    return f"{n} {word}"


def format_date(d: date, lang: Lang) -> str:
    if lang == "ru":
        return f"{d.day} {MONTHS_RU[d.month - 1]} {d.year}"
    return d.strftime("%-d %B %Y")


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env


def _font_faces(font_base: str) -> list[dict]:
    return [
        {"family": family, "weight": weight, "url": f"{font_base}{path}"}
        for family, spec in FONTS.items()
        for weight, path in spec["faces"].items()
    ]


def render_html(
    brief: Brief,
    profile: Profile,
    proposal: Proposal,
    pricing: Pricing,
    *,
    created: date | None = None,
    font_base: str | None = None,
) -> str:
    lang = brief.language
    brand = profile.brand
    heading_font = brand.heading_font
    if lang == "ru" and not FONTS.get(heading_font, {}).get("cyrillic", True):
        heading_font = brand.body_font

    cases = []
    for ref in proposal.relevant_cases:
        case = profile.case(ref.case_id)
        if case:
            cases.append({"case": case, "why": ref.why_relevant})

    blocks = []
    for ref in proposal.optional_blocks:
        block = profile.optional_block(ref.block_id)
        if block:
            blocks.append({
                "title": block.title.get(lang),
                "text": block.text.get(lang).replace("{detail}", ref.detail.strip()),
            })

    payment = profile.payment_option(proposal.payment_option_id)
    cases_url = profile.executor.contacts.cases_url

    return _env().get_template("proposal.html").render(
        lang=lang,
        t=LABELS[lang],
        brief=brief,
        profile=profile,
        executor=profile.executor,
        brand=brand,
        colors={
            "muted": mix(brand.text, brand.background, 0.62),
            "line": mix(brand.primary, brand.background, 0.16),
            "tint": mix(brand.primary, brand.background, 0.05),
            "accent_soft": mix(brand.accent, brand.background, 0.22),
            "screen_bg": mix(brand.primary, "#ffffff", 0.10),
        },
        footer=css_string(f"{LABELS[lang]['doc_title']} · {brief.company}"),
        heading_font=heading_font,
        font_faces=_font_faces(font_base if font_base is not None else FONTS_DIR.as_uri() + "/"),
        p=proposal,
        pricing=pricing,
        stage_rows=list(zip(proposal.stages, pricing.stages)),
        money=lambda v: format_money(v, pricing.currency),
        days=lambda n: days_label(n, lang),
        approval_days=pricing.total_days - sum(s.days for s in pricing.stages),
        cases=cases,
        cases_url=cases_url.get(lang) if cases_url else None,
        blocks=blocks,
        payment=payment.text.get(lang) if payment else "",
        included=profile.terms.included.get(lang),
        excluded=profile.terms.excluded.get(lang),
        needs=proposal.next_step.client_needs + profile.terms.next_step_fixed.get(lang),
        date=format_date(created or date.today(), lang),
    )


def render_pdf(html: str, out_path: Path) -> Path:
    # Импорт здесь: на macOS WeasyPrint требует DYLD_FALLBACK_LIBRARY_PATH,
    # а остальной код (тесты моделей, CLI profiles) работает и без него.
    from weasyprint import HTML

    out_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(ROOT)).write_pdf(out_path)
    return out_path
