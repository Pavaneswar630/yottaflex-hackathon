"""Create products, routings, machines, calendars, materials, tools, and rules."""

from collections import defaultdict
import random

from .config import MINUTES_PER_DAY, Scale, format_id


def generate_master_data(data: dict, rng: random.Random, scale: Scale) -> dict:
    capabilities = [f"CAP-{i:02d}" for i in range(1, 5)]
    machines = [
        {
            "machine_id": format_id("MACH", i),
            "name": f"Cell {i:02d}",
            "capability": capabilities[(i - 1) % 4],
            "active": True,
        }
        for i in range(1, scale.machines + 1)
    ]
    products = [
        {
            "sku": f"PROD-2026-{i:06d}",
            "name": f"Product {i:03d}",
            "family": f"FAM-{(i - 1) % 10 + 1:02d}",
            "active": True,
        }
        for i in range(1, scale.skus + 1)
    ]
    materials = [
        {
            "material_id": format_id("MAT", i),
            "name": f"Material {i:03d}",
            "unit": ("kg", "ea", "m")[(i - 1) % 3],
            "active": True,
        }
        for i in range(1, scale.materials + 1)
    ]
    data["machines"] = machines
    data["products"] = products
    data["materials"] = materials

    tooling_groups = [f"TG-{i:02d}" for i in range(1, 5)]
    tools = [
        {"tooling_id": format_id("TOOL", i), "tooling_group": tooling_groups[(i - 1) % 4]}
        for i in range(1, 9)
    ]
    data["tooling"] = tools
    tools_by_group = defaultdict(list)
    for tool in tools:
        tools_by_group[tool["tooling_group"]].append(tool["tooling_id"])

    route_for_sku = {}
    steps_for_route = {}
    for product in products:
        route_id = f"ROUTE-{product['sku']}-01"
        route_for_sku[product["sku"]] = route_id
        data["routings"].append({
            "routing_id": route_id, "sku": product["sku"], "revision": 1,
            "effective_from_min": 0, "effective_to_min": None, "lifecycle_state": "active",
        })
        steps = []
        for step_no in range(1, scale.operations_per_order + 1):
            step_id = f"{route_id}-STEP-{step_no:02d}"
            tooling_group = tooling_groups[(step_no - 1) % 4] if step_no == 2 else None
            step = {
                "routing_step_id": step_id, "routing_id": route_id, "step_no": step_no,
                "duration_min": rng.randint(35, 100), "tooling_group": tooling_group,
            }
            steps.append(step)
            data["routing_steps"].append(step)
            for tool_id in tools_by_group[tooling_group] if tooling_group else []:
                data["tooling_assignments"].append({
                    "tooling_assignment_id": f"TA-{len(data['tooling_assignments']) + 1:06d}",
                    "routing_step_id": step_id, "tooling_id": tool_id,
                })
            capability = capabilities[(step_no - 1) % 4]
            eligible = sorted(m["machine_id"] for m in machines if m["capability"] == capability)
            for machine_id in sorted(rng.sample(eligible, min(3, len(eligible)))):
                data["machine_eligibility"].append({
                    "eligibility_id": f"EL-{len(data['machine_eligibility']) + 1:07d}",
                    "routing_step_id": step_id, "machine_id": machine_id,
                })
        steps_for_route[route_id] = steps

    for machine in machines:
        for day in range(scale.horizon_days):
            if day % 7 >= 5:
                continue
            start = day * MINUTES_PER_DAY + 8 * 60
            data["machine_calendars"].append({
                "calendar_id": f"CAL-{machine['machine_id']}-{day:03d}-DAY",
                "machine_id": machine["machine_id"], "work_date": day,
                "shift_start_min": start, "shift_end_min": start + 8 * 60,
                "capacity_min": 8 * 60, "shift_code": "DAY",
            })

    bom_for_sku = {}
    for product in products:
        selected = sorted(
            rng.sample(materials, min(2 + rng.randrange(2), scale.materials)),
            key=lambda row: row["material_id"],
        )
        lines = []
        for material in selected:
            line = {
                "bom_line_id": f"BOM-{len(data['product_bom']) + 1:06d}",
                "sku": product["sku"], "material_id": material["material_id"],
                "quantity_per_unit": round(rng.uniform(0.5, 3.0), 2),
                "effective_from_min": 0, "effective_to_min": None,
            }
            data["product_bom"].append(line)
            lines.append(line)
        bom_for_sku[product["sku"]] = lines

    setup_lookup = {}
    families = [f"FAM-{i:02d}" for i in range(1, 11)]
    for machine in machines:
        machine_number = int(machine["machine_id"][-3:])
        for from_family in families:
            for to_family in families:
                setup = 0 if from_family == to_family else 10 + (
                    machine_number + int(from_family[-2:]) * 3 + int(to_family[-2:])
                ) % 31
                data["changeover_matrix"].append({
                    "changeover_id": f"CO-{machine['machine_id']}-{from_family}-{to_family}",
                    "machine_id": machine["machine_id"], "from_family": from_family,
                    "to_family": to_family, "setup_min": setup, "effective_from_min": 0,
                })
                setup_lookup[(machine["machine_id"], from_family, to_family)] = setup

    for index, machine in enumerate(machines[::9], start=1):
        start = (12 + index) * MINUTES_PER_DAY + 11 * 60
        data["machine_downtime_events"].append({
            "downtime_id": format_id("DOWN", index, 4),
            "machine_id": machine["machine_id"], "start_min": start, "end_min": start + 180,
            "reason": "maintenance" if index % 2 else "quality",
        })

    return {
        "route_for_sku": route_for_sku,
        "steps_for_route": steps_for_route,
        "bom_for_sku": bom_for_sku,
        "setup_lookup": setup_lookup,
    }
