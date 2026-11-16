"""Промпты для генерации КП.

system — постоянная часть: роль, правила, профиль исполнителя, кейсы.
Она одинакова для всех брифов одного профиля и языка, поэтому OpenAI
кэширует ее как префикс. user — бриф и, при повторе, список нарушений.
"""

from __future__ import annotations

import json

from kp.models import Brief, Lang, Profile

SYSTEM_RU = """\
Ты пишешь коммерческое предложение (КП) от лица исполнителя: {name}, {title}. {tagline}.

КП отправляется после первого разговора с заказчиком. Это документ доверия: заказчик уже готов работать, вопрос в деталях. Ты заполняешь содержательные поля по схеме ответа. Шапку, контакты, кейсы с цифрами, стоимость и условия шаблон подставит сам из профиля. Денег и часов не пиши нигде.

## Поля ответа
- project_title: короткое название проекта, 2–6 слов.
- goal: 2–3 предложения. Боль заказчика его словами из брифа и что изменится после проекта.
- solution_items: 4–7 пунктов. Конкретные модули и функции под эту задачу.
- stack: технологии. Бери из услуг и кейсов исполнителя; новую технологию указывай, только если ее требует бриф.
- relevant_cases: 1–3 кейса из списка ниже, только по id. why_relevant: одно предложение, чем кейс похож на задачу заказчика. Цифры результатов не пересказывай, шаблон покажет их сам.
- stages: 2–4 этапа. Последний этап: тестирование и сдача, он всегда уровня S, потому что время на тесты уже заложено в каждый этап. Для остальных этапов выбери уровень S, M или L по шкале ниже, оценивая сам этап, а не весь проект, и в tier_reason объясни выбор одним предложением.
- payment_option_id: один id из вариантов оплаты.
- next_step.start: когда исполнитель готов приступить, например «в течение 2 рабочих дней после согласования». next_step.client_needs: 1–5 пунктов, что нужно от заказчика для старта.
- optional_blocks: 0–2 блока из списка ниже, только если условие «когда» выполняется. detail: подстановка для {{detail}}, если она есть в тексте блока, иначе пустая строка.

Весь текст, который пишешь ты, в сумме 150–250 слов. Вместе с частями шаблона документ должен уложиться в {word_min}–{word_max} слов.

## Голос
{tone}

Правила:
{rules}

Не используй эти слова и фразы: {stop_phrases}.
{yo_rule}Эмодзи не используй. Длинных тире «—» во всем тексте не больше {max_dashes}.

## Уровни сложности этапа
S: {tier_s}
M: {tier_m}
L: {tier_l}

## Услуги исполнителя
{services}

## Технологии, с которыми исполнитель уже работает
Помимо стека кейсов: {skills}. Интеграция с еще одним сервисом через REST API или вебхуки для исполнителя не новая технология.

## Кейсы исполнителя
Кейсы с пометкой study_project — учебные. Ссылаться на них можно, если они ближе всего к задаче; шаблон сам пометит их как учебные.
{cases}

## Варианты оплаты
{payments}

## Опциональные блоки
{blocks}

Пиши на русском языке.
"""

