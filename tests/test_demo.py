"""Публичный режим демо: лимиты живых генераций и видимость только своих КП."""

import dataclasses

import pytest

import app as app_module
from app import create_app
from kp.demo import DailyCounter
from tests.test_web import SETTINGS, example

DEMO = dataclasses.replace(
    SETTINGS, openai_api_key="test-key", openai_model="test-model",
    public_demo=True, demo_max_per_session=2, demo_max_per_day=3,
)


@pytest.fixture()
def demo_app(tmp_path, monkeypatch):
    """Демо с «живым» ключом, но генерация подменена на заготовку, чтобы не ходить в OpenAI."""
    real = app_module.create_proposal

    def fake(brief, profile_id, settings, *, force_mock=False, output_root=None, **kw):
        return real(brief, profile_id, settings, force_mock=True, output_root=output_root, **kw)

    monkeypatch.setattr(app_module, "create_proposal", fake)
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret")
    app = create_app(DEMO, output_root=tmp_path)
    app.config["TESTING"] = True
    return app


def generate(client, **extra):
    return client.post("/generate", data={**example(), "profile": "tatiana", **extra})


def test_session_limit(demo_app):
    c = demo_app.test_client()
    assert "осталось: <strong>2</strong>" in c.get("/").get_data(as_text=True)
    assert generate(c).status_code == 302
    assert generate(c).status_code == 302
    r = generate(c)
    assert r.status_code == 429
    assert "Лимит демо на эту сессию исчерпан" in r.get_data(as_text=True)
    # без API лимит не расходуется
    assert generate(c, force_mock="on").status_code == 302


def test_daily_limit_shared_between_sessions(demo_app):
    a, b = demo_app.test_client(), demo_app.test_client()
    assert generate(a).status_code == 302
    assert generate(a).status_code == 302
    assert generate(b).status_code == 302
    r = generate(b)
    assert r.status_code == 429
    assert "Дневной лимит демо исчерпан" in r.get_data(as_text=True)


def test_records_are_private(demo_app):
    a, b = demo_app.test_client(), demo_app.test_client()
    rid = generate(a).headers["Location"].rstrip("/").split("/")[-1]
    assert a.get(f"/p/{rid}").status_code == 200
    assert a.get(f"/p/{rid}/pdf").status_code == 200
    assert b.get(f"/p/{rid}").status_code == 404
    assert b.get(f"/p/{rid}/pdf").status_code == 404
    assert rid in a.get("/history").get_data(as_text=True)
    assert rid not in b.get("/history").get_data(as_text=True)
    assert "Мои КП" in b.get("/").get_data(as_text=True)


def test_daily_counter_resets_by_date(tmp_path):
    counter = DailyCounter(tmp_path / "usage.json", limit=2)
    counter.add()
    assert counter.left() == 1
    (tmp_path / "usage.json").write_text('{"2000-01-01": 99}')
    assert counter.left() == 2


def test_demo_requires_secret_key(tmp_path, monkeypatch):
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FLASK_SECRET_KEY"):
        create_app(DEMO, output_root=tmp_path)
