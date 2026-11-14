"""Optional dashboard and read-only AI analysis API."""

from __future__ import annotations

import csv
import json
import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, model_validator

from .rag_index import LLMClient, Retriever, ask_sql, explain_violation
from .scheduler import reschedule_with_downtime
from .validator import validate

DATA_DIR = Path(os.getenv("SCHEDULING_DATA_DIR", "output"))
app = FastAPI(title="Production Scheduling Lab", version="1.0.0")


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class ExplanationRequest(BaseModel):
    schedule_id: str | None = Field(default=None, pattern=r"^SCH-2026-\d{6}$")
    issue_type: str | None = None
    issue: dict | None = None

    @model_validator(mode="after")
    def one_evidence_source(self):
        if (self.schedule_id is None) == (self.issue is None):
            raise ValueError("Provide exactly one of schedule_id or issue")
        return self


class WhatIfRequest(BaseModel):
    machine_id: str
    start_min: int = Field(ge=0)
    duration_min: int = Field(gt=0, le=60 * 24 * 30)


def _load():
    database = DATA_DIR / "clean" / "seed.sqlite"
    if not database.exists():
        raise HTTPException(503, f"Dataset not found at {database}; run the generate command first")
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        data = {}
        for (table,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            data[table] = [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]
    report_path = DATA_DIR / "clean" / "validation_summary.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else validate(data)
    return data, report


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """<!doctype html><html><head><title>Production Scheduling Lab</title>
<style>body{font:16px system-ui;max-width:980px;margin:40px auto;padding:0 20px;color:#172033}
article{padding:18px;border:1px solid #d5dbe5;border-radius:10px;margin:12px 0}.metric{font-size:26px;font-weight:700}
button{padding:9px 14px}pre{white-space:pre-wrap;background:#f4f6fa;padding:14px}</style></head>
<body><h1>Production Scheduling Lab</h1><p>Deterministic production plan, validation evidence, and optional AI analysis.</p>
<article><h2>Schedule KPIs</h2><pre id="summary">Loading...</pre></article>
<article><h2>Validator findings</h2><pre id="issues">Loading...</pre></article>
<article><h2>Ask the data</h2><input id="q" style="width:75%" placeholder="Which orders are late?">
<button onclick="ask()">Ask</button><pre id="answer"></pre></article>
<script>
async function load(){for(const id of ['summary','issues']){const r=await fetch('/api/'+(id==='summary'?'summary':'issues'));document.getElementById(id).textContent=JSON.stringify(await r.json(),null,2)}}
async function ask(){const r=await fetch('/api/ask-sql',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:document.getElementById('q').value})});document.getElementById('answer').textContent=JSON.stringify(await r.json(),null,2)}
load();</script></body></html>"""


@app.get("/api/summary")
def summary():
    _, report = _load()
    return {"schedule_id": report["schedule_id"], "valid": report["valid"], "metrics": report["metrics"]}


@app.get("/api/issues")
def issues():
    _, report = _load()
    return {"issues": report["issues"], "count": report["issue_count"]}


@app.get("/api/rules")
def rules():
    from .rag_index import RULES
    return {"rules": RULES}


@app.post("/api/explain")
def explain(request: ExplanationRequest):
    data, report = _load()
    if request.schedule_id:
        candidate_reports = [DATA_DIR / "clean" / "validation_summary.json"]
        candidate_reports.extend((DATA_DIR / "mutated").rglob("validation_summary.json"))
        matched_report = None
        for report_path in candidate_reports:
            candidate = json.loads(report_path.read_text(encoding="utf-8"))
            if candidate.get("schedule_id") == request.schedule_id:
                matched_report = candidate
                break
        if matched_report is None:
            raise HTTPException(404, "Validator evidence for this schedule_id was not found")
        report = matched_report
        findings = report.get("issues", [])
        if request.issue_type:
            findings = [item for item in findings if item["issue_type"] == request.issue_type]
        if not findings:
            raise HTTPException(404, "No matching validator issue exists for this schedule")
        issue = findings[0]
    else:
        issue = request.issue
    retriever = Retriever.from_dataset(data, report)
    try:
        return explain_violation(issue, retriever, LLMClient())
    except (RuntimeError, ValueError) as error:
        raise HTTPException(400, str(error)) from error


@app.post("/api/ask-sql")
def query(request: Question):
    try:
        with sqlite3.connect(f"file:{(DATA_DIR / 'clean' / 'seed.sqlite').resolve().as_posix()}?mode=ro", uri=True) as connection:
            return ask_sql(request.question, connection, LLMClient())
    except (RuntimeError, ValueError, sqlite3.Error) as error:
        raise HTTPException(400, str(error)) from error


@app.post("/api/what-if")
def what_if(request: WhatIfRequest):
    data, baseline = _load()
    schedule_id, output_dir = _allocate_what_if_directory()
    try:
        changed, schedules, consumption, events = reschedule_with_downtime(
            data, request.machine_id, request.start_min, request.duration_min, schedule_id,
        )
        report = validate(changed, schedules, consumption, schedule_id)
    except ValueError as error:
        output_dir.rmdir()
        raise HTTPException(400, str(error)) from error
    _write_records(output_dir / "operation_schedules.csv", schedules)
    _write_records(output_dir / "material_consumption_events.csv", consumption)
    _write_records(output_dir / "machine_downtime_events.csv", [changed["machine_downtime_events"][-1]])
    _write_records(output_dir / "schedule_events.csv", events)
    (output_dir / "validation_summary.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    old = baseline["metrics"]
    new = report["metrics"]
    return {
        "schedule_id": report["schedule_id"], "valid": report["valid"], "output": str(output_dir),
        "baseline": old, "what_if": new,
        "delta": {key: new[key] - old[key] for key in new if isinstance(new[key], (int, float))},
        "issues": report["issues"],
        "schedule_events": events,
    }


def _allocate_what_if_directory() -> tuple[str, Path]:
    root = DATA_DIR / "mutated" / "what_if"
    root.mkdir(parents=True, exist_ok=True)
    numbers = [1]
    for path in (DATA_DIR / "mutated").rglob("validation_summary.json"):
        try:
            numbers.append(int(json.loads(path.read_text(encoding="utf-8"))["schedule_id"][-6:]))
        except (KeyError, ValueError):
            continue
    for folder in root.iterdir():
        if folder.is_dir() and folder.name.startswith("SCH-2026-"):
            try:
                numbers.append(int(folder.name[-6:]))
            except ValueError:
                continue
    candidate = max(numbers) + 1
    while True:
        schedule_id = f"SCH-2026-{candidate:06d}"
        output_dir = root / schedule_id
        try:
            output_dir.mkdir()
            return schedule_id, output_dir
        except FileExistsError:
            candidate += 1


def _write_records(path: Path, rows: list[dict]):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
