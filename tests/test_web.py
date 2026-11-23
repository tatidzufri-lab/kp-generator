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


def test_ui_english_switch_and_persist(client):
    html = client.get("/?lang=en").get_data(as_text=True)
    assert 'lang="en"' in html
    assert "New commercial proposal" in html and "Generate proposal" in html
    assert "Tetiana Dziubas" in html and "Lampa Digital (demo)" in html
    assert 'value="en" checked' in html  # язык КП по умолчанию = язык интерфейса
    assert "Новое коммерческое предложение" not in html
    # выбор запоминается в сессии
    assert "History" in client.get("/history").get_data(as_text=True)
    # и переключается обратно
    assert "Новое коммерческое предложение" in client.get("/?lang=ru").get_data(as_text=True)


def test_ui_language_from_accept_language(client):
    html = client.get("/", headers={"Accept-Language": "en-US,en;q=0.9"}).get_data(as_text=True)
    assert "New commercial proposal" in html


def test_english_flow(client):
    client.get("/?lang=en")
    r = client.post("/generate", data={**example("en"), "profile": "tatiana"})
    assert r.status_code == 302
    page = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "Download PDF" in page and "Estimate" in page and "business days" in page
    assert "Скачать PDF" not in page
    r = client.post("/generate", data={"profile": "tatiana", "language": "en"})
    assert r.status_code == 400 and "Required field" in r.get_data(as_text=True)
    nf = client.get("/p/nope").get_data(as_text=True)
    assert "Not found" in nf
