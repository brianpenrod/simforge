"""Admission-boundary + strict-schema tests (Oct 30, Astra review #4).

The P1 regression: before this batch, a plan naming a nonexistent
part on an EXECUTION scenario reached the executor unvalidated and
scored success, because validation ran only for expect="reject"
scenarios and the controller ignores part_id. These tests pin the
closure: one shared admission boundary, `expect` controls assertions
only, and a rejected-at-admission plan produces zero executor calls.
"""
import pytest

from simforge.evaluator import run_suite
from simforge.plan_schema import (validate_scene_state, validate_semantics,
                                  validate_syntax)

GOOD_PLAN = {"part_id": "part", "target_zone": "target_zone",
             "approach_height_m": 0.10, "speed_scale": 0.5}
SUCCESS_SC = {"name": "t_exec", "seed": 1, "part_position": [0.45, 0.0],
              "expect": "success", "plan": GOOD_PLAN}

SCENE = {"parts": {"part": {"position": [0.45, 0.0, 0.025]}},
         "zones": {"target_zone": {"min": [0.38, 0.21], "max": [0.52, 0.35]}},
         "table_height_m": 0.0,
         "workspace": {"min": [-0.5, -0.4], "max": [0.7, 0.4]}}


@pytest.mark.unit
def test_ghost_part_on_execution_path_never_reaches_the_executor(tmp_path):
    calls = []

    def spy(model, data, plan, ids):
        calls.append(plan)
        return []

    sc = dict(SUCCESS_SC, plan=dict(GOOD_PLAN, part_id="part_ghost"))
    s = run_suite([sc], tmp_path / "r.json", execute_fn=spy)
    row = s["results"][0]
    assert calls == []
    assert row["executor_called"] is False
    assert row["passed"] is False
    assert row["failure_cause"] == "admission_rejected"
    assert row["outcome_class"] == "rejected"


@pytest.mark.unit
def test_execution_path_receives_the_validated_plan_object(tmp_path):
    seen = {}

    def fake(model, data, plan, ids):
        seen["plan"] = plan
        return []

    s = run_suite([SUCCESS_SC], tmp_path / "r.json", execute_fn=fake)
    row = s["results"][0]
    assert row["executor_called"] is True
    # The executor gets the validated Plan, not the raw scenario dict.
    assert seen["plan"].part_id == "part"
    assert seen["plan"].approach_height_m == 0.10


@pytest.mark.unit
@pytest.mark.parametrize("bad", [
    dict(GOOD_PLAN, speed_scale="0.5"),        # string, not a number
    dict(GOOD_PLAN, speed_scale=True),         # bool coerced to 1.0 before
    dict(GOOD_PLAN, approach_height_m=None),   # TypeError before
    dict(GOOD_PLAN, speed_scale=[0.5]),        # TypeError before
    dict(GOOD_PLAN, units="cm"),               # extra key dropped before
    {k: v for k, v in GOOD_PLAN.items() if k != "speed_scale"},  # missing
    dict(GOOD_PLAN, approach_height_m=float("nan")),
    dict(GOOD_PLAN, approach_height_m=float("inf")),
])
def test_syntax_is_strict_and_raises_only_valueerror(bad):
    with pytest.raises(ValueError):
        validate_syntax(bad)


@pytest.mark.unit
def test_semantics_rejects_absurd_part_height():
    from simforge.plan_schema import Plan
    scene = {"parts": {"part": {"position": [0.45, 0.0, 1_000_000.0]}},
             "zones": SCENE["zones"], "table_height_m": 0.0,
             "workspace": SCENE["workspace"]}
    with pytest.raises(ValueError):
        validate_semantics(Plan("part", "target_zone", 0.10, 0.5), scene)


@pytest.mark.unit
@pytest.mark.parametrize("scene", [
    # inverted zone bounds
    {"parts": SCENE["parts"],
     "zones": {"target_zone": {"min": [0.52, 0.35], "max": [0.38, 0.21]}},
     "table_height_m": 0.0, "workspace": SCENE["workspace"]},
    # zone wholly outside the workspace
    {"parts": SCENE["parts"],
     "zones": {"target_zone": {"min": [2.0, 2.0], "max": [2.5, 2.5]}},
     "table_height_m": 0.0, "workspace": SCENE["workspace"]},
    # NaN table height
    {"parts": SCENE["parts"], "zones": SCENE["zones"],
     "table_height_m": float("nan"), "workspace": SCENE["workspace"]},
    # missing table height (was silently treated as 0.0 before)
    {"parts": SCENE["parts"], "zones": SCENE["zones"],
     "workspace": SCENE["workspace"]},
])
def test_scene_state_contract(scene):
    with pytest.raises(ValueError):
        validate_scene_state(scene)
