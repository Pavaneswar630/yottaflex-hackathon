"""Canonical data dictionary and relational metadata for generated records."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RecordModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Product(RecordModel):
    sku: str = Field(pattern=r"^PROD-2026-\d{6}$")
    name: str
    family: str = Field(pattern=r"^FAM-\d{2}$")
    active: bool


class Routing(RecordModel):
    routing_id: str = Field(pattern=r"^ROUTE-PROD-2026-\d{6}-\d{2}$")
    sku: str = Field(pattern=r"^PROD-2026-\d{6}$")
    revision: int = Field(ge=1)
    effective_from_min: int = Field(ge=0)
    effective_to_min: int | None = Field(default=None, gt=0)
    lifecycle_state: Literal["draft", "active", "retired"]

    @model_validator(mode="after")
    def effective_range(self):
        if self.effective_to_min is not None and self.effective_to_min <= self.effective_from_min:
            raise ValueError("effective_to_min must be later than effective_from_min")
        return self


class Operation(RecordModel):
    operation_id: str = Field(pattern=r"^OP-PROD-2026-\d{6}-\d{2}$")
    order_id: str = Field(pattern=r"^PROD-2026-\d{6}$")
    routing_step_id: str
    step_no: int = Field(ge=1)
    duration_min: int = Field(gt=0)
    predecessor_operation_id: str | None = None
    tooling_group: str | None = None


class Machine(RecordModel):
    machine_id: str = Field(pattern=r"^MACH-\d{3}$")
    name: str
    capability: str
    active: bool


class MachineCalendar(RecordModel):
    calendar_id: str
    machine_id: str = Field(pattern=r"^MACH-\d{3}$")
    work_date: int = Field(ge=0)
    shift_start_min: int = Field(ge=0)
    shift_end_min: int = Field(gt=0)
    capacity_min: int = Field(gt=0)
    shift_code: Literal["DAY"]

    @model_validator(mode="after")
    def valid_shift(self):
        if self.shift_end_min <= self.shift_start_min:
            raise ValueError("shift_end_min must be later than shift_start_min")
        if self.capacity_min > self.shift_end_min - self.shift_start_min:
            raise ValueError("capacity_min cannot exceed shift length")
        return self


class Material(RecordModel):
    material_id: str = Field(pattern=r"^MAT-\d{3}$")
    name: str
    unit: Literal["kg", "ea", "m"]
    active: bool


class InventoryLot(RecordModel):
    lot_id: str = Field(pattern=r"^LOT-\d{3}$")
    material_id: str = Field(pattern=r"^MAT-\d{3}$")
    available_min: int = Field(ge=0)
    quantity: float = Field(gt=0)
    lifecycle_state: Literal["available", "delayed", "depleted"]


class ProductionOrder(RecordModel):
    order_id: str = Field(pattern=r"^PROD-2026-\d{6}$")
    sku: str = Field(pattern=r"^PROD-2026-\d{6}$")
    routing_id: str = Field(pattern=r"^ROUTE-PROD-2026-\d{6}-\d{2}$")
    quantity: int = Field(gt=0)
    release_min: int = Field(ge=0)
    due_min: int = Field(gt=0)
    priority: int = Field(ge=1, le=5)
    urgent: bool
    lifecycle_state: Literal["released", "scheduled", "completed", "infeasible"]

    @model_validator(mode="after")
    def valid_dates(self):
        if self.due_min <= self.release_min:
            raise ValueError("due_min must be later than release_min")
        return self


class OperationSchedule(RecordModel):
    schedule_line_id: str
    schedule_id: str = Field(pattern=r"^SCH-2026-\d{6}$")
    operation_id: str = Field(pattern=r"^OP-PROD-2026-\d{6}-\d{2}$")
    machine_id: str | None = Field(default=None, pattern=r"^MACH-\d{3}$")
    start_min: int | None = Field(default=None, ge=0)
    end_min: int | None = Field(default=None, gt=0)
    setup_start_min: int | None = Field(default=None, ge=0)
    setup_min: int = Field(ge=0)
    tooling_id: str | None = None
    status: Literal["scheduled", "infeasible"]
    infeasibility_reason: str | None = None

    @model_validator(mode="after")
    def consistent_state(self):
        times = (self.start_min, self.end_min, self.setup_start_min, self.machine_id)
        if self.status == "scheduled":
            if any(value is None for value in times):
                raise ValueError("scheduled rows require a machine and all schedule times")
            if self.end_min <= self.start_min or self.setup_start_min + self.setup_min != self.start_min:
                raise ValueError("scheduled times or setup arithmetic are invalid")
            if self.infeasibility_reason is not None:
                raise ValueError("scheduled rows cannot have an infeasibility reason")
        elif any(value is not None for value in times) or not self.infeasibility_reason:
            raise ValueError("infeasible rows require a reason and no assigned machine or times")
        return self


class ChangeoverMatrix(RecordModel):
    changeover_id: str
    machine_id: str = Field(pattern=r"^MACH-\d{3}$")
    from_family: str = Field(pattern=r"^FAM-\d{2}$")
    to_family: str = Field(pattern=r"^FAM-\d{2}$")
    setup_min: int = Field(ge=0)
    effective_from_min: int = Field(ge=0)


class RoutingStep(RecordModel):
    routing_step_id: str = Field(pattern=r"^ROUTE-PROD-2026-\d{6}-01-STEP-\d{2}$")
    routing_id: str = Field(pattern=r"^ROUTE-PROD-2026-\d{6}-01$")
    step_no: int = Field(ge=1)
    duration_min: int = Field(gt=0)
    tooling_group: str | None = None


class ProductBOM(RecordModel):
    bom_line_id: str = Field(pattern=r"^BOM-\d{6}$")
    sku: str = Field(pattern=r"^PROD-2026-\d{6}$")
    material_id: str = Field(pattern=r"^MAT-\d{3}$")
    quantity_per_unit: float = Field(gt=0)
    effective_from_min: int = Field(ge=0)
    effective_to_min: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def effective_range(self):
        if self.effective_to_min is not None and self.effective_to_min <= self.effective_from_min:
            raise ValueError("effective_to_min must be later than effective_from_min")
        return self


class MachineEligibility(RecordModel):
    eligibility_id: str = Field(pattern=r"^EL-\d{7}$")
    routing_step_id: str
    machine_id: str = Field(pattern=r"^MACH-\d{3}$")


class Tooling(RecordModel):
    tooling_id: str = Field(pattern=r"^TOOL-\d{3}$")
    tooling_group: str = Field(pattern=r"^TG-\d{2}$")


class ToolingAssignment(RecordModel):
    tooling_assignment_id: str = Field(pattern=r"^TA-\d{6}$")
    routing_step_id: str
    tooling_id: str = Field(pattern=r"^TOOL-\d{3}$")


class MaterialRequirement(RecordModel):
    requirement_id: str = Field(pattern=r"^REQ-\d{7}$")
    order_id: str = Field(pattern=r"^PROD-2026-\d{6}$")
    material_id: str = Field(pattern=r"^MAT-\d{3}$")
    lot_id: str = Field(pattern=r"^LOT-\d{3}$")
    quantity: float = Field(gt=0)


class MachineDowntimeEvent(RecordModel):
    downtime_id: str = Field(pattern=r"^DOWN-\d{4}$|^DOWN-WHATIF-\d{4}$")
    machine_id: str = Field(pattern=r"^MACH-\d{3}$")
    start_min: int = Field(ge=0)
    end_min: int = Field(gt=0)
    reason: Literal["maintenance", "quality"]

    @model_validator(mode="after")
    def valid_interval(self):
        if self.end_min <= self.start_min:
            raise ValueError("end_min must be later than start_min")
        return self


class MaterialConsumptionEvent(RecordModel):
    consumption_event_id: str = Field(pattern=r"^MC-\d{7}$")
    schedule_id: str = Field(pattern=r"^SCH-2026-\d{6}$")
    order_id: str = Field(pattern=r"^PROD-2026-\d{6}$")
    material_id: str = Field(pattern=r"^MAT-\d{3}$")
    lot_id: str = Field(pattern=r"^LOT-\d{3}$")
    consumed_min: int = Field(ge=0)
    quantity: float = Field(gt=0)


class ScheduleEvent(RecordModel):
    schedule_event_id: str = Field(pattern=r"^SE-\d{7}$")
    schedule_id: str = Field(pattern=r"^SCH-2026-\d{6}$")
    event_type: Literal["created", "rescheduled", "violated"]
    event_min: int = Field(ge=0)
    entity_id: str
    details: str


class OrderStatusEvent(RecordModel):
    order_status_event_id: str = Field(pattern=r"^OSE-\d{7}-\d{2}$")
    order_id: str = Field(pattern=r"^PROD-2026-\d{6}$")
    old_state: Literal["released", "scheduled", "completed", "infeasible"] | None = None
    new_state: Literal["released", "scheduled", "completed", "infeasible"]
    event_min: int = Field(ge=0)


MODEL_BY_TABLE = {
    "products": Product,
    "routings": Routing,
    "routing_steps": RoutingStep,
    "machines": Machine,
    "machine_calendars": MachineCalendar,
    "materials": Material,
    "product_bom": ProductBOM,
    "inventory_lots": InventoryLot,
    "production_orders": ProductionOrder,
    "operations": Operation,
    "machine_eligibility": MachineEligibility,
    "tooling": Tooling,
    "tooling_assignments": ToolingAssignment,
    "material_requirements": MaterialRequirement,
    "operation_schedules": OperationSchedule,
    "changeover_matrix": ChangeoverMatrix,
    "machine_downtime_events": MachineDowntimeEvent,
    "material_consumption_events": MaterialConsumptionEvent,
    "schedule_events": ScheduleEvent,
    "order_status_events": OrderStatusEvent,
}

ENTITIES: dict[str, dict] = {
    "products": {
        "pk": "sku",
        "fields": {
            "sku": ("string", True, "PROD-2026-000001 style; unique product key"),
            "name": ("string", True, "Synthetic product name"),
            "family": ("string", True, "FAM-01 through FAM-10"),
            "active": ("boolean", True, "Whether this product can be ordered"),
        },
    },
    "routings": {
        "pk": "routing_id",
        "fields": {
            "routing_id": ("string", True, "ROUTE-<sku>-01; unique"),
            "sku": ("string", True, "Product foreign key; many routings may belong to a product"),
            "revision": ("integer", True, "Positive immutable revision"),
            "effective_from_min": ("integer", True, "Minutes from 2026-01-01T00:00Z"),
            "effective_to_min": ("integer", False, "Exclusive end; null means currently effective"),
            "lifecycle_state": ("enum", True, "draft, active, retired"),
        },
    },
    "routing_steps": {
        "pk": "routing_step_id",
        "fields": {
            "routing_step_id": ("string", True, "Unique routing-step bridge key"),
            "routing_id": ("string", True, "Routing foreign key"),
            "step_no": ("integer", True, "One-based operation order; unique within routing"),
            "duration_min": ("integer", True, "Processing duration in minutes"),
            "tooling_group": ("string", False, "Shared tooling group required by the step"),
        },
    },
    "machines": {
        "pk": "machine_id",
        "fields": {
            "machine_id": ("string", True, "MACH-001 style; unique"),
            "name": ("string", True, "Synthetic machine name"),
            "capability": ("string", True, "Machine capability class"),
            "active": ("boolean", True, "Whether the machine is schedulable"),
        },
    },
    "machine_calendars": {
        "pk": "calendar_id",
        "fields": {
            "calendar_id": ("string", True, "Unique machine/date/shift key"),
            "machine_id": ("string", True, "Machine foreign key"),
            "work_date": ("integer", True, "Day offset from the fixed epoch"),
            "shift_start_min": ("integer", True, "Absolute minute from fixed epoch"),
            "shift_end_min": ("integer", True, "Exclusive absolute shift end"),
            "capacity_min": ("integer", True, "Shift capacity in minutes"),
            "shift_code": ("enum", True, "DAY"),
        },
    },
    "materials": {
        "pk": "material_id",
        "fields": {
            "material_id": ("string", True, "MAT-001 style; unique"),
            "name": ("string", True, "Synthetic material name"),
            "unit": ("enum", True, "kg, ea, m"),
            "active": ("boolean", True, "Whether material can be consumed"),
        },
    },
    "product_bom": {
        "pk": "bom_line_id",
        "fields": {
            "bom_line_id": ("string", True, "Unique bill-of-material bridge key"),
            "sku": ("string", True, "Product foreign key"),
            "material_id": ("string", True, "Material foreign key"),
            "quantity_per_unit": ("number", True, "Material units required per product unit"),
            "effective_from_min": ("integer", True, "Effective start minute"),
            "effective_to_min": ("integer", False, "Exclusive end; null means current"),
        },
    },
    "production_orders": {
        "pk": "order_id",
        "fields": {
            "order_id": ("string", True, "PROD-2026-000001 style; immutable order key"),
            "sku": ("string", True, "Product foreign key"),
            "routing_id": ("string", True, "Effective routing foreign key"),
            "quantity": ("integer", True, "Positive units"),
            "release_min": ("integer", True, "Release minute from fixed epoch"),
            "due_min": ("integer", True, "Due minute from fixed epoch"),
            "priority": ("integer", True, "1 (lowest) through 5 (highest)"),
            "urgent": ("boolean", True, "Urgent dispatch indicator"),
            "lifecycle_state": ("enum", True, "released, scheduled, completed, infeasible"),
        },
    },
    "operations": {
        "pk": "operation_id",
        "fields": {
            "operation_id": ("string", True, "OP-<order-id>-01 style; unique"),
            "order_id": ("string", True, "Production order foreign key"),
            "routing_step_id": ("string", True, "Routing-step foreign key"),
            "step_no": ("integer", True, "One-based precedence position"),
            "duration_min": ("integer", True, "Processing duration in minutes"),
            "predecessor_operation_id": ("string", False, "Previous operation in the same order"),
            "tooling_group": ("string", False, "Required shared tooling group"),
        },
    },
    "machine_eligibility": {
        "pk": "eligibility_id",
        "fields": {
            "eligibility_id": ("string", True, "Unique machine/step bridge key"),
            "routing_step_id": ("string", True, "Routing-step foreign key"),
            "machine_id": ("string", True, "Eligible machine foreign key"),
        },
    },
    "tooling": {
        "pk": "tooling_id",
        "fields": {
            "tooling_id": ("string", True, "TOOL-001 style; unique shared resource"),
            "tooling_group": ("string", True, "Group of compatible routing requirements"),
        },
    },
    "tooling_assignments": {
        "pk": "tooling_assignment_id",
        "fields": {
            "tooling_assignment_id": ("string", True, "Unique tooling/routing-step bridge key"),
            "routing_step_id": ("string", True, "Routing-step foreign key"),
            "tooling_id": ("string", True, "Shared tooling foreign key"),
        },
    },
    "inventory_lots": {
        "pk": "lot_id",
        "fields": {
            "lot_id": ("string", True, "LOT-001 style; unique"),
            "material_id": ("string", True, "Material foreign key"),
            "available_min": ("integer", True, "Availability minute; may be delayed"),
            "quantity": ("number", True, "Positive available quantity"),
            "lifecycle_state": ("enum", True, "available, delayed, depleted"),
        },
    },
    "material_requirements": {
        "pk": "requirement_id",
        "fields": {
            "requirement_id": ("string", True, "Unique order/material bridge key"),
            "order_id": ("string", True, "Production order foreign key"),
            "material_id": ("string", True, "Material foreign key"),
            "lot_id": ("string", True, "Allocated inventory lot foreign key"),
            "quantity": ("number", True, "Required material quantity"),
        },
    },
    "changeover_matrix": {
        "pk": "changeover_id",
        "fields": {
            "changeover_id": ("string", True, "Unique machine/from-family/to-family key"),
            "machine_id": ("string", True, "Machine foreign key"),
            "from_family": ("string", True, "Previous product family"),
            "to_family": ("string", True, "Next product family"),
            "setup_min": ("integer", True, "Sequence-dependent setup duration in minutes"),
            "effective_from_min": ("integer", True, "Effective start minute"),
        },
    },
    "machine_downtime_events": {
        "pk": "downtime_id",
        "fields": {
            "downtime_id": ("string", True, "Unique immutable downtime event key"),
            "machine_id": ("string", True, "Machine foreign key"),
            "start_min": ("integer", True, "Absolute downtime start"),
            "end_min": ("integer", True, "Exclusive downtime end"),
            "reason": ("enum", True, "maintenance, quality"),
        },
    },
    "operation_schedules": {
        "pk": "schedule_line_id",
        "fields": {
            "schedule_line_id": ("string", True, "Unique schedule-line key"),
            "schedule_id": ("string", True, "SCH-2026-000001 style; identifies a schedule version"),
            "operation_id": ("string", True, "Operation foreign key"),
            "machine_id": ("string", False, "Assigned machine foreign key; null only for infeasible operations"),
            "start_min": ("integer", False, "Processing start minute; null only for infeasible operations"),
            "end_min": ("integer", False, "Exclusive processing end minute; null only for infeasible operations"),
            "setup_start_min": ("integer", False, "Setup interval start minute; null only for infeasible operations"),
            "setup_min": ("integer", True, "Applied setup duration"),
            "tooling_id": ("string", False, "Assigned shared tooling foreign key"),
            "status": ("enum", True, "scheduled, infeasible"),
            "infeasibility_reason": ("string", False, "Required when no feasible placement exists"),
        },
    },
    "material_consumption_events": {
        "pk": "consumption_event_id",
        "fields": {
            "consumption_event_id": ("string", True, "Unique immutable consumption event key"),
            "schedule_id": ("string", True, "Schedule version foreign key"),
            "order_id": ("string", True, "Order foreign key"),
            "material_id": ("string", True, "Material foreign key"),
            "lot_id": ("string", True, "Inventory lot foreign key"),
            "consumed_min": ("integer", True, "Consumption event time"),
            "quantity": ("number", True, "Consumed material quantity"),
        },
    },
    "schedule_events": {
        "pk": "schedule_event_id",
        "fields": {
            "schedule_event_id": ("string", True, "Unique immutable schedule event key"),
            "schedule_id": ("string", True, "Schedule version"),
            "event_type": ("enum", True, "created, rescheduled, violated"),
            "event_min": ("integer", True, "Event time from fixed epoch"),
            "entity_id": ("string", True, "Affected order, operation, or schedule ID"),
            "details": ("string", True, "Traceability details"),
        },
    },
    "order_status_events": {
        "pk": "order_status_event_id",
        "fields": {
            "order_status_event_id": ("string", True, "Unique immutable order status event key"),
            "order_id": ("string", True, "Production order foreign key"),
            "old_state": ("enum", False, "Null for initial state"),
            "new_state": ("enum", True, "released, scheduled, completed, infeasible"),
            "event_min": ("integer", True, "Event time from fixed epoch"),
        },
    },
}

FOREIGN_KEYS: dict[str, tuple[tuple[str, str], ...]] = {
    "routings": (("sku", "products", "sku"),),
    "routing_steps": (("routing_id", "routings", "routing_id"),),
    "machine_calendars": (("machine_id", "machines", "machine_id"),),
    "product_bom": (("sku", "products", "sku"), ("material_id", "materials", "material_id")),
    "production_orders": (("sku", "products", "sku"), ("routing_id", "routings", "routing_id")),
    "operations": (("order_id", "production_orders", "order_id"), ("routing_step_id", "routing_steps", "routing_step_id")),
    "machine_eligibility": (("routing_step_id", "routing_steps", "routing_step_id"), ("machine_id", "machines", "machine_id")),
    "tooling_assignments": (("routing_step_id", "routing_steps", "routing_step_id"), ("tooling_id", "tooling", "tooling_id")),
    "inventory_lots": (("material_id", "materials", "material_id"),),
    "material_requirements": (("order_id", "production_orders", "order_id"), ("material_id", "materials", "material_id"), ("lot_id", "inventory_lots", "lot_id")),
    "changeover_matrix": (("machine_id", "machines", "machine_id"),),
    "machine_downtime_events": (("machine_id", "machines", "machine_id"),),
    "operation_schedules": (("operation_id", "operations", "operation_id"), ("machine_id", "machines", "machine_id")),
    "material_consumption_events": (("order_id", "production_orders", "order_id"), ("material_id", "materials", "material_id"), ("lot_id", "inventory_lots", "lot_id")),
    "order_status_events": (("order_id", "production_orders", "order_id"),),
}
UNIQUE_KEYS: dict[str, tuple[tuple[str, ...], ...]] = {
    "routing_steps": (("routing_id", "step_no"),),
    "machine_calendars": (("machine_id", "work_date", "shift_code"),),
    "product_bom": (("sku", "material_id"),),
    "machine_eligibility": (("routing_step_id", "machine_id"),),
    "tooling_assignments": (("routing_step_id", "tooling_id"),),
    "material_requirements": (("order_id", "material_id"),),
    "changeover_matrix": (("machine_id", "from_family", "to_family", "effective_from_min"),),
}

ALLOWED_VALUES = {
    ("routings", "lifecycle_state"): ["draft", "active", "retired"],
    ("machine_calendars", "shift_code"): ["DAY"],
    ("materials", "unit"): ["kg", "ea", "m"],
    ("inventory_lots", "lifecycle_state"): ["available", "delayed", "depleted"],
    ("production_orders", "priority"): [1, 2, 3, 4, 5],
    ("production_orders", "lifecycle_state"): ["released", "scheduled", "completed", "infeasible"],
    ("machine_downtime_events", "reason"): ["maintenance", "quality"],
    ("operation_schedules", "status"): ["scheduled", "infeasible"],
    ("schedule_events", "event_type"): ["created", "rescheduled", "violated"],
    ("order_status_events", "new_state"): ["released", "scheduled", "completed", "infeasible"],
    ("order_status_events", "old_state"): ["released", "scheduled", "completed", "infeasible"],
}
FIELD_UNITS = {
    "effective_from_min": "minutes from fixed epoch",
    "effective_to_min": "minutes from fixed epoch",
    "release_min": "minutes from fixed epoch",
    "due_min": "minutes from fixed epoch",
    "available_min": "minutes from fixed epoch",
    "consumed_min": "minutes from fixed epoch",
    "start_min": "minutes from fixed epoch",
    "end_min": "minutes from fixed epoch",
    "setup_start_min": "minutes from fixed epoch",
    "shift_start_min": "minutes from fixed epoch",
    "shift_end_min": "minutes from fixed epoch",
    "work_date": "days from fixed epoch",
    "event_min": "minutes from fixed epoch",
    "duration_min": "minutes",
    "setup_min": "minutes",
    "capacity_min": "minutes per shift",
    "quantity": "material-specific units",
    "quantity_per_unit": "material-specific units per finished product unit",
}


def data_dictionary() -> dict:
    """Return a serializable dictionary including key/cardinality metadata."""
    relationships = [
        {"from": "products", "to": "routings", "cardinality": "1:N", "optional": False},
        {"from": "routings", "to": "routing_steps", "cardinality": "1:N", "optional": False},
        {"from": "routing_steps", "to": "machines", "cardinality": "N:M via machine_eligibility", "optional": False},
        {"from": "products", "to": "materials", "cardinality": "N:M via product_bom", "optional": False},
        {"from": "routing_steps", "to": "tooling", "cardinality": "N:M via tooling_assignments", "optional": True},
        {"from": "production_orders", "to": "operations", "cardinality": "1:N", "optional": False},
        {"from": "machines", "to": "machine_calendars", "cardinality": "1:N", "optional": False},
        {"from": "materials", "to": "inventory_lots", "cardinality": "1:N", "optional": False},
        {"from": "production_orders", "to": "material_requirements", "cardinality": "1:N", "optional": False},
        {"from": "machines", "to": "changeover_matrix", "cardinality": "1:N", "optional": False},
        {"from": "machines", "to": "machine_downtime_events", "cardinality": "1:N", "optional": True},
        {"from": "operations", "to": "operation_schedules", "cardinality": "1:N across schedule versions", "optional": False},
        {"from": "production_orders", "to": "order_status_events", "cardinality": "1:N event history", "optional": False},
    ]
    return {
        "epoch": "2026-01-01T00:00:00Z",
        "time_unit": "integer minutes from epoch; intervals are half-open [start, end)",
        "entities": {
            name: {
                "primary_key": spec["pk"],
                "unique_constraints": [list(fields) for fields in UNIQUE_KEYS.get(name, ())],
                "fields": [
                    {
                        "name": field,
                        "type": meta[0],
                        "required": meta[1],
                        "allowed_values": ALLOWED_VALUES.get((name, field)),
                        "units": FIELD_UNITS.get(field),
                        "unique": field == spec["pk"],
                        "validation": meta[2],
                    }
                    for field, meta in spec["fields"].items()
                ],
            }
            for name, spec in ENTITIES.items()
        },
        "relationships": relationships,
        "lifecycle_states": {
            "routing": ["draft", "active", "retired"],
            "production_order": ["released", "scheduled", "completed", "infeasible"],
            "inventory_lot": ["available", "delayed", "depleted"],
            "operation_schedule": ["scheduled", "infeasible"],
        },
    }
