# Data dictionary

Epoch: `2026-01-01T00:00:00Z`. Time unit: integer minutes from epoch; intervals are half-open [start, end).

## Entities

### products

Primary key: `sku`.
Unique constraints: `[]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `sku` | string | yes |  |  | yes | PROD-2026-000001 style; unique product key |
| `name` | string | yes |  |  | no | Synthetic product name |
| `family` | string | yes |  |  | no | FAM-01 through FAM-10 |
| `active` | boolean | yes |  |  | no | Whether this product can be ordered |

### routings

Primary key: `routing_id`.
Unique constraints: `[]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `routing_id` | string | yes |  |  | yes | ROUTE-<sku>-01; unique |
| `sku` | string | yes |  |  | no | Product foreign key; many routings may belong to a product |
| `revision` | integer | yes |  |  | no | Positive immutable revision |
| `effective_from_min` | integer | yes |  | minutes from fixed epoch | no | Minutes from 2026-01-01T00:00Z |
| `effective_to_min` | integer | no |  | minutes from fixed epoch | no | Exclusive end; null means currently effective |
| `lifecycle_state` | enum | yes | draft, active, retired |  | no | draft, active, retired |

### routing_steps

Primary key: `routing_step_id`.
Unique constraints: `[['routing_id', 'step_no']]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `routing_step_id` | string | yes |  |  | yes | Unique routing-step bridge key |
| `routing_id` | string | yes |  |  | no | Routing foreign key |
| `step_no` | integer | yes |  |  | no | One-based operation order; unique within routing |
| `duration_min` | integer | yes |  | minutes | no | Processing duration in minutes |
| `tooling_group` | string | no |  |  | no | Shared tooling group required by the step |

### machines

Primary key: `machine_id`.
Unique constraints: `[]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `machine_id` | string | yes |  |  | yes | MACH-001 style; unique |
| `name` | string | yes |  |  | no | Synthetic machine name |
| `capability` | string | yes |  |  | no | Machine capability class |
| `active` | boolean | yes |  |  | no | Whether the machine is schedulable |

### machine_calendars

Primary key: `calendar_id`.
Unique constraints: `[['machine_id', 'work_date', 'shift_code']]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `calendar_id` | string | yes |  |  | yes | Unique machine/date/shift key |
| `machine_id` | string | yes |  |  | no | Machine foreign key |
| `work_date` | integer | yes |  | days from fixed epoch | no | Day offset from the fixed epoch |
| `shift_start_min` | integer | yes |  | minutes from fixed epoch | no | Absolute minute from fixed epoch |
| `shift_end_min` | integer | yes |  | minutes from fixed epoch | no | Exclusive absolute shift end |
| `capacity_min` | integer | yes |  | minutes per shift | no | Shift capacity in minutes |
| `shift_code` | enum | yes | DAY |  | no | DAY |

### materials

Primary key: `material_id`.
Unique constraints: `[]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `material_id` | string | yes |  |  | yes | MAT-001 style; unique |
| `name` | string | yes |  |  | no | Synthetic material name |
| `unit` | enum | yes | kg, ea, m |  | no | kg, ea, m |
| `active` | boolean | yes |  |  | no | Whether material can be consumed |

### product_bom

Primary key: `bom_line_id`.
Unique constraints: `[['sku', 'material_id']]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `bom_line_id` | string | yes |  |  | yes | Unique bill-of-material bridge key |
| `sku` | string | yes |  |  | no | Product foreign key |
| `material_id` | string | yes |  |  | no | Material foreign key |
| `quantity_per_unit` | number | yes |  | material-specific units per finished product unit | no | Material units required per product unit |
| `effective_from_min` | integer | yes |  | minutes from fixed epoch | no | Effective start minute |
| `effective_to_min` | integer | no |  | minutes from fixed epoch | no | Exclusive end; null means current |

### production_orders

Primary key: `order_id`.
Unique constraints: `[]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `order_id` | string | yes |  |  | yes | PROD-2026-000001 style; immutable order key |
| `sku` | string | yes |  |  | no | Product foreign key |
| `routing_id` | string | yes |  |  | no | Effective routing foreign key |
| `quantity` | integer | yes |  | material-specific units | no | Positive units |
| `release_min` | integer | yes |  | minutes from fixed epoch | no | Release minute from fixed epoch |
| `due_min` | integer | yes |  | minutes from fixed epoch | no | Due minute from fixed epoch |
| `priority` | integer | yes | 1, 2, 3, 4, 5 |  | no | 1 (lowest) through 5 (highest) |
| `urgent` | boolean | yes |  |  | no | Urgent dispatch indicator |
| `lifecycle_state` | enum | yes | released, scheduled, completed, infeasible |  | no | released, scheduled, completed, infeasible |

