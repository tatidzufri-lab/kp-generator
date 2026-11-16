"""Веб-интерфейс генератора КП.

    make run          # http://127.0.0.1:5050

Маршруты:
    GET  /                 форма брифа
    POST /generate         генерация → редирект на превью
    GET  /p/<id>           превью КП, расчет, предупреждения
    GET  /p/<id>/doc       само КП (HTML, грузится во фрейм превью)
    GET  /p/<id>/pdf       скачать PDF
    POST /p/<id>/regenerate  новый вариант по тому же брифу
    GET  /history          история КП
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_file, send_from_directory, url_for
from pydantic import ValidationError

from kp.config import ROOT, Settings, load_settings
from kp.generator import GenerationError
from kp.models import Brief, Proposal
from kp.pricing import Pricing, format_money
from kp.profiles import ProfileError, list_profiles, load_profile
from kp.render import FONTS_DIR, days_label, render_html
from kp.service import create_proposal
from kp.storage import OUTPUT_DIR, Record, get_record, list_history, slugify

FIELDS = ("company", "contact_name", "industry", "task", "budget", "deadline", "notes")

ERROR_TEXT = {
    "missing": "Обязательное поле",
    "string_too_short": "Слишком коротко: минимум {min_length} символов",
    "string_too_long": "Слишком длинно: максимум {max_length} символов",
    "literal_error": "Недопустимое значение",
}


def field_errors(e: ValidationError) -> dict[str, str]:
    out: dict[str, str] = {}
    for err in e.errors():
        name = str(err["loc"][0]) if err["loc"] else "form"
        ctx = err.get("ctx") or {}
        kind = "missing" if err["type"] == "string_too_short" and ctx.get("min_length") == 1 else err["type"]
        template = ERROR_TEXT.get(kind, err["msg"])
        out[name] = template.format(**ctx)
    return out


def create_app(settings: Settings | None = None, output_root: Path = OUTPUT_DIR) -> Flask:
    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(16)
    app.config["KP_SETTINGS"] = settings or load_settings()
    app.config["KP_OUTPUT"] = output_root

    def cfg() -> tuple[Settings, Path]:
        return app.config["KP_SETTINGS"], app.config["KP_OUTPUT"]

    def profiles() -> list[dict]:
        out = []
        for pid in list_profiles():
            p = load_profile(pid)
            out.append({"id": pid, "name": p.executor.name.ru, "demo": p.demo})
        return out

    def examples() -> dict:
        return {
            lang: json.loads((ROOT / f"examples/brief_{lang}.json").read_text(encoding="utf-8"))
            for lang in ("ru", "en")
        }

    def record_or_404(record_id: str) -> Record:
        record = get_record(record_id, cfg()[1])
        if record is None:
            abort(404)
        return record

    def run(brief: Brief, profile_id: str, force_mock: bool):
        settings, root = cfg()
        return create_proposal(brief, profile_id, settings, force_mock=force_mock, output_root=root)

    @app.context_processor
    def globals_():
        settings, _ = cfg()
        return {
            "mock_mode": settings.mock,
            "model_name": settings.openai_model or "модель не задана",
            "money": format_money,
        }

    @app.template_filter("dt")
    def dt(value: str) -> str:
        try:
            return datetime.fromisoformat(value).strftime("%d.%m.%Y %H:%M")
        except (TypeError, ValueError):
            return value or ""

    @app.get("/")
    def index():
        return render_template(
            "form.html", profiles=profiles(), values={"language": "ru", "profile": "tatiana"},
            errors={}, examples=examples(),
        )

    @app.post("/generate")
    def generate_view():
        form = request.form
        values = {k: form.get(k, "").strip() for k in FIELDS}
        values["language"] = form.get("language", "ru")
        values["profile"] = form.get("profile", "")
        values["force_mock"] = bool(form.get("force_mock"))

        def back(errors: dict, status: int = 400, details: list[str] | None = None):
            return render_template(
                "form.html", profiles=profiles(), values=values, errors=errors,
                examples=examples(), details=details or [],
            ), status

        if values["profile"] not in list_profiles():
            return back({"profile": "Выберите профиль исполнителя"})
        try:
            brief = Brief.model_validate({
                **{k: (values[k] or None) for k in FIELDS},
                "company": values["company"], "industry": values["industry"], "task": values["task"],
                "language": values["language"],
            })
        except ValidationError as e:
            return back(field_errors(e))

        try:
            record = run(brief, values["profile"], values["force_mock"])
        except GenerationError as e:
            return back({"form": str(e)}, 502, e.details)
        except ProfileError as e:
            return back({"form": str(e)}, 500)
        return redirect(url_for("preview", record_id=record.id))

    @app.get("/p/<record_id>")
    def preview(record_id: str):
        record = record_or_404(record_id)
        proposal = Proposal.model_validate(record.load_json("proposal"))
        pricing = Pricing.from_dict(record.load_json("pricing"))
        lang = record.meta["language"]
        rows = [
            {"stage": st, "cost": cost, "days": days_label(cost.days, lang)}
            for st, cost in zip(proposal.stages, pricing.stages)
        ]
        return render_template("preview.html", r=record, m=record.meta, pricing=pricing, rows=rows)

    @app.get("/p/<record_id>/doc")
    def document(record_id: str):
        record = record_or_404(record_id)
        brief = Brief.model_validate(record.load_json("brief"))
        html = render_html(
            brief,
            load_profile(record.meta["profile_id"]),
            Proposal.model_validate(record.load_json("proposal")),
            Pricing.from_dict(record.load_json("pricing")),
            created=datetime.fromisoformat(record.meta["created_at"]).date(),
            font_base=url_for("fonts", filename=""),
        )
        return html

    @app.get("/p/<record_id>/pdf")
    def pdf(record_id: str):
        record = record_or_404(record_id)
        name = f"KP_{slugify(record.meta['company'])}_{record.meta['created_at'][:10]}.pdf"
        return send_file(record.pdf, mimetype="application/pdf", as_attachment=True, download_name=name)

    @app.post("/p/<record_id>/regenerate")
    def regenerate(record_id: str):
        record = record_or_404(record_id)
        brief = Brief.model_validate(record.load_json("brief"))
        try:
            new = run(brief, record.meta["profile_id"], record.meta["mode"] == "mock")
        except (GenerationError, ProfileError) as e:
            flash(f"Не удалось сгенерировать заново: {e}")
            return redirect(url_for("preview", record_id=record_id))
        return redirect(url_for("preview", record_id=new.id))

    @app.get("/history")
    def history():
        return render_template("history.html", records=list_history(cfg()[1]))

    @app.get("/fonts/<path:filename>")
    def fonts(filename: str):
        return send_from_directory(FONTS_DIR, filename)

    @app.errorhandler(404)
    def not_found(_):
        return render_template("message.html", title="Не найдено", text="Такого КП нет в истории."), 404

    return app


app = create_app()
