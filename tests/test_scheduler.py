from src.scheduler import reschedule_with_downtime
from src.validator import validate


def test_baseline_counts_and_hard_constraints(small_data):
    assert len(small_data["operations"]) == 160
    assert len(small_data["production_orders"]) == 40
    result = validate(small_data)
    assert result["valid"], result["issues"][:5]
    assert result["metrics"]["scheduled_operations"] == 160
    assert result["metrics"]["makespan_min"] > 0
    operations = {row["operation_id"]: row for row in small_data["operations"]}
    orders = {row["order_id"]: row for row in small_data["production_orders"]}
    finish = {}
    for row in small_data["operation_schedules"]:
        order_id = operations[row["operation_id"]]["order_id"]
        finish[order_id] = max(finish.get(order_id, 0), row["end_min"])
    lateness = [max(0, finish[order_id] - order["due_min"]) for order_id, order in orders.items()]
    assert result["metrics"]["late_orders"] == sum(value > 0 for value in lateness)
    assert result["metrics"]["total_lateness_min"] == sum(lateness)


def test_what_if_creates_a_traced_schedule_version_without_mutating_baseline(small_data):
    baseline_schedules = list(small_data["operation_schedules"])
    changed, schedules, consumption, events = reschedule_with_downtime(
        small_data, "MACH-001", 1000, 120,
    )
    assert schedules
    assert events[0]["event_type"] == "rescheduled"
    assert events[0]["schedule_id"] == schedules[0]["schedule_id"] == "SCH-2026-000002"
    assert changed["machine_downtime_events"][-1]["machine_id"] == "MACH-001"
    assert small_data["operation_schedules"] == baseline_schedules
