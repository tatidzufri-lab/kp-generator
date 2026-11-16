import json
from pathlib import Path

import pytest

from kp import prompts
from kp.cli import main as cli_main
from kp.generator import GenerationError, MockDrafter, OpenAIDrafter, Usage, generate
from kp.models import Brief, Proposal
from kp.profiles import load_profile
from kp.tov_lint import autofix, document_text, lint, word_count

ROOT = Path(__file__).resolve().parent.parent


def brief(lang="ru") -> Brief:
    return Brief.model_validate_json((ROOT / f"examples/brief_{lang}.json").read_text(encoding="utf-8"))


def fixture(profile_id="tatiana", lang="ru") -> dict:
    return json.loads((ROOT / f"fixtures/mock_{profile_id}_{lang}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tatiana():
    return load_profile("tatiana")


class FakeDrafter:
    """Отдает заранее заданные ответы по очереди и запоминает feedback."""

    mode, model = "live", "fake"

    def __init__(self, *responses: dict):
        self.responses = list(responses)
        self.feedbacks: list = []

    def draft(self, brief, profile, feedback):
        self.feedbacks.append(feedback)
        return Proposal.model_validate(self.responses.pop(0)), Usage(100, 50, 20)


# ---------------------------------------------------------------- mock

@pytest.mark.parametrize("profile_id", ["tatiana", "demo_agency"])
@pytest.mark.parametrize("lang", ["ru", "en"])
def test_mock_fixtures_pass_all_checks(profile_id, lang):
    profile = load_profile(profile_id)
    result = generate(brief(lang), profile, MockDrafter())
    assert result.mode == "mock" and result.attempts == 1 and result.warnings == []


def test_mock_substitutes_brief(tatiana, tmp_path):
    data = fixture()
    data["project_title"] = "Бот для {company}"
    data["goal"] = "{contact} просит {unknown}. " + data["goal"]
    (tmp_path / "mock_tatiana_ru.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    p, _ = MockDrafter(tmp_path).draft(brief(), tatiana, None)
    assert p.project_title == "Бот для Сеть салонов «Лаванда»"
    assert p.goal.startswith("Ирина, управляющая просит {unknown}.")  # неизвестное поле не ломает подстановку


# ---------------------------------------------------------------- tov_lint

def test_autofix_yo_and_emoji(tatiana):
    data = fixture()
    data["goal"] = "Всё будет готово 🚀 ещё до сезона. " + data["goal"]
    p = autofix(Proposal.model_validate(data), tatiana)
    assert "ё" not in p.goal and "🚀" not in p.goal
    assert p.relevant_cases[0].case_id == "lead-qualifier"  # id не трогаются


def test_lint_catches_patterns(tatiana):
    data = fixture()
    data["solution_items"][0] = "Бот — это не просто чат, а полноценный ассистент — и он реально работает — круглосуточно"
    codes = {i.code for i in lint(Proposal.model_validate(data), tatiana, "ru")}
    assert {"ai_pattern", "dashes", "stop_phrase"} <= codes


def test_lint_en_pattern(tatiana):
    data = fixture(lang="en")
    data["goal"] = "This is not a chatbot, but a real assistant. " + data["goal"]
    assert any(i.code == "ai_pattern" for i in lint(Proposal.model_validate(data), tatiana, "en"))


def test_word_count_includes_template_parts(tatiana):
    p = Proposal.model_validate(fixture())
    text = document_text(p, tatiana, "ru")
    case = tatiana.case("lead-qualifier")
    assert case.results.ru[0] in text
    assert tatiana.terms.included.ru[0] in text
    assert 250 <= word_count(text) <= 400


def test_lint_too_long(tatiana):
    data = fixture()
    data["goal"] = " ".join(["слово"] * 300)
    assert any(i.code == "too_long" for i in lint(Proposal.model_validate(data), tatiana, "ru"))


# ---------------------------------------------------------------- конвейер

def test_retry_fixes_structure(tatiana):
    bad = fixture()
    bad["relevant_cases"] = [{"case_id": "invented", "why_relevant": "..."}]
    drafter = FakeDrafter(bad, fixture())
    result = generate(brief(), tatiana, drafter)
    assert result.attempts == 2 and result.warnings == []
    assert drafter.feedbacks[0] is None
    assert any("invented" in f for f in drafter.feedbacks[1])
    assert result.usage.input_tokens == 200


def test_persistent_structure_error_raises(tatiana):
    bad = fixture()
    bad["payment_option_id"] = "crypto"
    with pytest.raises(GenerationError) as e:
        generate(brief(), tatiana, FakeDrafter(bad, bad))
    assert any("crypto" in d for d in e.value.details)


def test_persistent_style_issue_becomes_warning(tatiana):
    bad = fixture()
    bad["goal"] = "Это ключевой этап для бизнеса. " + bad["goal"]
    result = generate(brief(), tatiana, FakeDrafter(bad, bad))
    assert result.attempts == 2
    assert any("ключевой" in w for w in result.warnings)


def test_openai_drafter_requires_model():
    with pytest.raises(GenerationError):
        OpenAIDrafter(api_key="sk-test", model="")


# ---------------------------------------------------------------- промпты

def test_system_prompt_has_profile_data(tatiana):
    s = prompts.system_prompt(tatiana, "ru")
    for c in tatiana.cases:
        assert c.id in s
    assert "prepay_50" in s and "Татьяна Дзюбас" in s
    import re
    assert re.findall(r"\{[a-z_]+\}", s) == ["{detail}"] * s.count("{detail}")  # все поля шаблона подставлены
    s_en = prompts.system_prompt(tatiana, "en")
    assert "Tetiana Dziubas" in s_en and "write the proposal in English" in s_en


def test_user_prompt_with_feedback():
    u = prompts.user_prompt(brief(), ["ошибка один"])
    assert "Сеть салонов" in u and "ошибка один" in u
    assert "Client brief" in prompts.user_prompt(brief("en"))


# ---------------------------------------------------------------- CLI

def test_cli_mock(tmp_path):
    code = cli_main(["generate", "--brief", str(ROOT / "examples/brief_en.json"),
                     "--profile", "tatiana", "--mock", "--out", str(tmp_path)])
    assert code == 0
    [record_dir] = list(tmp_path.iterdir())
    p = Proposal.model_validate_json((record_dir / "proposal.json").read_text(encoding="utf-8"))
    assert p.relevant_cases
    assert (record_dir / "proposal.pdf").stat().st_size > 10_000


def test_cli_bad_profile(tmp_path):
    code = cli_main(["generate", "--brief", str(ROOT / "examples/brief_ru.json"),
                     "--profile", "nope", "--mock", "--out", str(tmp_path)])
    assert code == 1
