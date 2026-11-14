"""Run the deterministic master-data, transaction, and scheduling phases."""

import random

from .config import DEFAULT_SEED, Scale
from .master_generator import generate_master_data
from .schemas import ENTITIES
from .scheduler import schedule_operations
from .transaction_generator import generate_transactions


def generate(seed: int = DEFAULT_SEED, scale: Scale | None = None) -> dict[str, list[dict]]:
    scale = scale or Scale()
    if min(scale.skus, scale.machines, scale.orders, scale.materials, scale.operations_per_order) < 1:
        raise ValueError("All entity counts must be positive")
    if scale.machines < 4:
        raise ValueError("At least four machines are required for the routing capability classes")
    if scale.horizon_days < 1:
        raise ValueError("Planning horizon must be at least one day")

    data = {table: [] for table in ENTITIES}
    rng = random.Random(seed)
    masters = generate_master_data(data, rng, scale)
    transactions = generate_transactions(data, rng, scale, masters)

    schedules, consumption, events = schedule_operations(
        data,
        transactions["operations_by_order"],
        transactions["requirements_by_order"],
        transactions["lot_for_material"],
        masters["setup_lookup"],
    )
    data["operation_schedules"] = schedules
    data["material_consumption_events"] = consumption
    data["schedule_events"] = events

    operations = {row["operation_id"]: row for row in data["operations"]}
    schedules_by_order = {}
    for row in schedules:
        order_id = operations[row["operation_id"]]["order_id"]
        schedules_by_order.setdefault(order_id, []).append(row)

    for order in transactions["orders"]:
        order_rows = schedules_by_order.get(order["order_id"], [])
        complete = bool(order_rows) and all(row["status"] == "scheduled" for row in order_rows)
        if complete:
            order["lifecycle_state"] = "scheduled"
            event_time = max(row["end_min"] for row in order_rows)
            new_state = "scheduled"
        else:
            order["lifecycle_state"] = "infeasible"
            event_time = order["release_min"]
            new_state = "infeasible"
        data["order_status_events"].append({
            "order_status_event_id": f"OSE-{int(order['order_id'][-6:]):07d}-02",
            "order_id": order["order_id"], "old_state": "released",
            "new_state": new_state, "event_min": event_time,
        })
    return data
