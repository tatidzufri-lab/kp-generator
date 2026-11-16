import json
from datetime import date
from pathlib import Path

import pytest

from kp.config import Settings, TierCost, load_settings
from kp.models import Brief, Proposal
from kp.pricing import calculate, format_money
from kp.profiles import load_profile
from kp.render import days_label, format_date, mix, render_html
from kp.service import create_proposal
from kp.storage import get_record, list_history, slugify

ROOT = Path(__file__).resolve().parent.parent

SETTINGS = Settings(
    rate_rub=500, rate_usd=12, usd_rub=80, hours_per_client_day=4, test_multiplier=3,
    tiers={"S": TierCost(1, 2, 10), "M": TierCost(2.5, 3, 30), "L": TierCost(6, 5, 75)},
)


def brief(lang="ru") -> Brief:
    return Brief.model_validate_json((ROOT / f"examples/brief_{lang}.json").read_text(encoding="utf-8"))


def proposal(profile_id="tatiana", lang="ru") -> Proposal:
    return Proposal.model_validate_json((ROOT / f"fixtures/mock_{profile_id}_{lang}.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- стоимость

def test_pricing_matches_pricing_md():
    # мок: этапы M, S, S
    pr = calculate(proposal(), SETTINGS, "ru")
    assert [s.hours for s in pr.stages] == [10.5, 5, 5]
    # M: 10.5 ч × 500 + $30 × 80 = 7650 → 8000; S: 5 × 500 + 800 = 3300 → 3500
    assert [s.price for s in pr.stages] == [8000, 3500, 3500]
    assert pr.total_price == 15000 and pr.currency == "RUB"
    assert [s.days for s in pr.stages] == [3, 2, 2] and pr.total_days == 8


def test_pricing_usd():
    pr = calculate(proposal(lang="en"), SETTINGS, "en")
    # M: 10.5 × 12 + 30 = 156 → 160; S: 5 × 12 + 10 = 70
    assert [s.price for s in pr.stages] == [160, 70, 70]
    assert pr.currency == "USD" and pr.total_price == 300


def test_rate_from_env(monkeypatch):
    monkeypatch.setenv("KP_RATE_RUB", "1000")
    monkeypatch.setenv("KP_TIER_S", "2,2,0")
    s = load_settings()
    assert s.rate_rub == 1000 and s.tiers["S"].agent_hours == 2


def test_bad_env_value(monkeypatch):
    monkeypatch.setenv("KP_TIER_M", "много")
    with pytest.raises(ValueError):
        load_settings()


def test_money_and_days_format():
    assert format_money(15000, "RUB") == "15 000 ₽"
    assert format_money(1885, "USD") == "$1,885"
    assert [days_label(n, "ru") for n in (1, 3, 5, 11, 21, 22)] == [
        "1 рабочий день", "3 рабочих дня", "5 рабочих дней",
        "11 рабочих дней", "21 рабочий день", "22 рабочих дня",
    ]
    assert days_label(1, "en") == "1 business day" and days_label(8, "en") == "8 business days"
    assert format_date(date(2026, 11, 16), "ru") == "16 ноября 2026"


def test_mix():
    assert mix("#000000", "#ffffff", 0.5) == "#808080"
    assert mix("#1F364D", "#FAF8F4", 1) == "#1f364d"


# ---------------------------------------------------------------- HTML

def test_html_uses_profile_facts():
    prof = load_profile("tatiana")
    p = proposal()
    html = render_html(brief(), prof, p, calculate(p, SETTINGS, "ru"))
    case = prof.case("lead-qualifier")
    assert case.results.ru[0] in html            # цифры кейса из профиля, а не от LLM
    assert "15 000 ₽" in html
    assert "Демо-профиль" not in html
    assert '--heading: "Inter"' in html          # в Space Grotesk нет кириллицы
    assert "color-mix" not in html               # WeasyPrint его не понимает


def test_html_en_and_demo():
    prof = load_profile("demo_agency")
    p = proposal("demo_agency", "en")
    html = render_html(brief("en"), prof, p, calculate(p, SETTINGS, "en"))
    assert "Demo profile" in html and '--heading: "Space Grotesk"' in html
    assert "$" in html and "₽" not in html


def test_study_project_label():
    prof = load_profile("tatiana")
    data = json.loads(proposal().model_dump_json())
    data["relevant_cases"] = [{"case_id": "business-reports", "why_relevant": "Тоже отчеты."}]
    p = Proposal.model_validate(data)
    html = render_html(brief(), prof, p, calculate(p, SETTINGS, "ru"))
    assert "учебный проект" in html


# ---------------------------------------------------------------- хранение

def test_slugify():
    assert slugify("Сеть салонов «Лаванда»") == "set-salonov-lavanda"
    assert slugify("!!!") == "client"


def test_full_cycle_and_history(tmp_path):
    r1 = create_proposal(brief(), "tatiana", SETTINGS, force_mock=True, output_root=tmp_path)
    r2 = create_proposal(brief(), "tatiana", SETTINGS, force_mock=True, output_root=tmp_path)
    assert r1.id != r2.id  # в одну секунду — разные папки
    for r in (r1, r2):
        assert r.pdf.read_bytes().startswith(b"%PDF")
        for name in ("brief", "proposal", "pricing", "meta"):
            assert (r.path / f"{name}.json").exists()
    assert r1.meta["total_price"] == 15000 and r1.meta["mode"] == "mock"
    assert {r.id for r in list_history(tmp_path)} == {r1.id, r2.id}


def test_get_record_rejects_traversal(tmp_path):
    assert get_record("../etc", tmp_path) is None
    assert get_record("2026-11-16_x_120000", tmp_path) is None
