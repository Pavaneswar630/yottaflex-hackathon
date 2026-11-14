"""Relational, arithmetic, lifecycle, and hard-constraint validation."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from pydantic import ValidationError

from .schemas import ENTITIES, FOREIGN_KEYS, MODEL_BY_TABLE, UNIQUE_KEYS


def validate(data: dict[str, list[dict[str, Any]]], schedule_rows: list[dict] | None = None,
             consumption_rows: list[dict] | None = None, schedule_id: str = "SCH-2026-000001") -> dict:
    """Validate one schedule against generated inputs and return explicit evidence."""
    schedules = schedule_rows if schedule_rows is not None else data["operation_schedules"]
    consumptions = consumption_rows if consumption_rows is not None else data["material_consumption_events"]
    issues: list[dict[str, Any]] = []

    def report(issue_type: str, entities: list[str], detail: str):
        issues.append({"issue_type": issue_type, "affected_entity_ids": entities, "detail": detail})

    for table, spec in ENTITIES.items():
        rows = data.get(table, [])
        key = spec["pk"]
        keys = [r.get(key) for r in rows]
        duplicates = [value for value, count in Counter(keys).items() if count > 1]
        if duplicates:
            report("duplicate_primary_key", [str(x) for x in duplicates], f"{table}.{key} is not unique")
        for unique_fields in UNIQUE_KEYS.get(table, ()):
            seen = set()
            for row in rows:
                values = tuple(row.get(field) for field in unique_fields)
                if values in seen:
                    report(
                        "duplicate_unique_constraint",
                        [str(row.get(key))],
                        f"{table}{unique_fields} must be unique; duplicate values {values}",
                    )
                seen.add(values)

    for table, relations in FOREIGN_KEYS.items():
        rows = data.get(table, [])
        for field, parent, parent_key in relations:
            parent_ids = {row.get(parent_key) for row in data.get(parent, [])}
            for row in rows:
                value = row.get(field)
                if value is not None and value not in parent_ids:
                    report("foreign_key_violation", [str(row.get(ENTITIES[table]["pk"]), value)], f"{table}.{field} references missing {parent}.{parent_key}")

    for table, model in MODEL_BY_TABLE.items():
        for row in data.get(table, []):
            try:
                model.model_validate(row)
            except ValidationError as error:
                report(
                    "schema_violation",
                    [str(row.get(ENTITIES[table]["pk"], "unknown"))],
                    f"{table} does not match its Pydantic schema: {error.errors(include_url=False)}",
                )

    operations = {r["operation_id"]: r for r in data["operations"]}
    orders = {r["order_id"]: r for r in data["production_orders"]}
    products = {r["sku"]: r for r in data["products"]}
    lots = {r["lot_id"]: r for r in data["inventory_lots"]}
    step_by_id = {r["routing_step_id"]: r for r in data["routing_steps"]}
    machine_by_id = {r["machine_id"]: r for r in data["machines"]}
    eligibility = {(r["routing_step_id"], r["machine_id"]) for r in data["machine_eligibility"]}
    tooling_assignments = {(r["routing_step_id"], r["tooling_id"]) for r in data["tooling_assignments"]}
    tools = {r["tooling_id"]: r["tooling_group"] for r in data["tooling"]}
    calendars = defaultdict(list)
    for row in data["machine_calendars"]:
        calendars[row["machine_id"]].append((row["shift_start_min"], row["shift_end_min"]))
    downtime = defaultdict(list)
    for row in data["machine_downtime_events"]:
        downtime[row["machine_id"]].append((row["start_min"], row["end_min"]))
    changeovers = {(r["machine_id"], r["from_family"], r["to_family"]): r["setup_min"] for r in data["changeover_matrix"]}
    schedule_by_op = {}
    scheduled_rows = [r for r in schedules if r["status"] == "scheduled"]
    for row in schedules:
        if row["schedule_id"] != schedule_id:
            continue
        op = operations.get(row["operation_id"])
        if not op:
            continue
        schedule_by_op[row["operation_id"]] = row
        if row["status"] == "infeasible":
            if not row.get("infeasibility_reason"):
                report("missing_infeasibility_reason", [row["operation_id"]], "Unscheduled operation has no explanation")
            continue
        machine_id = row["machine_id"]
        if machine_id not in machine_by_id:
            continue
        if (op["routing_step_id"], machine_id) not in eligibility:
            report("ineligible_machine", [row["operation_id"], machine_id], "Assigned machine is not eligible for the routing step")
        if op.get("tooling_group") and tools.get(row.get("tooling_id")) != op["tooling_group"]:
            report("tooling_mismatch", [row["operation_id"]], "Required shared tooling is missing or incompatible")
        if op.get("tooling_group") and (op["routing_step_id"], row.get("tooling_id")) not in tooling_assignments:
            report("tooling_mismatch", [row["operation_id"]], "Assigned tool is not eligible for the routing step")
        start, end = row["start_min"], row["end_min"]
        block_start = row["setup_start_min"]
        if end - start != op["duration_min"]:
            report("duration_mismatch", [row["operation_id"]], "Scheduled processing duration differs from operation duration")
        if block_start + row["setup_min"] != start:
            report("setup_arithmetic", [row["operation_id"]], "setup_start_min + setup_min must equal start_min")
        if not any(block_start >= a and end <= b for a, b in calendars[machine_id]):
            report("outside_shift", [row["operation_id"], machine_id], "Setup/processing interval is not contained in a machine shift")
        if any(block_start < b and end > a for a, b in downtime[machine_id]):
            report("machine_downtime", [row["operation_id"], machine_id], "Scheduled interval overlaps machine downtime")

    # Machine intervals include setup, not only processing.
    by_machine = defaultdict(list)
    for row in schedules:
        if row["schedule_id"] == schedule_id and row["status"] == "scheduled" and row["machine_id"] in machine_by_id:
            by_machine[row["machine_id"]].append(row)
    for machine_id, rows in by_machine.items():
        rows.sort(key=lambda r: (r["setup_start_min"], r["end_min"], r["operation_id"]))
        machine_has_overlap = False
        for previous, current in zip(rows, rows[1:]):
            if current["setup_start_min"] < previous["end_min"]:
                report("machine_overlap", [previous["operation_id"], current["operation_id"]], f"Machine {machine_id} has overlapping setup/processing intervals")
                machine_has_overlap = True
        previous_family = None
        for row in rows:
            if machine_has_overlap:
                break
            op = operations[row["operation_id"]]
            order = orders[op["order_id"]]
            family = products[order["sku"]]["family"]
            required = changeovers.get((machine_id, previous_family, family), 0) if previous_family else 0
            if row["setup_min"] != required:
                report("changeover_omitted", [row["operation_id"], machine_id], f"Required setup is {required} minutes, recorded {row['setup_min']}")
            previous_family = family

    by_tool = defaultdict(list)
    for row in schedules:
        if row["schedule_id"] == schedule_id and row["status"] == "scheduled" and row.get("tooling_id"):
            by_tool[row["tooling_id"]].append(row)
    for tool_id, rows in by_tool.items():
        rows.sort(key=lambda r: (r["setup_start_min"], r["end_min"], r["operation_id"]))
        for previous, current in zip(rows, rows[1:]):
            if current["setup_start_min"] < previous["end_min"]:
                report("tooling_overlap", [previous["operation_id"], current["operation_id"]], f"Shared tool {tool_id} has overlapping assignments")

    for op_id, op in operations.items():
        if op.get("predecessor_operation_id"):
            previous = schedule_by_op.get(op["predecessor_operation_id"])
            current = schedule_by_op.get(op_id)
            if previous and current and previous["status"] == current["status"] == "scheduled" and current["start_min"] < previous["end_min"]:
                report("precedence_violation", [op["predecessor_operation_id"], op_id], "Operation starts before its predecessor finishes")
    for event in consumptions:
        if event["schedule_id"] != schedule_id:
            continue
        lot = lots.get(event["lot_id"])
        if lot and event["consumed_min"] < lot["available_min"]:
            report("material_before_availability", [event["order_id"], event["lot_id"]], "Material was consumed before its inventory lot became available")
    consumed_by_lot = Counter()
    for event in consumptions:
        if event["schedule_id"] == schedule_id:
            consumed_by_lot[event["lot_id"]] += event["quantity"]
    for lot_id, quantity in consumed_by_lot.items():
        if lot_id in lots and quantity > lots[lot_id]["quantity"] + 1e-8:
            report("material_balance", [lot_id], "Consumption exceeds inventory lot quantity")

    order_finish = defaultdict(int)
    for row in schedules:
        if row["schedule_id"] == schedule_id and row["status"] == "scheduled":
            op = operations[row["operation_id"]]
            order_finish[op["order_id"]] = max(order_finish[op["order_id"]], row["end_min"])
    scheduled_orders = [o for o in data["production_orders"] if o["order_id"] in order_finish]
    lateness = {o["order_id"]: max(0, order_finish[o["order_id"]] - o["due_min"]) for o in scheduled_orders}
    makespan = max((r["end_min"] for r in schedules if r["schedule_id"] == schedule_id and r["status"] == "scheduled"), default=0)
    total_processing = sum(
        r["end_min"] - r["start_min"] for r in schedules
        if r["schedule_id"] == schedule_id and r["status"] == "scheduled"
    )
    scheduled_operation_count = sum(r["schedule_id"] == schedule_id and r["status"] == "scheduled" for r in schedules)
    return {
        "schedule_id": schedule_id,
        "valid": not issues,
        "issue_count": len(issues),
        "issues": issues,
        "metrics": {
            "makespan_min": makespan,
            "scheduled_operations": scheduled_operation_count,
            "infeasible_operations": sum(r["schedule_id"] == schedule_id and r["status"] == "infeasible" for r in schedules),
            "total_processing_min": total_processing,
            "late_orders": sum(value > 0 for value in lateness.values()),
            "total_lateness_min": sum(lateness.values()),
            "max_order_lateness_min": max(lateness.values(), default=0),
        },
    }
