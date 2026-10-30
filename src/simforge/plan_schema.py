"""Gate 4 plan schema + validation (drafted Oct 24, 2026 per Red Cell;
hardened Oct 29-30 per Astra reviews #3 and #4).

A plan is FOUR fields - exactly four. Validation layers, all required
before execution:
  - syntax: exact key set; identifiers are non-empty strings; motion
    values are JSON numbers (int/float, never bool), finite, in range.
    NO coercion: the string "0.5" is not a number and an extra key is
    not silently dropped - both are rejections. Every failure raises
    ValueError (never TypeError), so callers rely on one exception type.
  - scene contract: the scene state itself is validated (complete,
    finite, ordered bounds with positive dimensions; zones inside the
    workspace; a real finite table height). A validator that trusts
    its reference data proves nothing.
  - semantics: the plan must make sense against the validated scene
    (known part/zone, part inside the workspace, part height inside
    the frozen cell's operational envelope).

Oct 29: validate_semantics rejects non-finite part coordinates
explicitly (Hypothesis property catch; NaN comparisons are False).
Oct 30 (Astra review #4): strict syntax, scene-state contract,
part-height envelope.
Oct 30 (Astra review #5, design lock v2): parse_plan() — the raw-text
entry point. Duplicate keys and NaN/Infinity literals are invisible
to dict-level validation, so they are rejected at parse time, before
a dict ever exists. Every raw plan entering the system (model output,
injected case, file) goes through here.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass

FIELDS = {"part_id", "target_zone", "approach_height_m", "speed_scale"}
MAX_PART_HEIGHT_ABOVE_TABLE_M = 0.5  # frozen-cell operational envelope


@dataclass
class Plan:
    part_id: str
    target_zone: str
    approach_height_m: float  # gripper height above the part before descent
    speed_scale: float        # 0.1 - 1.0 multiplier on nominal motion speed


def _is_json_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _no_duplicates(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate key in plan JSON: {key!r}")
        obj[key] = value
    return obj


def _no_nonfinite_literals(name):
    raise ValueError(f"non-finite literal in plan JSON: {name}")


def parse_plan(text) -> Plan:
    """Parse raw JSON text into a validated Plan. Raises ValueError on
    malformed JSON, duplicate keys, NaN/Infinity literals, a non-object
    document, or any syntax violation. This is the ONLY way raw text
    becomes a plan; callers never json.loads() a plan themselves."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("plan text is empty")
    try:
        raw = json.loads(text,
                         object_pairs_hook=_no_duplicates,
                         parse_constant=_no_nonfinite_literals)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"plan is not valid JSON: {exc}") from exc
    return validate_syntax(raw)


def validate_syntax(raw: dict) -> Plan:
    """Raise ValueError on any shape/type/range violation. Strict:
    exact key set, no coercion, finite JSON numbers only."""
    if not isinstance(raw, dict):
        raise ValueError("plan is not an object")
    keys = set(raw.keys())
    if keys != FIELDS:
        raise ValueError(
            f"plan fields must be exactly {sorted(FIELDS)}; "
            f"missing={sorted(FIELDS - keys)}, extra={sorted(keys - FIELDS)}")
    if not isinstance(raw["part_id"], str) or not raw["part_id"]:
        raise ValueError("part_id must be a non-empty string")
    if not isinstance(raw["target_zone"], str) or not raw["target_zone"]:
        raise ValueError("target_zone must be a non-empty string")
    for name, lo, hi in (("approach_height_m", 0.02, 0.50),
                         ("speed_scale", 0.1, 1.0)):
        v = raw[name]
        if not _is_json_number(v):
            raise ValueError(
                f"{name} must be a JSON number, got {type(v).__name__}")
        if not math.isfinite(v):
            raise ValueError(f"{name} is not finite: {v}")
        if not (lo <= v <= hi):
            raise ValueError(f"{name} out of range: {v}")
    return Plan(raw["part_id"], raw["target_zone"],
                float(raw["approach_height_m"]), float(raw["speed_scale"]))


def _check_bounds(bounds, label):
    try:
        lo, hi = bounds["min"], bounds["max"]
        vals = [float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1])]
    except Exception as exc:
        raise ValueError(f"{label}: malformed bounds") from exc
    if not all(math.isfinite(v) for v in vals):
        raise ValueError(f"{label}: bounds are not finite")
    if not (vals[0] < vals[2] and vals[1] < vals[3]):
        raise ValueError(
            f"{label}: bounds are not ordered with positive dimensions")
    return vals


def validate_scene_state(scene_state: dict) -> None:
    """Raise ValueError if the scene state itself is untrustworthy:
    incomplete, non-finite, inverted, or self-contradictory."""
    if not isinstance(scene_state, dict):
        raise ValueError("scene state is not an object")
    for key in ("parts", "zones", "table_height_m", "workspace"):
        if key not in scene_state:
            raise ValueError(f"scene state missing '{key}'")
    table = scene_state["table_height_m"]
    if not _is_json_number(table) or not math.isfinite(table):
        raise ValueError("table_height_m is not a finite number")
    ws = _check_bounds(scene_state["workspace"], "workspace")
    for name, zone in scene_state["zones"].items():
        zb = _check_bounds(zone, f"zone '{name}'")
        if not (ws[0] <= zb[0] and ws[1] <= zb[1]
                and zb[2] <= ws[2] and zb[3] <= ws[3]):
            raise ValueError(f"zone '{name}' lies outside the workspace")
    for pid, part in scene_state["parts"].items():
        try:
            pos = part["position"]
            vals = [float(pos[0]), float(pos[1]), float(pos[2])]
        except Exception as exc:
            raise ValueError(f"part '{pid}': malformed position") from exc
        if not all(math.isfinite(v) for v in vals):
            raise ValueError(f"part '{pid}': position is not finite")


def validate_semantics(plan: Plan, scene_state: dict) -> None:
    """Raise ValueError if the plan is syntactically fine but senseless
    against a scene state that must itself validate first.

    scene_state format (produced from the actual simulator):
      {"parts": {part_id: {"position": [x, y, z]}},
       "zones": {zone_name: {"min": [x, y], "max": [x, y]}},
       "table_height_m": float,
       "workspace": {"min": [x, y], "max": [x, y]}}
    """
    validate_scene_state(scene_state)
    parts = scene_state["parts"]
    if plan.part_id not in parts:
        raise ValueError(f"hallucinated or unknown part: {plan.part_id}")
    zones = scene_state["zones"]
    if plan.target_zone not in zones:
        raise ValueError(f"unknown target zone: {plan.target_zone}")
    x, y, z = (float(v) for v in parts[plan.part_id]["position"])
    ws = scene_state["workspace"]
    if not (ws["min"][0] <= x <= ws["max"][0]
            and ws["min"][1] <= y <= ws["max"][1]):
        raise ValueError("part position outside workspace bounds")
    table = float(scene_state["table_height_m"])
    if z < table:
        raise ValueError("grasp target below table surface")
    if z > table + MAX_PART_HEIGHT_ABOVE_TABLE_M:
        raise ValueError(
            "part height outside the cell's operational envelope")
