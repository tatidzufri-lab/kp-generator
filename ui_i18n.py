"""Язык веб-интерфейса: RU и EN.

Язык интерфейса не равен языку КП. Интерфейс выбирается так:
?lang=en|ru в адресе (запоминается в сессии) → сессия → Accept-Language → ru.
Язык КП по умолчанию совпадает с языком интерфейса, но его можно переключить в форме.
"""

from __future__ import annotations

from flask import request, session

LANGS = ("ru", "en")
DEFAULT = "ru"

TEXT: dict[str, dict[str, str]] = {
    # шапка
    "app_title": {"ru": "Генератор КП", "en": "Proposal generator"},
    "brand": {"ru": "КП<span>·</span>генератор", "en": "Proposal<span>·</span>generator"},
    "nav_new": {"ru": "Новое КП", "en": "New proposal"},
    "nav_mine": {"ru": "Мои КП", "en": "My proposals"},
    "nav_history": {"ru": "История", "en": "History"},
    "mode_mock": {"ru": "Без API: заготовки", "en": "No API: canned drafts"},
    "mode_mock_hint": {"ru": "Нет ключа OpenAI или KP_MOCK=1", "en": "No OpenAI key or KP_MOCK=1"},
    "mode_live_hint": {"ru": "Запросы идут в OpenAI", "en": "Requests go to OpenAI"},
    "no_model": {"ru": "модель не задана", "en": "no model set"},
    # форма
    "form_h1": {"ru": "Новое коммерческое предложение", "en": "New commercial proposal"},
    "form_sub": {
        "ru": "Заполните бриф после разговора с заказчиком. Структура, кейсы и стоимость соберутся из профиля исполнителя.",
        "en": "Fill in the brief after your call with the client. Structure, case studies and pricing come from the contractor profile.",
    },
    "demo_note": {
        "ru": "Это демо. Генераций через OpenAI в этой сессии осталось: <strong>{n}</strong>. Без API (галочка «без API») можно сколько угодно, но текст будет заготовкой. Созданные КП видны только вам.",
        "en": "This is a demo. OpenAI generations left in this session: <strong>{n}</strong>. Without the API (the “no API” checkbox) you can generate as many as you like, but the text will be a canned draft. Your proposals are visible only to you.",
    },
    "f_profile": {"ru": "Профиль исполнителя", "en": "Contractor profile"},
    "demo_suffix": {"ru": " (демо)", "en": " (demo)"},
    "f_language": {"ru": "Язык КП", "en": "Proposal language"},
    "f_company": {"ru": "Компания или заказчик", "en": "Company or client"},
    "f_contact": {"ru": "Контактное лицо", "en": "Contact person"},
    "ph_contact": {"ru": "Имя, должность", "en": "Name, job title"},
    "f_industry": {"ru": "Отрасль", "en": "Industry"},
    "f_task": {"ru": "Задача и боль заказчика", "en": "Client’s task and pain"},
    "ph_task": {
        "ru": "Своими словами заказчика: что сейчас не так, что хочет получить",
        "en": "In the client’s own words: what’s wrong now and what they want to get",
    },
    "f_budget": {"ru": "Бюджет (ориентир)", "en": "Budget (rough)"},
    "ph_budget": {"ru": "до 60 000 ₽", "en": "up to $1,500"},
    "f_deadline": {"ru": "Сроки", "en": "Timeline"},
    "ph_deadline": {"ru": "за месяц", "en": "within a month"},
    "f_notes": {"ru": "Что еще прозвучало на созвоне", "en": "Anything else from the call"},
    "ph_notes": {"ru": "Какие системы уже есть, доступы, ограничения", "en": "Existing systems, access, constraints"},
    "btn_generate": {"ru": "Сгенерировать КП", "en": "Generate proposal"},
    "btn_example": {"ru": "Заполнить пример", "en": "Fill in an example"},
    "chk_mock": {"ru": "без API (заготовка)", "en": "no API (canned draft)"},
    "wait": {"ru": "Генерирую, обычно это 20–60 секунд…", "en": "Generating, usually 20–60 seconds…"},
    "generating": {"ru": "Генерирую…", "en": "Generating…"},
    # ошибки формы
    "err_missing": {"ru": "Обязательное поле", "en": "Required field"},
    "err_short": {"ru": "Слишком коротко: минимум {min_length} символов", "en": "Too short: at least {min_length} characters"},
    "err_long": {"ru": "Слишком длинно: максимум {max_length} символов", "en": "Too long: at most {max_length} characters"},
    "err_literal": {"ru": "Недопустимое значение", "en": "Invalid value"},
    "err_profile": {"ru": "Выберите профиль исполнителя", "en": "Choose a contractor profile"},
    "quota_session": {
        "ru": "Лимит демо на эту сессию исчерпан. Можно сгенерировать КП без API (галочка «без API»).",
        "en": "The demo limit for this session is used up. You can still generate without the API (the “no API” checkbox).",
    },
    "quota_day": {
        "ru": "Дневной лимит демо исчерпан, попробуйте завтра. Без API генерация доступна.",
        "en": "The daily demo limit is used up, please try tomorrow. Generation without the API still works.",
    },
    "regen_failed": {"ru": "Не удалось сгенерировать заново: {e}", "en": "Could not regenerate: {e}"},
    # история
    "hist_title": {"ru": "История КП", "en": "Proposal history"},
    "hist_h1": {"ru": "История", "en": "History"},
    "hist_sub_demo": {"ru": "КП, созданные в этой сессии, новые сверху.", "en": "Proposals created in this session, newest first."},
    "hist_sub": {
        "ru": "Все сгенерированные КП, новые сверху. Файлы лежат в папке <code>output/</code>.",
        "en": "All generated proposals, newest first. Files are stored in <code>output/</code>.",
    },
    "th_date": {"ru": "Дата", "en": "Date"},
    "th_client": {"ru": "Клиент и проект", "en": "Client and project"},
    "th_profile": {"ru": "Исполнитель", "en": "Contractor"},
    "th_lang": {"ru": "Язык", "en": "Language"},
    "th_sum": {"ru": "Сумма", "en": "Total"},
    "th_mode": {"ru": "Режим", "en": "Mode"},
    "pill_demo": {"ru": "демо", "en": "demo"},
    "pill_mock": {"ru": "заготовка", "en": "canned"},
    "remarks": {"ru": "замеч.", "en": "notes"},
    "workdays_short": {"ru": "раб. дн.", "en": "business days"},
    "empty": {"ru": "Пока ни одного КП.", "en": "No proposals yet."},
    "create_first": {"ru": "Создать первое", "en": "Create the first one"},
    # превью
    "back_history": {"ru": "← История", "en": "← History"},
    "download_pdf": {"ru": "Скачать PDF", "en": "Download PDF"},
    "regenerate": {"ru": "Сгенерировать заново", "en": "Regenerate"},
    "tov_warn": {
        "ru": "Проверка по Tone of Voice: поправьте перед отправкой",
        "en": "Tone of voice check: fix before sending",
    },
    "doc_frame": {"ru": "КП", "en": "Proposal"},
    "calc": {"ru": "Расчет", "en": "Estimate"},
    "calc_private": {"ru": "Видно только вам, в PDF не попадает.", "en": "Visible only to you, not included in the PDF."},
    "th_stage": {"ru": "Этап", "en": "Stage"},
    "th_tier": {"ru": "Ур.", "en": "Tier"},
    "th_hours": {"ru": "Часы", "en": "Hours"},
    "th_price": {"ru": "Цена", "en": "Price"},
    "total": {"ru": "Итого", "en": "Total"},
    "rate": {"ru": "Ставка", "en": "Rate"},
    "per_hour": {"ru": "/ч", "en": "/h"},
    "agent_tokens": {"ru": "Токены агента", "en": "Agent tokens"},
    "term": {"ru": "Срок", "en": "Timeline"},
    "generation": {"ru": "Генерация", "en": "Generation"},
    "canned": {"ru": "заготовка", "en": "canned draft"},
    "attempts": {"ru": "попыток", "en": "attempts"},
    "req_tokens": {"ru": "Токены запроса", "en": "Request tokens"},
    "tok_line": {
        "ru": "вход {i} (кэш {c}), выход {o}",
        "en": "input {i} (cached {c}), output {o}",
    },
    # 404
    "nf_title": {"ru": "Не найдено", "en": "Not found"},
    "nf_text": {"ru": "Такого КП нет в истории.", "en": "There is no such proposal in the history."},
    "to_form": {"ru": "К форме", "en": "Back to the form"},
}


def current_lang() -> str:
    """Язык интерфейса для текущего запроса."""
    q = request.args.get("lang")
    if q in LANGS:
        session["ui_lang"] = q
        return q
    saved = session.get("ui_lang")
    if saved in LANGS:
        return saved
    return request.accept_languages.best_match(LANGS) or DEFAULT


def t(key: str, lang: str | None = None, **kw) -> str:
    lang = lang or current_lang()
    entry = TEXT[key]
    s = entry.get(lang) or entry[DEFAULT]
    return s.format(**kw) if kw else s
