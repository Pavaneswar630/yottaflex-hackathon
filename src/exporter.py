"""Portable CSV, JSON, SQLite, documentation, and checksum exports."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .schemas import ENTITIES, FOREIGN_KEYS, UNIQUE_KEYS, data_dictionary
from .validator import validate


def dataset_hashes(data: dict[str, list[dict]]) -> dict[str, str]:
    hashes = {}
    for table, rows in sorted(data.items()):
        canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        hashes[table] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return hashes


def _json_default(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def export_dataset(data: dict[str, list[dict[str, Any]]], output: Path, report: dict,
                   scenarios: dict[str, dict], ground_truth: list[dict], hashes: dict[str, str],
                   seed: int, parameters: dict, reproducibility: dict) -> dict[str, str]:
    output.mkdir(parents=True, exist_ok=True)
    clean_dir = output / "clean"
    clean_dir.mkdir(exist_ok=True)
    for table, rows in data.items():
        _write_csv(clean_dir / f"{table}.csv", rows)
        (clean_dir / f"{table}.json").write_text(json.dumps(rows, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")
    _write_sqlite(data, clean_dir / "seed.sqlite")
    _write_sql(data, clean_dir / "seed.sql")
    (clean_dir / "validation_summary.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (clean_dir / "reproducibility.json").write_text(json.dumps(reproducibility, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (clean_dir / "dataset_checksums.json").write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    docs_dir = output.parent / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    dictionary = data_dictionary()
    (docs_dir / "data_dictionary.json").write_text(json.dumps(dictionary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_dictionary_markdown(dictionary, docs_dir / "data_dictionary.md")
    truth_dir = output / "ground_truth"
    truth_dir.mkdir(exist_ok=True)
    _write_csv(truth_dir / "ground_truth.csv", ground_truth)
    scenario_dir = output / "mutated"
    scenario_dir.mkdir(exist_ok=True)
    for issue_type, scenario in scenarios.items():
        folder = scenario_dir / issue_type
        folder.mkdir(exist_ok=True)
        _write_csv(folder / "operation_schedules.csv", scenario["operation_schedules"])
        _write_csv(folder / "material_consumption_events.csv", scenario["material_consumption_events"])
        scenario_report = validate(
            data,
            scenario["operation_schedules"],
            scenario["material_consumption_events"],
            scenario["schedule_id"],
        )
        (folder / "validation_summary.json").write_text(
            json.dumps(scenario_report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    file_hashes = {}
    for path in sorted(p for p in output.rglob("*") if p.is_file()):
        file_hashes[str(path.relative_to(output)).replace("\\", "/")] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "generator": "production_scheduler",
        "seed": seed,
        "parameters": parameters,
        "epoch": "2026-01-01T00:00:00Z",
        "provenance": "Entirely synthetic records; no external data used. Public production-data models informed schema only.",
        "input_feature_policy": "Ground truth is written separately and is not included in data/clean or AI retrieval documents.",
        "files_sha256": file_hashes,
    }
    (docs_dir / "source_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (docs_dir / "source_manifest.md").write_text(
        "# Source manifest\n\n"
        f"- Generator: `{manifest['generator']}`\n- Seed: `{seed}`\n"
        f"- Parameters: `{json.dumps(parameters, sort_keys=True)}`\n"
        f"- Epoch: `{manifest['epoch']}`\n- Provenance: {manifest['provenance']}\n"
        f"- Ground-truth policy: {manifest['input_feature_policy']}\n"
        "- Per-file SHA-256 checksums are recorded in `source_manifest.json`.\n",
        encoding="utf-8",
    )
    return file_hashes


def _write_dictionary_markdown(dictionary: dict, path: Path):
    lines = [
        "# Data dictionary",
        "",
        f"Epoch: `{dictionary['epoch']}`. Time unit: {dictionary['time_unit']}.",
        "",
        "## Entities",
        "",
    ]
    for entity, spec in dictionary["entities"].items():
        lines.extend([
            f"### {entity}", "", f"Primary key: `{spec['primary_key']}`.",
            f"Unique constraints: `{spec['unique_constraints']}`.", "",
            "| Field | Type | Required | Allowed values | Units | Unique | Validation |",
            "|---|---|---:|---|---|---:|---|",
        ])
        for field in spec["fields"]:
            units = field["units"] or ""
            rule = field["validation"].replace("|", "\\|")
            allowed = ", ".join(str(value) for value in field["allowed_values"]) if field["allowed_values"] else ""
            lines.append(
                f"| `{field['name']}` | {field['type']} | {'yes' if field['required'] else 'no'} "
                f"| {allowed} | {units} | {'yes' if field['unique'] else 'no'} | {rule} |"
            )
        lines.append("")
    lines.extend(["## Relationships", "", "| From | To | Cardinality | Optional |", "|---|---|---|---:|"])
    for relation in dictionary["relationships"]:
        lines.append(f"| `{relation['from']}` | `{relation['to']}` | {relation['cardinality']} | {'yes' if relation['optional'] else 'no'} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict]):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_sqlite(data: dict[str, list[dict]], path: Path):
    if path.exists():
        path.unlink()
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for table, rows in data.items():
            spec = ENTITIES[table]
            field_names = list(spec["fields"])
            connection.execute(_create_table_sql(table))
            if rows:
                placeholders = ",".join("?" for _ in field_names)
                names = ",".join(f'"{field}"' for field in field_names)
                connection.executemany(
                    f'INSERT INTO "{table}" ({names}) VALUES ({placeholders})',
                    [tuple(_sqlite_value(row.get(field)) for field in field_names) for row in rows],
                )


def _sqlite_value(value):
    return int(value) if isinstance(value, bool) else value


def _write_sql(data: dict[str, list[dict]], path: Path):
    statements = ["PRAGMA foreign_keys = ON;", "BEGIN TRANSACTION;"]
    order = [name for name in ENTITIES if name in data]
    for table in order:
        statements.append(_create_table_sql(table) + ";")
    for table in order:
        rows = data[table]
        fields = list(ENTITIES[table]["fields"])
        for row in rows:
            values = ", ".join(_sql_literal(row.get(field)) for field in fields)
            names = ", ".join(f'"{field}"' for field in fields)
            statements.append(f'INSERT INTO "{table}" ({names}) VALUES ({values});')
    statements.append("COMMIT;")
    path.write_text("\n".join(statements) + "\n", encoding="utf-8")


def _create_table_sql(table: str) -> str:
    spec = ENTITIES[table]
    columns = []
    for field, metadata in spec["fields"].items():
        sql_type = "INTEGER" if metadata[0] in ("integer", "boolean", "enum") else ("REAL" if metadata[0] == "number" else "TEXT")
        columns.append(f'"{field}" {sql_type}')
    columns.append(f'PRIMARY KEY ("{spec["pk"]}")')
    for field, parent, parent_key in FOREIGN_KEYS.get(table, ()):
        columns.append(f'FOREIGN KEY ("{field}") REFERENCES "{parent}" ("{parent_key}")')
    for fields in UNIQUE_KEYS.get(table, ()):
        quoted_fields = ", ".join('"' + field + '"' for field in fields)
        columns.append(f"UNIQUE ({quoted_fields})")
    return f'CREATE TABLE "{table}" ({", ".join(columns)})'


def _sql_literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"
