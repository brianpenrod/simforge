"""Unit tests for the Gate 4 plan validator (src/simforge/plan_schema.py).

A plan may only execute if BOTH layers accept it:
  syntax    - shape, types, ranges
  semantics - the plan makes sense against the actual scene state
These tests pin both layers, including the hallucination cases.
"""
import pytest

from simforge.plan_schema import Plan, validate_semantics, validate_syntax

pytestmark = pytest.mark.unit

VALID_RAW = {
    "part_id": "part",
    "target_zone": "target_zone",
    "approach_height_m": 0.10,
    "speed_scale": 0.5,
}

SCENE_STATE = {
    "parts": {"part": {"position": [0.45, 0.0, 0.025]}},
    "zones": {"target_zone": {"min": [0.38, 0.21], "max": [0.52, 0.35]}},
    "table_height_m": 0.0,
    "workspace": {"min": [-0.5, -0.4], "max": [0.7, 0.4]},
}


def test_valid_plan_passes_syntax():
    plan = validate_syntax(VALID_RAW)
    assert isinstance(plan, Plan)
    assert plan.part_id == "part"
    assert plan.approach_height_m == pytest.approx(0.10)
    assert plan.speed_scale == pytest.approx(0.5)


def test_missing_field_rejected():
    raw = {k: v for k, v in VALID_RAW.items() if k != "speed_scale"}
    with pytest.raises(ValueError):
        validate_syntax(raw)


def test_non_object_rejected():
    with pytest.raises(ValueError):
        validate_syntax(["not", "a", "plan"])


@pytest.mark.parametrize("bad_height", [0.01, 0.60])
def test_approach_height_out_of_range_rejected(bad_height):
    with pytest.raises(ValueError):
        validate_syntax({**VALID_RAW, "approach_height_m": bad_height})


@pytest.mark.parametrize("bad_speed", [0.05, 1.50])
def test_speed_scale_out_of_range_rejected(bad_speed):
    with pytest.raises(ValueError):
        validate_syntax({**VALID_RAW, "speed_scale": bad_speed})


def test_valid_plan_passes_semantics():
    plan = validate_syntax(VALID_RAW)
    validate_semantics(plan, SCENE_STATE)  # must not raise


def test_hallucinated_part_rejected():
    plan = validate_syntax({**VALID_RAW, "part_id": "ghost_part"})
    with pytest.raises(ValueError):
        validate_semantics(plan, SCENE_STATE)


def test_unknown_zone_rejected():
    plan = validate_syntax({**VALID_RAW, "target_zone": "zone_99"})
    with pytest.raises(ValueError):
        validate_semantics(plan, SCENE_STATE)


def test_part_outside_workspace_rejected():
    state = {
        **SCENE_STATE,
        "parts": {"part": {"position": [0.90, 0.0, 0.025]}},
    }
    plan = validate_syntax(VALID_RAW)
    with pytest.raises(ValueError):
        validate_semantics(plan, state)


def test_part_below_table_rejected():
    state = {
        **SCENE_STATE,
        "parts": {"part": {"position": [0.45, 0.0, -0.05]}},
    }
    plan = validate_syntax(VALID_RAW)
    with pytest.raises(ValueError):
        validate_semantics(plan, state)
