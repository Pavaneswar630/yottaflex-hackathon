"""Earliest-feasible-slot priority dispatcher and downtime what-if runner."""

import copy
import heapq
from collections import defaultdict


def schedule_operations(data: dict, operations_by_order: dict, requirements_by_order: dict,
                        lot_for_material: dict, setup_lookup: dict,
                        schedule_id: str = "SCH-2026-000001") -> tuple[list[dict], list[dict], list[dict]]:
    calendars = defaultdict(list)
    for row in data["machine_calendars"]:
        calendars[row["machine_id"]].append(row)
    for rows in calendars.values():
        rows.sort(key=lambda row: row["shift_start_min"])

    downtime = defaultdict(list)
    for row in data["machine_downtime_events"]:
        downtime[row["machine_id"]].append((row["start_min"], row["end_min"]))

    eligible_machines = defaultdict(list)
    for row in data["machine_eligibility"]:
        eligible_machines[row["routing_step_id"]].append(row["machine_id"])

    tools_by_step = defaultdict(list)
    for row in data["tooling_assignments"]:
        tools_by_step[row["routing_step_id"]].append(row["tooling_id"])

    products = {row["sku"]: row for row in data["products"]}
    orders = {row["order_id"]: row for row in data["production_orders"]}
    operations = {
        row["operation_id"]: row
        for order_operations in operations_by_order.values()
        for row in order_operations
    }
    successors = defaultdict(list)
    for operation in operations.values():
        predecessor = operation["predecessor_operation_id"]
        if predecessor:
            successors[predecessor].append(operation)

    order_ready = {
        order_id: max(
            [orders[order_id]["release_min"]]
            + [lot_for_material[row["material_id"]]["available_min"] for row in requirements]
        )
        for order_id, requirements in requirements_by_order.items()
    }
    machine_ready = defaultdict(int)
    machine_family = defaultdict(lambda: None)
    tool_ready = defaultdict(int)
    finish_by_operation = {}
    failed_operations = set()
    queued_operations = set()
    schedule_rows = []
    ready_heap = []

    def candidate_for(operation):
        order = orders[operation["order_id"]]
        predecessor = operation["predecessor_operation_id"]
        earliest = max(order["release_min"], finish_by_operation.get(predecessor, 0), order_ready[order["order_id"]])
        family = products[order["sku"]]["family"]
        candidates = []
        for machine_id in sorted(eligible_machines[operation["routing_step_id"]]):
            previous_family = machine_family[machine_id]
            setup = setup_lookup[(machine_id, previous_family, family)] if previous_family else 0
            tool_ids = tools_by_step[operation["routing_step_id"]] if operation["tooling_group"] else [None]
            for tool_id in tool_ids:
                ready = max(earliest, machine_ready[machine_id], tool_ready[tool_id] if tool_id else 0)
                placement = _find_slot(calendars[machine_id], downtime[machine_id], ready, setup + operation["duration_min"])
                if placement:
                    start, _ = placement
                    end = start + setup + operation["duration_min"]
                    candidates.append((end, start, machine_id, setup, tool_id))
        return min(candidates, key=lambda item: (item[1], item[0], item[2])) if candidates else None

    def mark_infeasible(operation, reason):
        operation_id = operation["operation_id"]
        if operation_id in finish_by_operation or operation_id in failed_operations:
            return
        failed_operations.add(operation_id)
        schedule_rows.append({
            "schedule_line_id": f"SL-{len(schedule_rows) + 1:07d}",
            "schedule_id": schedule_id, "operation_id": operation_id,
            "machine_id": None, "start_min": None, "end_min": None,
            "setup_start_min": None, "setup_min": 0, "tooling_id": None,
            "status": "infeasible", "infeasibility_reason": reason,
        })
        for child in successors[operation_id]:
            mark_infeasible(child, "Predecessor operation was not scheduled")

    def enqueue(operation):
        operation_id = operation["operation_id"]
        if operation_id in queued_operations or operation_id in finish_by_operation or operation_id in failed_operations:
            return
        candidate = candidate_for(operation)
        if candidate is None:
            mark_infeasible(operation, "No eligible machine shift with capacity before the planning horizon")
            return
        order = orders[operation["order_id"]]
        heapq.heappush(ready_heap, (
            candidate[1], -int(order["urgent"]), -order["priority"],
            order["due_min"], order["order_id"], operation["step_no"],
            operation_id, candidate,
        ))
        queued_operations.add(operation_id)

    for order_operations in operations_by_order.values():
        enqueue(min(order_operations, key=lambda operation: operation["step_no"]))

    while ready_heap:
        *_, operation_id, old_candidate = heapq.heappop(ready_heap)
        queued_operations.discard(operation_id)
        if operation_id in finish_by_operation or operation_id in failed_operations:
            continue
        operation = operations[operation_id]
        candidate = candidate_for(operation)
        if candidate is None:
            mark_infeasible(operation, "No eligible machine shift with capacity before the planning horizon")
            continue
        if candidate != old_candidate:
            enqueue(operation)
            continue

        end, block_start, machine_id, setup, tool_id = candidate
        start = block_start + setup
        schedule_rows.append({
            "schedule_line_id": f"SL-{len(schedule_rows) + 1:07d}",
            "schedule_id": schedule_id, "operation_id": operation_id,
            "machine_id": machine_id, "start_min": start, "end_min": end,
            "setup_start_min": block_start, "setup_min": setup,
            "tooling_id": tool_id, "status": "scheduled", "infeasibility_reason": None,
        })
        machine_ready[machine_id] = end
        machine_family[machine_id] = products[orders[operation["order_id"]]["sku"]]["family"]
        if tool_id:
            tool_ready[tool_id] = end
        finish_by_operation[operation_id] = end
        for child in successors[operation_id]:
            enqueue(child)

    for operation in operations.values():
        if operation["operation_id"] not in finish_by_operation.keys() | failed_operations:
            mark_infeasible(operation, "Predecessor operation was not scheduled")

    rows_by_order = defaultdict(list)
    for row in schedule_rows:
        rows_by_order[operations[row["operation_id"]]["order_id"]].append(row)
    consumption = []
    for order_id, requirements in requirements_by_order.items():
        first_start = min(
            (row["start_min"] for row in rows_by_order[order_id] if row["status"] == "scheduled"),
            default=orders[order_id]["release_min"],
        )
        for requirement in requirements:
            consumption.append({
                "consumption_event_id": f"MC-{len(consumption) + 1:07d}",
                "schedule_id": schedule_id, "order_id": order_id,
                "material_id": requirement["material_id"], "lot_id": requirement["lot_id"],
                "consumed_min": first_start, "quantity": requirement["quantity"],
            })

    events = [{
        "schedule_event_id": "SE-0000001", "schedule_id": schedule_id,
        "event_type": "created", "event_min": 0, "entity_id": schedule_id,
        "details": "Seeded priority-dispatch schedule generated",
    }]
    return schedule_rows, consumption, events


