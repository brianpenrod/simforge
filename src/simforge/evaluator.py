"""Gate 3 outcome evaluator ??? rebuilt Oct 29 on the telemetry scorer.

Replaces the Oct 24 skeleton, whose run_suite trusted the grasp
callback's self-reported success (Astra review #2: a no-physics
callback scored 20/20, and a timeout counted as a rejection pass).

Rules of this harness (GATE_METRICS Gate 3, as amended Oct 28):
  - Execution scenarios are judged ONLY by scoring.evaluate_attempt
    over real telemetry from grasp.execute_plan in the real cell.
  - Rejection scenarios are judged ONLY by the validation path
    (plan_schema): the scenario passes iff validation raises AND the
    executor is never invoked. A timeout, IK error, or failed grasp is
    a FAILURE - never a rejection.
  - Gate 3 pass (ratified amendment, Oct 28): ALL scenarios meet their
    declared expectations AND a fresh-draw rerun agrees on >= 7/8
    scenario outcomes. "Same outcome" = same outcome CLASS:
    "success" | "rejected" | "failure" (failure causes may differ).
  - The unattended-suite bound (<= 20 min) is WALL-CLOCK for one full
    suite run on the build laptop, measured by gate3_run.py.

Perturbation rule (ratified Oct 24): the seed DRIVES the perturbations
- position jitter, yaw, friction - it is not a label. A rerun with a
seed offset is the fresh-draw rerun.
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

import mujoco
import numpy as np

from .plan_schema import validate_semantics, validate_syntax
from .scoring import CellIds, evaluate_attempt
from .sim.cell import load_cell, reset_home, step_checked

WORKSPACE = {"min": [-0.5, -0.4], "max": [0.7, 0.4]}  # frozen table extent


def perturb(scenario: dict) -> dict:
    rng = random.Random(scenario["seed"])
    x, y = scenario["part_position"]
    return {
        **scenario,
        "part_position": [x + rng.uniform(-0.010, 0.010), y + rng.uniform(-0.010, 0.010)],
        "yaw_deg": scenario.get("yaw_deg", 0.0) + rng.uniform(-10.0, 10.0),
        "friction_scale": scenario.get("friction_scale", 1.0) * rng.uniform(0.9, 1.1),
    }


def _zone_bounds(model):
    gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "target_zone")
    zp, zs = model.geom_pos[gid], model.geom_size[gid]
    return {"min": [float(zp[0] - zs[0]), float(zp[1] - zs[1])],
            "max": [float(zp[0] + zs[0]), float(zp[1] + zs[1])]}


def _setup_scene(draw):
    """Fresh cell with the draw applied (friction on part/table/pads,
    part at the jittered pose), settled. Returns (model, data, ids,
    rest_z, zone)."""
    model, data, pad_geoms = load_cell()
    reset_home(model, data)
    ids = CellIds(model, pad_geoms)
    px, py = draw["part_position"]
    yaw = np.radians(draw["yaw_deg"])
    fscale = draw["friction_scale"]
    part_gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "part_geom")
    table_gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "table_top")
    for gid in [part_gid, table_gid, *pad_geoms]:
        model.geom_friction[gid][0] = float(model.geom_friction[gid][0]) * fscale
    jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "part_free")
    adr = int(model.jnt_qposadr[jid])
    data.qpos[adr:adr + 3] = [px, py, 0.025]
    data.qpos[adr + 3:adr + 7] = [np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2)]
    mujoco.mj_forward(model, data)
    for _ in range(250):  # 0.5 s settle
        step_checked(model, data, 1)
    rest_z = float(data.xpos[ids.part_body][2])
    return model, data, ids, rest_z, _zone_bounds(model)


def _apply_shift(model, data, ids, shift):
    """perturbed_shift: the part is moved AFTER setup (the world changed
    under a plan made from stale state). Returns (before, after) part
    xy, both recorded in the result row."""
    before = [float(v) for v in data.xpos[ids.part_body][:2]]
    jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "part_free")
    adr = int(model.jnt_qposadr[jid])
    data.qpos[adr] += shift["dx"]
    data.qpos[adr + 1] += shift["dy"]
    mujoco.mj_forward(model, data)
    for _ in range(125):  # 0.25 s settle
        step_checked(model, data, 1)
    after = [float(v) for v in data.xpos[ids.part_body][:2]]
    return before, after


def _scene_state(nominal_xy):
    """Scene state for the validation path (reject scenarios). Zone
    bounds are read from the real cell; nothing is executed."""
    model, data, _ = load_cell()
    return {"parts": {"part": {"position": [nominal_xy[0], nominal_xy[1], 0.025]}},
            "zones": {"target_zone": _zone_bounds(model)},
            "table_height_m": 0.0, "workspace": WORKSPACE}


def _outcome_class(row) -> str:
    if row["expect"] == "reject":
        return "rejected" if row["passed"] else "failure"
    return "success" if row.get("success") else "failure"


def run_suite(scenarios: list[dict], out_path: str | Path,
              seed_offset: int = 0, execute_fn=None) -> dict:
    """Run every scenario; write the machine-readable summary; return it.

    execute_fn(model, data, plan, ids) -> samples; defaults to
    grasp.execute_plan. Injectable for tests only.
    """
    if execute_fn is None:
        from .grasp import execute_plan as execute_fn
    results = []
    t_start = time.time()
    for raw in scenarios:
        t0 = time.time()
        sc = {**raw, "seed": raw["seed"] + seed_offset}
        row = {"scenario": sc["name"], "seed": sc["seed"],
               "expect": sc["expect"], "executor_called": False}
        if sc["expect"] == "reject":
            # Judged by validation ONLY; the executor is never invoked.
            try:
                plan = validate_syntax(sc["plan"])
                validate_semantics(plan, _scene_state(sc["part_position"]))
                row.update({"passed": False, "success": False,
                            "failure_cause": "not_rejected"})
            except ValueError as exc:
                row.update({"passed": True, "success": False,
                            "rejection": str(exc)})
        else:
            draw = perturb(sc)
            row["perturbed"] = {
                "part_position": [round(v, 4) for v in draw["part_position"]],
                "yaw_deg": round(draw["yaw_deg"], 2),
                "friction_scale": round(draw["friction_scale"], 4)}
            try:
                model, data, ids, rest_z, zone = _setup_scene(draw)
                if "shift" in sc:
                    before, after = _apply_shift(model, data, ids, sc["shift"])
                    row["shift"] = {"before": [round(v, 4) for v in before],
                                    "after": [round(v, 4) for v in after]}
                row["executor_called"] = True
                samples = execute_fn(model, data, sc["plan"], ids)
                verdict = evaluate_attempt(samples, rest_z, zone)
                row.update(verdict)
                row["passed"] = bool(verdict["success"])
            except Exception as exc:
                row.update({"success": False, "passed": False,
                            "failure_cause": "timeout" if "30 s" in str(exc)
                            else "sim_error",
                            "error": f"{type(exc).__name__}: {exc}"})
        row["outcome_class"] = _outcome_class(row)
        row["wall_s"] = round(time.time() - t0, 3)
        results.append(row)
    summary = {"total": len(results),
               "expectations_met": sum(r["passed"] for r in results),
               "all_expectations_met": all(r["passed"] for r in results),
               "wall_s": round(time.time() - t_start, 3),
               "results": results}
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(summary, indent=2))
    return summary


def compare_runs(run_a: dict, run_b: dict) -> dict:
    """Fresh-draw agreement between two suite summaries, matched by
    scenario name, on outcome CLASS (success | rejected | failure)."""
    a = {r["scenario"]: r["outcome_class"] for r in run_a["results"]}
    b = {r["scenario"]: r["outcome_class"] for r in run_b["results"]}
    flips = [{"scenario": name, "run_a": a[name], "run_b": b[name]}
             for name in a if a[name] != b.get(name)]
    return {"total": len(a), "agreement": len(a) - len(flips),
            "flips": flips}
