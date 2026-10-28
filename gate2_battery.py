"""Gate 2 battery (ratified, GATE_METRICS.md as amended Oct 24-28).

20 attempts = 5 part positions x 4 perturbation draws. Each draw's seed
DRIVES real variation (position jitter +-10 mm, yaw +-10 deg, friction
scale 0.9-1.1, via the shared evaluator.perturb) and the runner asserts
the draw actually changed the simulator state before stepping.

Every attempt is executed by grasp.execute_plan and judged ONLY by the
telemetry scorer. The runner writes one record per attempt by
construction, so no failure can be unlogged; the pass rule applies the
double-count arithmetic anyway (score = successes - unlogged failures).

Pass: score >= 18/20 AND every position >= 3/4.
Evidence: results/gate2/battery_results.json + battery_summary.txt.

Run from the repo root:  python gate2_battery.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import mujoco
import numpy as np

from simforge.evaluator import perturb
from simforge.grasp import execute_plan
from simforge.scoring import CellIds, evaluate_attempt
from simforge.sim.cell import load_cell, reset_home, step_checked

POSITIONS = {
    "P1_center": (0.45, 0.00),
    "P2_near_left": (0.35, -0.15),
    "P3_far_right": (0.55, 0.15),
    "P4_far_left": (0.30, 0.20),
    "P5_near_right": (0.60, -0.10),
}
SEEDS = [101, 202, 303, 404]
PLAN = {"part_id": "part", "target_zone": "target_zone",
        "approach_height_m": 0.10, "speed_scale": 0.5}
OUT_DIR = ROOT / "results" / "gate2"


def _zone_bounds(model):
    gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "target_zone")
    zp, zs = model.geom_pos[gid], model.geom_size[gid]
    return {"min": [float(zp[0] - zs[0]), float(zp[1] - zs[1])],
            "max": [float(zp[0] + zs[0]), float(zp[1] + zs[1])]}


def run_attempt(position_id, nominal_xy, seed):
    """One battery attempt. Returns the full result row (always logged)."""
    scenario = {"name": f"{position_id}_s{seed}", "seed": seed,
                "part_position": list(nominal_xy), "yaw_deg": 0.0,
                "friction_scale": 1.0, "expect": "success"}
    draw = perturb(scenario)
    px, py = draw["part_position"]
    yaw = np.radians(draw["yaw_deg"])
    fscale = draw["friction_scale"]

    model, data, pad_geoms = load_cell()
    reset_home(model, data)
    ids = CellIds(model, pad_geoms)

    # Friction draw: scale every surface the part touches, relative to
    # its loaded base value, so the draw changes the real contact
    # physics (part-table and part-pad pairs alike).
    part_gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "part_geom")
    table_gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "table_top")
    for gid in [part_gid, table_gid, *pad_geoms]:
        model.geom_friction[gid][0] = float(model.geom_friction[gid][0]) * fscale

    # Part pose draw: position the freejoint at the jittered pose.
    jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "part_free")
    adr = int(model.jnt_qposadr[jid])
    data.qpos[adr:adr + 3] = [px, py, 0.025]
    data.qpos[adr + 3:adr + 7] = [np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2)]
    mujoco.mj_forward(model, data)

    # The draw must have changed something real (Oct 28 rule).
    actual = np.array(data.xpos[ids.part_body])
    assert abs(fscale - 1.0) > 1e-9 or np.linalg.norm(actual[:2] - nominal_xy) > 1e-6, \
        f"perturbation draw for seed {seed} changed nothing"

    for _ in range(250):  # 0.5 s settle
        step_checked(model, data, 1)
    rest_z = float(data.xpos[ids.part_body][2])
    zone = _zone_bounds(model)

    row = {"position": position_id, "seed": seed,
           "perturbed": {"part_position": [round(px, 4), round(py, 4)],
                         "yaw_deg": round(draw["yaw_deg"], 2),
                         "friction_scale": round(fscale, 4)}}
    try:
        samples = execute_plan(model, data, PLAN, ids, log=lambda *a: None)
        row.update(evaluate_attempt(samples, rest_z, zone))
    except Exception as exc:  # Oct 28 pre-flight fix: ANY exception in an
        # attempt (guarded-stepper RuntimeError, QP solver failure, IK
        # error) is a logged attempt failure - never a dead battery run.
        row.update({"success": False,
                    "failure_cause": "timeout" if "30 s" in str(exc) else "sim_error",
                    "error": f"{type(exc).__name__}: {exc}"})
    row["failure_cause"] = row.get("failure_cause")
    return row


def _write_partial(rows):
    """Oct 28 pre-flight fix: persist results after EVERY attempt, so a
    hard crash mid-battery (OOM, solver segfault, Ctrl-C) loses at most
    the attempt in flight - not the 19 already measured."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "battery_results_partial.json").write_text(
        json.dumps({"completed": len(rows), "results": rows}, indent=2))


def main():
    rows = []
    for position_id, xy in POSITIONS.items():
        for seed in SEEDS:
            row = run_attempt(position_id, xy, seed)
            rows.append(row)
            _write_partial(rows)
            verdict = "PASS" if row["success"] else f"FAIL ({row['failure_cause']})"
            print(f"{position_id} seed {seed}: {verdict} "
                  f"rise={row.get('max_rise_m', 0):.3f} m hold={row.get('longest_hold_s', 0):.2f} s",
                  flush=True)

    successes = sum(r["success"] for r in rows)
    unlogged = sum(1 for r in rows if not r["success"] and not r.get("failure_cause"))
    score = successes - unlogged
    per_position = {}
    for position_id in POSITIONS:
        mine = [r for r in rows if r["position"] == position_id]
        per_position[position_id] = sum(r["success"] for r in mine)
    gate_pass = score >= 18 and all(v >= 3 for v in per_position.values())

    summary = {"total": len(rows), "successes": successes,
               "unlogged_failures": unlogged, "score": score,
               "per_position": per_position, "gate2_pass": gate_pass,
               "results": rows}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "battery_results.json").write_text(json.dumps(summary, indent=2))

    lines = [f"Gate 2 battery: {successes}/20 successes, score {score} "
             f"(unlogged failures: {unlogged})"]
    for pid, v in per_position.items():
        lines.append(f"  {pid}: {v}/4")
    lines.append(f"GATE 2 BATTERY: {'PASS' if gate_pass else 'FAIL'}")
    (OUT_DIR / "battery_summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if gate_pass else 1


if __name__ == "__main__":
    sys.exit(main())
