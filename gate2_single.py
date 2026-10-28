"""Gate 2 single instrumented attempt (Oct 28) - the tuning run.

One nominal full cycle at the scene's default part position, judged by
the telemetry scorer. Prints diagnostics first (mink/quadprog
availability), the controller's phase log, and the scorer's verdict.

Run from the repo root:  python gate2_single.py
"""
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import mink
import mujoco

from simforge.grasp import execute_plan
from simforge.scoring import CellIds, evaluate_attempt
from simforge.sim.cell import load_cell, reset_home, step_checked

PLAN = {"part_id": "part", "target_zone": "target_zone",
        "approach_height_m": 0.10, "speed_scale": 0.5}


def main():
    print(f"mink {getattr(mink, '__version__', '?')}, "
          f"quadprog available: {importlib.util.find_spec('quadprog') is not None}")
    model, data, pad_geoms = load_cell()
    reset_home(model, data)
    ids = CellIds(model, pad_geoms)

    zone_gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "target_zone")
    zp, zs = model.geom_pos[zone_gid], model.geom_size[zone_gid]
    zone = {"min": [float(zp[0] - zs[0]), float(zp[1] - zs[1])],
            "max": [float(zp[0] + zs[0]), float(zp[1] + zs[1])]}
    print(f"zone bounds from geom: {zone}")

    for _ in range(250):  # 0.5 s settle at the home keyframe
        step_checked(model, data, 1)
    rest_z = float(data.xpos[ids.part_body][2])
    print(f"part rest z = {rest_z:.6f}, plan = {PLAN}")

    samples = execute_plan(model, data, PLAN, ids)
    result = evaluate_attempt(samples, rest_z, zone)
    print("\nSCORER VERDICT:")
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
