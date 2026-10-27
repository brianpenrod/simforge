"""Guard demo: propose one plan against the live cell and decide on it.

Run from the repo root:  python guard_demo.py
Type y to approve, anything else to reject. Nothing moves yet (the motion
stack arrives at Gate 2) - the demo executor records the decision so you
can watch the guard and the audit log work end to end.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import mujoco

from simforge.guard import AuditLog, run_guarded
from simforge.sim.cell import load_cell, reset_home


def live_scene_state():
    model, data, _ = load_cell()
    reset_home(model, data)
    pid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "part")
    x, y, z = (float(v) for v in data.xpos[pid])
    return {
        "parts": {"part": {"position": [x, y, z]}},
        "zones": {"target_zone": {"min": [0.38, 0.21], "max": [0.52, 0.35]}},
        "table_height_m": 0.0,
        "workspace": {"min": [-0.5, -0.4], "max": [0.7, 0.4]},
    }


def main():
    raw = {
        "part_id": "part",
        "target_zone": "target_zone",
        "approach_height_m": 0.10,
        "speed_scale": 0.5,
    }
    print("Proposed plan:", raw)

    def approve(plan):
        return input("Approve this plan? [y/N] ").strip().lower() == "y"

    def executor(plan):
        return "STUB: motion stack arrives at Gate 2 - execution recorded, nothing moved"

    audit = AuditLog(ROOT / "results" / "audit" / "audit_log.jsonl")
    result = run_guarded(raw, live_scene_state(), executor, approve, audit)
    print("Result:", result.status)
    print("Audit log:", audit.path)
    for line in audit.path.read_text(encoding="utf-8").splitlines()[-4:]:
        print(" ", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