### operations

Primary key: `operation_id`.
Unique constraints: `[]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `operation_id` | string | yes |  |  | yes | OP-<order-id>-01 style; unique |
| `order_id` | string | yes |  |  | no | Production order foreign key |
| `routing_step_id` | string | yes |  |  | no | Routing-step foreign key |
| `step_no` | integer | yes |  |  | no | One-based precedence position |
| `duration_min` | integer | yes |  | minutes | no | Processing duration in minutes |
| `predecessor_operation_id` | string | no |  |  | no | Previous operation in the same order |
| `tooling_group` | string | no |  |  | no | Required shared tooling group |

### machine_eligibility

Primary key: `eligibility_id`.
Unique constraints: `[['routing_step_id', 'machine_id']]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `eligibility_id` | string | yes |  |  | yes | Unique machine/step bridge key |
| `routing_step_id` | string | yes |  |  | no | Routing-step foreign key |
| `machine_id` | string | yes |  |  | no | Eligible machine foreign key |

### tooling

Primary key: `tooling_id`.
Unique constraints: `[]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `tooling_id` | string | yes |  |  | yes | TOOL-001 style; unique shared resource |
| `tooling_group` | string | yes |  |  | no | Group of compatible routing requirements |

### tooling_assignments

Primary key: `tooling_assignment_id`.
Unique constraints: `[['routing_step_id', 'tooling_id']]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `tooling_assignment_id` | string | yes |  |  | yes | Unique tooling/routing-step bridge key |
| `routing_step_id` | string | yes |  |  | no | Routing-step foreign key |
| `tooling_id` | string | yes |  |  | no | Shared tooling foreign key |

### inventory_lots

Primary key: `lot_id`.
Unique constraints: `[]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `lot_id` | string | yes |  |  | yes | LOT-001 style; unique |
| `material_id` | string | yes |  |  | no | Material foreign key |
| `available_min` | integer | yes |  | minutes from fixed epoch | no | Availability minute; may be delayed |
| `quantity` | number | yes |  | material-specific units | no | Positive available quantity |
| `lifecycle_state` | enum | yes | available, delayed, depleted |  | no | available, delayed, depleted |

### material_requirements

Primary key: `requirement_id`.
Unique constraints: `[['order_id', 'material_id']]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `requirement_id` | string | yes |  |  | yes | Unique order/material bridge key |
| `order_id` | string | yes |  |  | no | Production order foreign key |
| `material_id` | string | yes |  |  | no | Material foreign key |
| `lot_id` | string | yes |  |  | no | Allocated inventory lot foreign key |
| `quantity` | number | yes |  | material-specific units | no | Required material quantity |

### changeover_matrix

Primary key: `changeover_id`.
Unique constraints: `[['machine_id', 'from_family', 'to_family', 'effective_from_min']]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `changeover_id` | string | yes |  |  | yes | Unique machine/from-family/to-family key |
| `machine_id` | string | yes |  |  | no | Machine foreign key |
| `from_family` | string | yes |  |  | no | Previous product family |
| `to_family` | string | yes |  |  | no | Next product family |
| `setup_min` | integer | yes |  | minutes | no | Sequence-dependent setup duration in minutes |
| `effective_from_min` | integer | yes |  | minutes from fixed epoch | no | Effective start minute |

### machine_downtime_events

Primary key: `downtime_id`.
Unique constraints: `[]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `downtime_id` | string | yes |  |  | yes | Unique immutable downtime event key |
| `machine_id` | string | yes |  |  | no | Machine foreign key |
| `start_min` | integer | yes |  | minutes from fixed epoch | no | Absolute downtime start |
| `end_min` | integer | yes |  | minutes from fixed epoch | no | Exclusive downtime end |
| `reason` | enum | yes | maintenance, quality |  | no | maintenance, quality |