def reschedule_with_downtime(data: dict, machine_id: str, start_min: int, duration_min: int,
                             schedule_id: str = "SCH-2026-000002"):
    """Run a new schedule version after adding a hypothetical downtime event."""
    if machine_id not in {row["machine_id"] for row in data["machines"]}:
        raise ValueError(f"Unknown machine: {machine_id}")
    if start_min < 0 or duration_min <= 0:
        raise ValueError("Downtime start must be non-negative and duration must be positive")

    changed = copy.deepcopy(data)
    event_id = f"DOWN-WHATIF-{len(changed['machine_downtime_events']) + 1:04d}"
    changed["machine_downtime_events"].append({
        "downtime_id": event_id, "machine_id": machine_id,
        "start_min": start_min, "end_min": start_min + duration_min,
        "reason": "maintenance",
    })
    operations_by_order = defaultdict(list)
    for operation in changed["operations"]:
        operations_by_order[operation["order_id"]].append(operation)
    for rows in operations_by_order.values():
        rows.sort(key=lambda row: row["step_no"])
    requirements_by_order = defaultdict(list)
    for requirement in changed["material_requirements"]:
        requirements_by_order[requirement["order_id"]].append(requirement)
    lot_for_material = {row["material_id"]: row for row in changed["inventory_lots"]}
    setup_lookup = {
        (row["machine_id"], row["from_family"], row["to_family"]): row["setup_min"]
        for row in changed["changeover_matrix"]
    }
    schedules, consumption, events = schedule_operations(
        changed, operations_by_order, requirements_by_order, lot_for_material,
        setup_lookup, schedule_id,
    )
    events[0]["event_type"] = "rescheduled"
    events[0]["schedule_event_id"] = f"SE-{schedule_id[-6:]}"
    events[0]["details"] = f"Replanned after hypothetical downtime event {event_id}"
    changed["schedule_events"].extend(events)
    return changed, schedules, consumption, events


def _find_slot(calendar_rows: list[dict], downtime_rows: list[tuple[int, int]],
               earliest: int, duration: int) -> tuple[int, int] | None:
    if duration <= 0:
        return None
    for shift in calendar_rows:
        start = max(earliest, shift["shift_start_min"])
        while start + duration <= shift["shift_end_min"]:
            conflict = next(((a, b) for a, b in downtime_rows if start < b and start + duration > a), None)
            if conflict is None:
                return start, start + duration
            start = conflict[1]
    return None