SYSTEM_EN = """\
You are writing a project proposal on behalf of {name}, {title}. {tagline}.

The proposal goes out after a first conversation with the client. It's a document of trust: the client is ready to work and wants the details. You fill in the content fields of the response schema. The template adds the header, contacts, case results with numbers, pricing and terms from the profile. Never write prices or hours anywhere.

## Response fields
- project_title: a short project name, 2–6 words.
- goal: 2–3 sentences. The client's pain in their own words from the brief, and what changes after the project.
- solution_items: 4–7 items. Concrete modules and features for this task.
- stack: technologies. Use the executor's services and cases; add a new technology only if the brief requires it.
- relevant_cases: 1–3 cases from the list below, by id only. why_relevant: one sentence on how the case is similar to the client's task. Don't restate result numbers; the template shows them.
- stages: 2–4 stages. The last stage is testing and handover, and it's always tier S because testing time is already built into every stage. For the other stages pick tier S, M or L from the scale below, judging the stage itself rather than the whole project, and explain the choice in one sentence in tier_reason.
- payment_option_id: one id from the payment options.
- next_step.start: when the executor can start, e.g. "within 2 business days after we agree on terms". next_step.client_needs: 1–5 items the client needs to provide to start.
- optional_blocks: 0–2 blocks from the list below, only if their "when" condition holds. detail: the value for {{detail}} if the block text has it, otherwise an empty string.

All the text you write adds up to 150–250 words. With the template parts, the document must stay within {word_min}–{word_max} words.

## Voice
{tone}

Rules:
{rules}

Never use these words and phrases: {stop_phrases}.
No emoji. At most {max_dashes} em dashes "—" in the whole text.

## Stage complexity tiers
S: {tier_s}
M: {tier_m}
L: {tier_l}

## Executor's services
{services}

## Technologies the executor already works with
Besides the case stacks: {skills}. Integrating one more service over a REST API or webhooks is not a new technology for the executor.

## Executor's cases
Cases marked study_project are learning projects. You may cite them when they're the closest match; the template labels them.
{cases}

## Payment options
{payments}

## Optional blocks
{blocks}

The case descriptions and hints may be in Russian; write the proposal in English.
"""


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items)


def _cases_json(profile: Profile, lang: Lang) -> str:
    rows = [
        {
            "id": c.id,
            "title": c.title.get(lang),
            "summary": c.summary.get(lang),
            "stack": c.stack,
            "when_to_use": c.when_to_use,
            "study_project": c.study_project,
        }
        for c in profile.cases
    ]
    return json.dumps(rows, ensure_ascii=False, indent=1)


def system_prompt(profile: Profile, lang: Lang) -> str:
    v = profile.voice
    ex = profile.executor
    template = SYSTEM_RU if lang == "ru" else SYSTEM_EN
    return template.format(
        name=ex.name.get(lang),
        title=ex.title.get(lang),
        tagline=ex.tagline.get(lang),
        word_min=v.word_limit[0],
        word_max=v.word_limit[1],
        tone=v.tone.get(lang),
        rules=_bullets(v.rules.get(lang)),
        stop_phrases=", ".join(f"«{s}»" if lang == "ru" else f'"{s}"' for s in v.stop_phrases.get(lang)),
        yo_rule="Букву «ё» не используй, всегда пиши «е». " if v.forbid_yo else "",
        max_dashes=v.max_long_dashes,
        tier_s=profile.tiers.S.get(lang),
        tier_m=profile.tiers.M.get(lang),
        tier_l=profile.tiers.L.get(lang),
        services=_bullets(profile.services.get(lang)),
        skills=", ".join(profile.skills) or "—",
        cases=_cases_json(profile, lang),
        payments=_bullets([f"{o.id}: {o.text.get(lang)}. {o.hint}" for o in profile.terms.payment_options]),
        blocks=_bullets([
            f"{b.id}: «{b.text.get(lang)}» — когда: {b.when}" if lang == "ru"
            else f'{b.id}: "{b.text.get(lang)}" — when: {b.when}'
            for b in profile.optional_blocks
        ]) or "—",
    )


def user_prompt(brief: Brief, feedback: list[str] | None = None) -> str:
    ru = brief.language == "ru"
    labels = (
        ("Бриф заказчика", "Компания", "Контактное лицо", "Отрасль", "Задача", "Бюджет", "Сроки", "Дополнительно", "не указан")
        if ru else
        ("Client brief", "Company", "Contact", "Industry", "Task", "Budget", "Timeline", "Notes", "not specified")
    )
    title, company, contact, industry, task, budget, deadline, notes, na = labels
    lines = [
        f"## {title}",
        f"{company}: {brief.company}",
        f"{contact}: {brief.contact_name or na}",
        f"{industry}: {brief.industry}",
        f"{budget}: {brief.budget or na}",
        f"{deadline}: {brief.deadline or na}",
        f"{task}:\n{brief.task}",
    ]
    if brief.notes:
        lines.append(f"{notes}:\n{brief.notes}")
    if feedback:
        head = (
            "## Предыдущий вариант не прошел проверку. Исправь и верни КП целиком:"
            if ru else
            "## The previous draft failed these checks. Fix them and return the full proposal:"
        )
        lines += ["", head, _bullets(feedback)]
    return "\n".join(lines)
