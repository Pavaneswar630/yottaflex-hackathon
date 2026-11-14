"""Create orders, operations, inventory lots, and material requirements."""

import random
from collections import defaultdict

from .config import MINUTES_PER_DAY, Scale, format_id


def generate_transactions(data: dict, rng: random.Random, scale: Scale, masters: dict) -> dict:
    orders = []
    operations_by_order = {}
    for number in range(1, scale.orders + 1):
        product = data["products"][(number - 1) % scale.skus]
        release_day = rng.randrange(0, min(15, max(1, scale.horizon_days // 5)))
        release = release_day * MINUTES_PER_DAY + 8 * 60
        due_day = min(scale.horizon_days - 1, release_day + rng.randint(4, 35))
        order_id = f"PROD-2026-{number:06d}"
        order = {
            "order_id": order_id, "sku": product["sku"],
            "routing_id": masters["route_for_sku"][product["sku"]],
            "quantity": rng.randint(1, 10), "release_min": release,
            "due_min": due_day * MINUTES_PER_DAY + 17 * 60,
            "priority": rng.randint(1, 5), "urgent": number % 23 == 0,
            "lifecycle_state": "released",
        }
        orders.append(order)
        operations = []
        for step in masters["steps_for_route"][order["routing_id"]]:
            step_no = step["step_no"]
            operations.append({
                "operation_id": f"OP-{order_id}-{step_no:02d}",
                "order_id": order_id, "routing_step_id": step["routing_step_id"],
                "step_no": step_no, "duration_min": step["duration_min"],
                "predecessor_operation_id": f"OP-{order_id}-{step_no - 1:02d}" if step_no > 1 else None,
                "tooling_group": step["tooling_group"],
            })
        operations_by_order[order_id] = operations
        data["operations"].extend(operations)
        data["order_status_events"].append({
            "order_status_event_id": f"OSE-{number:07d}-01", "order_id": order_id,
            "old_state": None, "new_state": "released", "event_min": release,
        })
    data["production_orders"] = orders

    material_totals = defaultdict(float)
    for order in orders:
        for line in masters["bom_for_sku"][order["sku"]]:
            material_totals[line["material_id"]] += order["quantity"] * line["quantity_per_unit"]
    delayed_ids = {row["material_id"] for index, row in enumerate(data["materials"]) if index % 17 == 0}
    for index, material in enumerate(data["materials"], start=1):
        delayed = material["material_id"] in delayed_ids
        data["inventory_lots"].append({
            "lot_id": format_id("LOT", index), "material_id": material["material_id"],
            "available_min": (8 + index % 12) * MINUTES_PER_DAY if delayed else 0,
            "quantity": round(material_totals.get(material["material_id"], 0) * 1.2 + 100, 2),
            "lifecycle_state": "delayed" if delayed else "available",
        })
    lot_for_material = {row["material_id"]: row for row in data["inventory_lots"]}

    requirements_by_order = {}
    for order in orders:
        requirements = []
        for line in masters["bom_for_sku"][order["sku"]]:
            requirement = {
                "requirement_id": f"REQ-{len(data['material_requirements']) + 1:07d}",
                "order_id": order["order_id"], "material_id": line["material_id"],
                "lot_id": lot_for_material[line["material_id"]]["lot_id"],
                "quantity": round(order["quantity"] * line["quantity_per_unit"], 2),
            }
            data["material_requirements"].append(requirement)
            requirements.append(requirement)
        requirements_by_order[order["order_id"]] = requirements

    return {
        "orders": orders,
        "operations_by_order": operations_by_order,
        "requirements_by_order": requirements_by_order,
        "lot_for_material": lot_for_material,
    }
