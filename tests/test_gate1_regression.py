"""Gate 1 golden-baseline regression.

Re-runs the frozen cell exactly as the baseline was recorded and compares
the final state. Any change to the scene, the friction pins, the loader,
or the MuJoCo version that alters the physics shows up here as a failure.

Re-blessing the baseline (make_gate1_baseline.py) requires the founder's
approval; the git diff of the baseline file is the approval record.

Stepping is guarded (Oct 28): if the simulator warns or resets during
the run, the test fails in the stepper before any comparison happens -
a baseline "match" produced by a repaired run would be worthless.
"""
import json
import pathlib

import mujoco
import numpy as np
import pytest

from simforge.sim.cell import load_cell, reset_home, step_checked

pytestmark = [pytest.mark.e2e, pytest.mark.regression]

BASELINE = pathlib.Path(__file__).resolve().parent / "baselines" / "gate1_baseline.json"
TOL = 1e-6


def test_gate1_baseline_unchanged():
    assert BASELINE.exists(), (
        "baseline missing - run `python make_gate1_baseline.py` (founder approval required)"
    )
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert mujoco.__version__ == baseline["mujoco_version"]

    model, data, _ = load_cell()
    reset_home(model, data)
    step_checked(model, data, baseline["steps"])

    qpos_diff = float(np.max(np.abs(data.qpos - np.array(baseline["final_qpos"]))))
    qvel_diff = float(np.max(np.abs(data.qvel - np.array(baseline["final_qvel"]))))
    assert qpos_diff <= TOL, f"final qpos drifted by {qpos_diff:.3e} (tol {TOL:.0e})"
    assert qvel_diff <= TOL, f"final qvel drifted by {qvel_diff:.3e} (tol {TOL:.0e})"

    part_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "part")
    part_diff = float(np.max(np.abs(data.xpos[part_id] - np.array(baseline["part_final_pos"]))))
    assert part_diff <= TOL, f"part final position drifted by {part_diff:.3e} (tol {TOL:.0e})"
