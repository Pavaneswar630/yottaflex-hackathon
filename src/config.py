"""Shared deterministic generator settings."""

from dataclasses import dataclass

EPOCH = "2026-01-01T00:00:00Z"
MINUTES_PER_DAY = 24 * 60
DEFAULT_SEED = 20261022


@dataclass(frozen=True)
class Scale:
    skus: int = 100
    machines: int = 40
    orders: int = 500
    materials: int = 200
    operations_per_order: int = 4
    horizon_days: int = 180


def format_id(prefix: str, number: int, width: int = 3) -> str:
    return f"{prefix}-{number:0{width}d}"
