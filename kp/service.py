"""Полный цикл: бриф → КП → стоимость → HTML/PDF → история.

Одна точка входа для веба, CLI и скилла.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from kp.config import Settings
from kp.generator import Drafter, generate, make_drafter
from kp.models import Brief
from kp.pricing import calculate
from kp.profiles import load_profile
from kp.render import render_html, render_pdf
from kp.storage import OUTPUT_DIR, Record, get_record, new_record_dir, write_json


def create_proposal(
    brief: Brief,
    profile_id: str,
    settings: Settings,
    *,
    force_mock: bool = False,
    drafter: Drafter | None = None,
    output_root: Path = OUTPUT_DIR,
) -> Record:
    profile = load_profile(profile_id)
    drafter = drafter or make_drafter(settings, force_mock=force_mock)
    result = generate(brief, profile, drafter)
    pricing = calculate(result.proposal, settings, brief.language)

    now = datetime.now()
    path = new_record_dir(brief.company, now, output_root)
    meta = {
        "created_at": now.isoformat(timespec="seconds"),
        "company": brief.company,
        "profile_id": profile.id,
        "profile_name": profile.executor.name.get(brief.language),
        "demo_profile": profile.demo,
        "language": brief.language,
        "project_title": result.proposal.project_title,
        "mode": result.mode,
        "model": result.model,
        "attempts": result.attempts,
        "warnings": result.warnings,
        "usage": vars(result.usage),
        "total_price": pricing.total_price,
        "currency": pricing.currency,
        "total_days": pricing.total_days,
    }
    write_json(path, "brief", brief.model_dump())
    write_json(path, "proposal", result.proposal.model_dump())
    write_json(path, "pricing", pricing.to_dict())

    html = render_html(brief, profile, result.proposal, pricing, created=now.date())
    (path / "proposal.html").write_text(html, encoding="utf-8")
    render_pdf(html, path / "proposal.pdf")
    write_json(path, "meta", meta)  # последним: запись без meta не видна в истории

    record = get_record(path.name, output_root)
    assert record is not None
    return record
