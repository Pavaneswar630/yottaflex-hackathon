from pathlib import Path

from src import api


def test_what_if_allocates_unique_versions_and_persists_events(tmp_path, monkeypatch):
    baseline = {"metrics": {
        "makespan_min": 100, "scheduled_operations": 1, "infeasible_operations": 0,
        "total_processing_min": 10, "late_orders": 0, "total_lateness_min": 0,
        "max_order_lateness_min": 0,
    }}
    monkeypatch.setattr(api, "DATA_DIR", tmp_path)
    monkeypatch.setattr(api, "_load", lambda: ({"machine_downtime_events": []}, baseline))

    def fake_reschedule(data, machine_id, start_min, duration_min, schedule_id):
        downtime = {"downtime_id": "DOWN-TEST", "machine_id": machine_id, "start_min": start_min, "end_min": start_min + duration_min}
        event = {"schedule_event_id": f"SE-{schedule_id[-6:]}", "schedule_id": schedule_id, "event_type": "rescheduled"}
        changed = {"machine_downtime_events": [downtime]}
        schedules = [{"schedule_id": schedule_id, "operation_id": "OP-PROD-2026-000001-01"}]
        consumption = [{"schedule_id": schedule_id, "order_id": "PROD-2026-000001"}]
        return changed, schedules, consumption, [event]

    def fake_validate(changed, schedules, consumption, schedule_id):
        return {
            "schedule_id": schedule_id, "valid": True, "issues": [],
            "metrics": {**baseline["metrics"], "makespan_min": 110},
        }

    monkeypatch.setattr(api, "reschedule_with_downtime", fake_reschedule)
    monkeypatch.setattr(api, "validate", fake_validate)
    request = api.WhatIfRequest(machine_id="MACH-001", start_min=100, duration_min=60)

    first = api.what_if(request)
    second = api.what_if(request)
    assert first["schedule_id"] == "SCH-2026-000002"
    assert second["schedule_id"] == "SCH-2026-000003"
    event_path = Path(first["output"]) / "schedule_events.csv"
    assert event_path.read_text(encoding="utf-8").startswith("schedule_event_id,schedule_id,event_type")
    assert (Path(first["output"]) / "validation_summary.json").exists()
