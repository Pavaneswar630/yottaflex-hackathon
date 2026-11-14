"""Make five isolated schedule copies and separate, rule-derived labels."""

import copy
from collections import defaultdict


def make_anomaly_scenarios(data: dict) -> tuple[dict[str, dict], list[dict]]:
    scenarios = {}
    labels = []
    rule_by_issue = {
        "machine_overlap": "RULE-MACHINE-NO-OVERLAP",
        "precedence_violation": "RULE-OPERATION-PRECEDENCE",
        "material_before_availability": "RULE-MATERIAL-AVAILABLE",
        "outside_shift": "RULE-MACHINE-CALENDAR",
        "changeover_omitted": "RULE-CHANGEOVER-REQUIRED",
    }
    operations = {row["operation_id"]: row for row in data["operations"]}
    orders = {row["order_id"]: row for row in data["production_orders"]}
    products = {row["sku"]: row for row in data["products"]}
    calendars = defaultdict(list)
    for row in data["machine_calendars"]:
        calendars[row["machine_id"]].append((row["shift_start_min"], row["shift_end_min"]))
    lots = {row["lot_id"]: row for row in data["inventory_lots"]}

    for number, (issue_type, rule_id) in enumerate(rule_by_issue.items(), start=2):
        schedule_id = f"SCH-2026-{number:06d}"
        schedule_rows = copy.deepcopy(data["operation_schedules"])
        consumption = copy.deepcopy(data["material_consumption_events"])
        for row in schedule_rows + consumption:
            row["schedule_id"] = schedule_id

        if issue_type == "machine_overlap":
            affected = _inject_overlap(schedule_rows, operations, orders, products)
        elif issue_type == "precedence_violation":
            affected = _inject_precedence(schedule_rows, operations)
        elif issue_type == "material_before_availability":
            affected = _inject_early_material(consumption, lots)
        elif issue_type == "outside_shift":
            affected = _inject_outside_shift(schedule_rows, operations, calendars)
        else:
            affected = _inject_omitted_changeover(schedule_rows)

        scenarios[issue_type] = {
            "schedule_id": schedule_id,
            "operation_schedules": schedule_rows,
            "material_consumption_events": consumption,
        }
        labels.append({
            "schedule_id": schedule_id,
            "issue_type": issue_type,
            "affected_entity_ids": "|".join(affected),
            "expected_explanation_key": rule_id,
        })
    return scenarios, labels


def _inject_overlap(rows, operations, orders, products):
    by_machine = defaultdict(list)
    for row in rows:
        if row["status"] == "scheduled":
            by_machine[row["machine_id"]].append(row)
    for machine_rows in by_machine.values():
        chronological = sorted(machine_rows, key=lambda row: (row["setup_start_min"], row["end_min"]))
        for first, second in zip(chronological, chronological[1:]):
            first_op = operations[first["operation_id"]]
            second_op = operations[second["operation_id"]]
            if second_op["step_no"] != 1 or second["setup_min"] != 0:
                continue
            first_family = products[orders[first_op["order_id"]]["sku"]]["family"]
            second_family = products[orders[second_op["order_id"]]["sku"]]["family"]
            if first_family != second_family:
                continue
            start = first["start_min"]
            end = start + second_op["duration_min"]
            others = [row for row in chronological if row is not first and row is not second]
            if any(start < row["end_min"] and end > row["setup_start_min"] for row in others):
                continue
            second["start_min"] = start
            second["setup_start_min"] = start
            second["end_min"] = end
            return [first["operation_id"], second["operation_id"]]
    raise RuntimeError("Could not find a compatible pair for the isolated overlap scenario")


def _inject_precedence(rows, operations):
    row_by_id = {row["operation_id"]: row for row in rows}
    for row in rows:
        operation = operations[row["operation_id"]]
        predecessor_id = operation["predecessor_operation_id"]
        if not predecessor_id or row["status"] != "scheduled":
            continue
        predecessor = row_by_id[predecessor_id]
        row["start_min"] = predecessor["start_min"]
        row["end_min"] = row["start_min"] + operation["duration_min"]
        row["setup_start_min"] = row["start_min"]
        row["setup_min"] = 0
        return [predecessor_id, row["operation_id"]]
    raise RuntimeError("Could not find an operation for the isolated precedence scenario")


def _inject_early_material(consumption, lots):
    for row in consumption:
        available = lots[row["lot_id"]]["available_min"]
        if available > 0:
            row["consumed_min"] = available - 1
            return [row["order_id"], row["lot_id"]]
    raise RuntimeError("No delayed lot is available for the material scenario")


def _inject_outside_shift(rows, operations, calendars):
    by_machine = defaultdict(list)
    for row in rows:
        if row["status"] == "scheduled":
            by_machine[row["machine_id"]].append(row)
    for machine_rows in by_machine.values():
        last = max(machine_rows, key=lambda row: row["end_min"])
        operation = operations[last["operation_id"]]
        order_steps = [row["step_no"] for row in operations.values() if row["order_id"] == operation["order_id"]]
        if operation["step_no"] != max(order_steps):
            continue
        shift_end = max(end for _, end in calendars[last["machine_id"]])
        last["start_min"] = shift_end
        last["end_min"] = shift_end + operation["duration_min"]
        last["setup_start_min"] = shift_end - last["setup_min"]
        return [last["operation_id"], last["machine_id"]]
    raise RuntimeError("Could not find a terminal operation for the outside-shift scenario")


def _inject_omitted_changeover(rows):
    for row in rows:
        if row["status"] == "scheduled" and row["setup_min"] > 0:
            row["setup_min"] = 0
            row["setup_start_min"] = row["start_min"]
            return [row["operation_id"], row["machine_id"]]
    raise RuntimeError("No positive setup is available for the omitted-changeover scenario")
