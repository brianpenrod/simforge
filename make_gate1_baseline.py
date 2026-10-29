"""Record the Gate 1 golden baseline: tests/baselines/gate1_baseline.json.

Runs the frozen cell exactly as gate1_check.py does (shared loader, home
keyframe, 10,000 steps) and records the final state.

Stepping goes through the GUARDED stepper (step_checked): a simulator
fault during baseline generation must fail loudly here, never bake a
corrupt baseline silently. (Astra review #3, Oct 28.)

WARNING: running this RE-BLESSES the baseline. Do it only with the
founder's approval, and review the change with `git diff` before
committing - the diff IS the approval record.

Run from the repo root:  python make_gate1_baseline.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import mujoco

from simforge.sim.cell import load_cell, reset_home, step_checked

STEPS = 10_000
OUT = ROOT / "tests" / "baselines" / "gate1_baseline.json"


def main():
    model, data, _ = load_cell()
    reset_home(model, data)
    step_checked(model, data, STEPS)
    part_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "part")
    baseline = {
        "mujoco_version": mujoco.__version__,
        "steps": STEPS,
        "final_qpos": [float(v) for v in data.qpos],
        "final_qvel": [float(v) for v in data.qvel],
        "part_final_pos": [float(v) for v in data.xpos[part_id]],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    print(f"baseline written to {OUT.relative_to(ROOT)}")
    print(f"part_final_pos = {baseline['part_final_pos']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

