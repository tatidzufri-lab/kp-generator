import json
from pathlib import Path

import pytest

from app import create_app
from kp.config import Settings, TierCost

ROOT = Path(__file__).resolve().parent.parent

SETTINGS = Settings(
    rate_rub=500, rate_usd=12, usd_rub=80, hours_per_client_day=4, test_multiplier=3,
    tiers={"S": TierCost(1, 2, 10), "M": TierCost(2.5, 3, 30), "L": TierCost(6, 5, 75)},
)  # без ключа → mock


@pytest.fixture()
def client(tmp_path):
    app = create_app(SETTINGS, output_root=tmp_path)
    app.config["TESTING"] = True
    return app.test_client()


def example(lang="ru") -> dict:
    data = json.loads((ROOT / f"examples/brief_{lang}.json").read_text(encoding="utf-8"))
    return {k: v or "" for k, v in data.items()}


def test_form_page(client):
    r = client.get("/")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Татьяна Дзюбас" in html and "Лампа Digital (демо)" in html
    assert "Без API: заготовки" in html
    assert "Sunset Bay Boutique Hotel" in html  # примеры для кнопки «Заполнить пример» (JSON, кириллица экранирована)


def test_generate_preview_pdf_history(client):
    r = client.post("/generate", data={**example(), "profile": "tatiana"})
    assert r.status_code == 302
    url = r.headers["Location"]
    rid = url.rstrip("/").split("/")[-1]

    page = client.get(url).get_data(as_text=True)
    assert "Скачать PDF" in page and "Расчет" in page and "15 000 ₽" in page

    doc = client.get(f"/p/{rid}/doc").get_data(as_text=True)
    assert 'src: url("/fonts/inter/Inter-Regular.ttf")' in doc
    assert client.get("/fonts/inter/Inter-Regular.ttf").status_code == 200

    pdf = client.get(f"/p/{rid}/pdf")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")
    assert "KP_set-salonov-lavanda" in pdf.headers["Content-Disposition"]

    hist = client.get("/history").get_data(as_text=True)
    assert "Сеть салонов «Лаванда»" in hist and "заготовка" in hist


def test_regenerate_creates_new_record(client):
    rid = client.post("/generate", data={**example("en"), "profile": "demo_agency"}).headers["Location"].split("/")[-1]
    r = client.post(f"/p/{rid}/regenerate")
    assert r.status_code == 302 and r.headers["Location"].split("/")[-1] != rid


def test_validation_errors_keep_values(client):
    data = {**example(), "profile": "tatiana", "company": "", "task": "коротко"}
    r = client.post("/generate", data=data)
    html = r.get_data(as_text=True)
    assert r.status_code == 400
    assert "Обязательное поле" in html and "минимум 20 символов" in html
    assert "Салоны красоты" in html  # введенное не потерялось


def test_unknown_profile(client):
    r = client.post("/generate", data={**example(), "profile": "../../etc"})
    assert r.status_code == 400 and "Выберите профиль" in r.get_data(as_text=True)


def test_missing_record_404(client):
    assert client.get("/p/2026-01-01_nope_000000").status_code == 404
    assert client.get("/p/..%2F..%2Fetc").status_code == 404
    assert client.get("/p/x/pdf").status_code == 404
