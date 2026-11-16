import json
import textwrap
from pathlib import Path

import pytest
from openai.lib._pydantic import to_strict_json_schema
from pydantic import ValidationError

from kp.models import Brief, Proposal, check_proposal
from kp.profiles import ProfileError, list_profiles, load_profile

ROOT = Path(__file__).resolve().parent.parent


def make_proposal(**over) -> Proposal:
    data = {
        "project_title": "Бот для записи",
        "goal": "Администратор теряет заявки в переписке. Нужен бот, который принимает запись сам.",
        "solution_items": ["Бот записи", "Календарь врачей", "Напоминания", "Выгрузка в CRM"],
        "stack": ["Python", "aiogram"],
        "relevant_cases": [{"case_id": "lead-qualifier", "why_relevant": "Тоже бот, который собирает заявку."}],
        "stages": [
            {"name": "MVP", "content": "Запись и календарь", "tier": "M", "tier_reason": "Есть интеграция."},
            {"name": "Тестирование и сдача", "content": "Проверка и передача", "tier": "S", "tier_reason": "Типовой этап."},
        ],
        "payment_option_id": "prepay_50",
        "next_step": {"start": "через 2 рабочих дня", "client_needs": ["Доступ к CRM"]},
        "optional_blocks": [],
    }
    data.update(over)
    return Proposal.model_validate(data)


@pytest.fixture(scope="module")
def tatiana():
    return load_profile("tatiana")


def test_all_profiles_load():
    ids = list_profiles()
    assert {"tatiana", "demo_agency"} <= set(ids)
    for pid in ids:
        assert load_profile(pid).cases


def test_tatiana_cases_imported(tatiana):
    assert len(tatiana.cases) == 13
    study = {c.id for c in tatiana.cases if c.study_project}
    assert study == {"business-reports", "llm-fine-tuning"}
    for c in tatiana.cases:
        assert "учебный проект" not in c.title.ru.lower()
        assert c.url and c.url.en.startswith("https://tatidzufri.com/en/case/")


def test_demo_flag():
    assert load_profile("demo_agency").demo is True
    assert load_profile("tatiana").demo is False


def test_missing_profile():
    with pytest.raises(ProfileError):
        load_profile("nope")


def test_proposal_schema_is_strict_compatible():
    schema = to_strict_json_schema(Proposal)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_valid_proposal_passes(tatiana):
    assert check_proposal(make_proposal(), tatiana) == []


def test_unknown_case_and_payment_rejected(tatiana):
    p = make_proposal(
        relevant_cases=[{"case_id": "invented-case", "why_relevant": "..."}],
        payment_option_id="crypto",
    )
    errors = check_proposal(p, tatiana)
    assert any("invented-case" in e for e in errors)
    assert any("crypto" in e for e in errors)


def test_counts_and_detail_checked(tatiana):
    p = make_proposal(
        solution_items=["Только один пункт"],
        optional_blocks=[{"block_id": "limitations", "detail": " ", "reason": "Новая технология"}],
    )
    errors = check_proposal(p, tatiana)
    assert any(e.startswith("solution_items") for e in errors)
    assert any("limitations" in e and "detail" in e for e in errors)


def test_brief_validation():
    b = Brief(company="  TechCorp ", industry="IT", task="Нужно автоматизировать ответы на отзывы клиентов")
    assert b.company == "TechCorp" and b.language == "ru"
    with pytest.raises(ValidationError):
        Brief(company="X", industry="IT", task="коротко")
    with pytest.raises(ValidationError):
        Brief(company="X", industry="IT", task="Достаточно длинное описание задачи", language="de")


def test_import_cases_parsers(tmp_path):
    from scripts.import_cases import build_cases

    site = tmp_path / "Site"
    (site / "i18n").mkdir(parents=True)
    (site / "config.py").write_text(textwrap.dedent("""
        import os
        class Config:
            CASES = [{'id': 1, 'slug': 'demo-bot', 'tech': ['Python'], 'demo_link': 'https://t.me/x'}]
    """), encoding="utf-8")
    case = {"title": "Бот (учебный проект)", "short_desc": "Кратко", "results": ["+30%"], "study_project": True}
    (site / "i18n" / "cases_ru.json").write_text(json.dumps({"demo-bot": case}, ensure_ascii=False), encoding="utf-8")
    case_en = {**case, "title": "Bot (learning project)"}
    (site / "i18n" / "cases_en.json").write_text(json.dumps({"demo-bot": case_en}), encoding="utf-8")
    md = tmp_path / "cases.md"
    md.write_text("## КЕЙС №1 — Бот\n\n**Когда упоминать:** боты, SMM\n\n**Формулировка для письма:**\nсекрет\n", encoding="utf-8")

    [c] = build_cases(site, md)
    assert c["title"] == {"ru": "Бот", "en": "Bot"}
    assert c["study_project"] is True
    assert c["when_to_use"] == "боты, SMM"
    assert "секрет" not in json.dumps(c, ensure_ascii=False)
