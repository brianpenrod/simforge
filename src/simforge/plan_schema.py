"""Gate 4 plan schema + validation (drafted Oct 24, 2026 per Red Cell).

A plan is FOUR fields. Anything richer is scope creep until Gates 1-3 pass.
Validation has two layers, both required before execution:
  - syntax: shape/types/ranges (what the ratified metrics originally checked)
  - semantics: the plan must make sense against the actual scene state
    (Red Cell amendment: a schema-valid plan can still command a grasp at
    empty coordinates or through the table; syntax alone proves nothing).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Plan:
    part_id: str
    target_zone: str
    approach_height_m: float  # gripper height above the part before descent
    speed_scale: float        # 0.1 - 1.0 multiplier on nominal motion speed


def validate_syntax(raw: dict) -> Plan:
    """Raise ValueError on any shape/type/range violation."""
    if not isinstance(raw, dict):
        raise ValueError("plan is not an object")
    missing = {"part_id", "target_zone", "approach_height_m", "speed_scale"} - raw.keys()
    if missing:
        raise ValueError(f"plan missing fields: {sorted(missing)}")
    if not isinstance(raw["part_id"], str) or not raw["part_id"]:
        raise ValueError("part_id must be a non-empty string")
    if not isinstance(raw["target_zone"], str) or not raw["target_zone"]:
        raise ValueError("target_zone must be a non-empty string")
    h = float(raw["approach_height_m"])
    if not (0.02 <= h <= 0.50):
        raise ValueError(f"approach_height_m out of range: {h}")
    s = float(raw["speed_scale"])
    if not (0.1 <= s <= 1.0):
        raise ValueError(f"speed_scale out of range: {s}")
    return Plan(raw["part_id"], raw["target_zone"], h, s)


def validate_semantics(plan: Plan, scene_state: dict) -> None:
    """Raise ValueError if the plan is syntactically fine but senseless.

    scene_state format (produced by the scene module):
      {"parts": {part_id: {"position": [x, y, z]}},
       "zones": {zone_name: {"min": [x, y], "max": [x, y]}},
       "table_height_m": float,
       "workspace": {"min": [x, y], "max": [x, y]}}
    """
    parts = scene_state.get("parts", {})
    if plan.part_id not in parts:
        raise ValueError(f"hallucinated or unknown part: {plan.part_id}")
    zones = scene_state.get("zones", {})
    if plan.target_zone not in zones:
        raise ValueError(f"unknown target zone: {plan.target_zone}")
    x, y, z = parts[plan.part_id]["position"]
    ws = scene_state["workspace"]
    if not (ws["min"][0] <= x <= ws["max"][0] and ws["min"][1] <= y <= ws["max"][1]):
        raise ValueError("part position outside workspace bounds")
    if z < scene_state.get("table_height_m", 0.0):
        raise ValueError("grasp target below table surface")
