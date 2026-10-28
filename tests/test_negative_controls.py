"""Negative controls (ratified Oct 27, 2026 - red-cell amendments).

A test suite that cannot say "fail" proves nothing. These two controls
prove the measuring instruments themselves work:

NC-1  The Gate 2 lift criterion must FAIL on a run where nothing is
      commanded. If a no-op run could "pass" the lift test, the metric
      would be vacuous. (Gate 3 extends this pattern to scenario
      outcomes; the validation-layer version lives in
      test_plan_validation.py - a hallucinated part must be rejected.)

NC-2  The friction settings must measurably change the physics. The same
      push is applied to the part at normal friction and at near-zero
      friction; the outcomes must differ widely. If they did not, the
      friction pin would be inert and every grasp result suspect.

All stepping goes through the guarded stepper (Oct 28 fix): a run the
simulator warned on or silently reset must fail here, not pass.
"""
import mujoco
import pytest

from simforge.sim.cell import load_cell, reset_home, step_checked

pytestmark = pytest.mark.e2e

PART_REST_Z = 0.025
LIFT_THRESHOLD_M = 0.05  # Gate 2: part center must rise >= 5 cm


def _part_body(model):
    return mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "part")


def test_nc1_noop_run_fails_lift_criterion():
    model, data, _ = load_cell()
    reset_home(model, data)
    bid = _part_body(model)
    start_z = float(data.xpos[bid][2])
    max_rise = 0.0
    for _ in range(1000):  # 2 s of sim time, no commands at all
        step_checked(model, data, 1)
        max_rise = max(max_rise, float(data.xpos[bid][2]) - start_z)
    # The lift criterion (>= 5 cm rise) must NOT be met by doing nothing.
    assert max_rise < LIFT_THRESHOLD_M, (
        f"no-op run rose {max_rise:.4f} m - the lift criterion would be vacuous"
    )
    # And the part should still be resting on the table.
    assert abs(float(data.xpos[bid][2]) - PART_REST_Z) < 0.002


def _push_displacement(friction: float) -> float:
    """Push the part sideways with a constant 0.5 N force for 0.2 s of sim
    time at the given sliding-friction value; return x displacement (m)."""
    model, data, _ = load_cell()
    for geom_name in ("part_geom", "table_top"):
        gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, geom_name)
        model.geom_friction[gid][0] = friction
    reset_home(model, data)
    bid = _part_body(model)
    start_x = float(data.xpos[bid][0])
    data.xfrc_applied[bid] = [0.5, 0.0, 0.0, 0.0, 0.0, 0.0]
    step_checked(model, data, 100)  # 0.2 s at the 0.002 s timestep
    return float(data.xpos[bid][0]) - start_x


def test_nc2_friction_changes_physics():
    stuck = _push_displacement(1.0)     # pinned friction: must hold
    sliding = _push_displacement(0.02)  # near-zero friction: must slide
    # Absolute bounds (Oct 28 fix): a signed '<' would pass on any large
    # negative displacement.
    assert abs(stuck) < 0.002, f"part moved {stuck:+.4f} m at full friction"
    assert abs(sliding) > 0.05, f"part only moved {sliding:+.4f} m at near-zero friction"
