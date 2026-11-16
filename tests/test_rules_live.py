"""Правила, найденные на живом прогоне (этап 6), и необязательный живой тест.

Живой тест ходит в OpenAI и стоит ~$0.02:
    KP_LIVE_TESTS=1 make test
"""

import json
import os
from pathlib import Path

import pytest

from kp.config import load_settings
from kp.generator import OpenAIDrafter, generate
from kp.models import Brief, Proposal, check_proposal
from kp.profiles import load_profile
from kp import prompts
from kp.tov_lint import lint

ROOT = Path(__file__).resolve().parent.parent


def fixture(lang="ru") -> dict:
    return json.loads((ROOT / f"fixtures/mock_tatiana_{lang}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tatiana():
    return load_profile("tatiana")


def test_last_stage_must_be_s(tatiana):
    # живой прогон: модели ставили «Тестирование и сдача» на L, хотя тесты уже в часах этапов
    data = fixture()
    data["stages"][-1]["tier"] = "L"
    errors = check_proposal(Proposal.model_validate(data), tatiana)
    assert any("последний этап" in e for e in errors)


def test_limitations_rejects_known_tech(tatiana):
    # живой прогон: «С YCLIENTS API и Google Таблицами я буду работать впервые»
    data = fixture()
    data["optional_blocks"] = [{"block_id": "limitations", "detail": "Google Sheets API и YCLIENTS API", "reason": "..."}]
    errors = check_proposal(Proposal.model_validate(data), tatiana)
    assert any("знакомые" in e and "Google Sheets API" in e for e in errors)


def test_limitations_allows_new_class(tatiana):
    data = fixture()
    data["optional_blocks"] = [{"block_id": "limitations", "detail": "1С:Предприятие", "reason": "..."}]
    assert check_proposal(Proposal.model_validate(data), tatiana) == []


def test_same_start_items(tatiana):
    # живой прогон gpt-6.1-terra: «Сделаю…», «Подключу…», «Настрою…», «Добавлю…»
    data = fixture()
    data["solution_items"] = [
        "Сделаю Telegram-бота с выбором салона",
        "Подключу прайс из Google Таблицы",
        "Настрою ответы на частые вопросы",
        "Добавлю запись в YCLIENTS",
    ]
    assert any(i.code == "same_start" for i in lint(Proposal.model_validate(data), tatiana, "ru"))


def test_prompt_mentions_skills_and_stage_rule(tatiana):
    s = prompts.system_prompt(tatiana, "ru")
    assert "Google Sheets API" in s and "всегда уровня S" in s
    assert "always tier S" in prompts.system_prompt(tatiana, "en")


@pytest.mark.skipif(os.getenv("KP_LIVE_TESTS") != "1", reason="живой запрос к OpenAI: KP_LIVE_TESTS=1")
@pytest.mark.parametrize("lang", ["ru", "en"])
def test_live_generation(tatiana, lang):
    s = load_settings()
    assert s.openai_api_key and s.openai_model, "нужны OPENAI_API_KEY и OPENAI_MODEL в .env"
    brief = Brief.model_validate_json((ROOT / f"examples/brief_{lang}.json").read_text(encoding="utf-8"))
    result = generate(brief, tatiana, OpenAIDrafter(s.openai_api_key, s.openai_model))
    assert result.mode == "live"
    assert check_proposal(result.proposal, tatiana) == []
    assert result.usage.input_tokens > 0