### operation_schedules

Primary key: `schedule_line_id`.
Unique constraints: `[]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `schedule_line_id` | string | yes |  |  | yes | Unique schedule-line key |
| `schedule_id` | string | yes |  |  | no | SCH-2026-000001 style; identifies a schedule version |
| `operation_id` | string | yes |  |  | no | Operation foreign key |
| `machine_id` | string | no |  |  | no | Assigned machine foreign key; null only for infeasible operations |
| `start_min` | integer | no |  | minutes from fixed epoch | no | Processing start minute; null only for infeasible operations |
| `end_min` | integer | no |  | minutes from fixed epoch | no | Exclusive processing end minute; null only for infeasible operations |
| `setup_start_min` | integer | no |  | minutes from fixed epoch | no | Setup interval start minute; null only for infeasible operations |
| `setup_min` | integer | yes |  | minutes | no | Applied setup duration |
| `tooling_id` | string | no |  |  | no | Assigned shared tooling foreign key |
| `status` | enum | yes | scheduled, infeasible |  | no | scheduled, infeasible |
| `infeasibility_reason` | string | no |  |  | no | Required when no feasible placement exists |

### material_consumption_events

Primary key: `consumption_event_id`.
Unique constraints: `[]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `consumption_event_id` | string | yes |  |  | yes | Unique immutable consumption event key |
| `schedule_id` | string | yes |  |  | no | Schedule version foreign key |
| `order_id` | string | yes |  |  | no | Order foreign key |
| `material_id` | string | yes |  |  | no | Material foreign key |
| `lot_id` | string | yes |  |  | no | Inventory lot foreign key |
| `consumed_min` | integer | yes |  | minutes from fixed epoch | no | Consumption event time |
| `quantity` | number | yes |  | material-specific units | no | Consumed material quantity |

### schedule_events

Primary key: `schedule_event_id`.
Unique constraints: `[]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `schedule_event_id` | string | yes |  |  | yes | Unique immutable schedule event key |
| `schedule_id` | string | yes |  |  | no | Schedule version |
| `event_type` | enum | yes | created, rescheduled, violated |  | no | created, rescheduled, violated |
| `event_min` | integer | yes |  | minutes from fixed epoch | no | Event time from fixed epoch |
| `entity_id` | string | yes |  |  | no | Affected order, operation, or schedule ID |
| `details` | string | yes |  |  | no | Traceability details |

### order_status_events

Primary key: `order_status_event_id`.
Unique constraints: `[]`.

| Field | Type | Required | Allowed values | Units | Unique | Validation |
|---|---|---:|---|---|---:|---|
| `order_status_event_id` | string | yes |  |  | yes | Unique immutable order status event key |
| `order_id` | string | yes |  |  | no | Production order foreign key |
| `old_state` | enum | no | released, scheduled, completed, infeasible |  | no | Null for initial state |
| `new_state` | enum | yes | released, scheduled, completed, infeasible |  | no | released, scheduled, completed, infeasible |
| `event_min` | integer | yes |  | minutes from fixed epoch | no | Event time from fixed epoch |

## Relationships

| From | To | Cardinality | Optional |
|---|---|---|---:|
| `products` | `routings` | 1:N | no |
| `routings` | `routing_steps` | 1:N | no |
| `routing_steps` | `machines` | N:M via machine_eligibility | no |
| `products` | `materials` | N:M via product_bom | no |
| `routing_steps` | `tooling` | N:M via tooling_assignments | yes |
| `production_orders` | `operations` | 1:N | no |
| `machines` | `machine_calendars` | 1:N | no |
| `materials` | `inventory_lots` | 1:N | no |
| `production_orders` | `material_requirements` | 1:N | no |
| `machines` | `changeover_matrix` | 1:N | no |
| `machines` | `machine_downtime_events` | 1:N | yes |
| `operations` | `operation_schedules` | 1:N across schedule versions | no |
| `production_orders` | `order_status_events` | 1:N event history | no |
