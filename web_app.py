#!/usr/bin/env python3
"""Gmail 自动清理 Web 版。"""

from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stdout
from dataclasses import asdict

from flask import Flask, render_template, request

import gmail_cleanup_tool as tool

app = Flask(__name__)


def _build_config_from_form(form) -> tool.CleanupConfig:
    return tool.CleanupConfig(
        days_old=int(form.get("days_old", 30)),
        max_messages=int(form.get("max_messages", 200)),
        min_size_kb=int(form.get("min_size_kb", 40)),
        dry_run=form.get("dry_run", "true") == "true",
        monthly_day=int(form.get("monthly_day", 1)),
        monthly_hour=int(form.get("monthly_hour", 3)),
        ai_provider=form.get("ai_provider", "openai"),
        ai_model=form.get("ai_model", "gpt-4o-mini"),
        low_value_threshold=float(form.get("low_value_threshold", 0.45)),
    )


@app.route("/", methods=["GET"])
def index():
    cfg = tool.CleanupConfig()
    return render_template(
        "index.html",
        config=asdict(cfg),
        env_openai=bool(os.getenv("OPENAI_API_KEY")),
        cron_line="",
        output="",
        result=None,
        error="",
    )


@app.route("/cron", methods=["POST"])
def generate_cron():
    cfg = _build_config_from_form(request.form)
    script_path = request.form.get("script_path", os.path.abspath("gmail_cleanup_tool.py"))
    config_path = request.form.get("config_path", "config.json")
    cron_line = tool.generate_monthly_cron(script_path, config_path, cfg.monthly_day, cfg.monthly_hour)
    return render_template(
        "index.html",
        config=asdict(cfg),
        env_openai=bool(os.getenv("OPENAI_API_KEY")),
        cron_line=cron_line,
        output="",
        result=None,
        error="",
    )


@app.route("/run", methods=["POST"])
def run_cleanup():
    cfg = _build_config_from_form(request.form)
    credentials = request.form.get("credentials", "credentials.json")
    token = request.form.get("token", "token.json")
    output_buffer = io.StringIO()

    result = None
    error = ""
    try:
        with redirect_stdout(output_buffer):
            service = tool.get_gmail_service(credentials, token)
            scanned, deleted, freed = tool.cleanup(service, cfg)
        result = {
            "scanned": scanned,
            "deleted": deleted,
            "freed_mb": round(freed / 1024 / 1024, 2),
            "dry_run": cfg.dry_run,
        }
    except Exception as exc:
        error = str(exc)

    return render_template(
        "index.html",
        config=asdict(cfg),
        env_openai=bool(os.getenv("OPENAI_API_KEY")),
        cron_line="",
        output=output_buffer.getvalue(),
        result=result,
        error=error,
    )


@app.route("/config-template", methods=["GET"])
def config_template():
    return json.dumps(asdict(tool.CleanupConfig()), ensure_ascii=False, indent=2), 200, {
        "Content-Type": "application/json; charset=utf-8"
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
