"""Gate 3 outcome evaluator — rebuilt Oct 29 on the telemetry scorer;
admission-hardened Oct 30 per Astra review #4.

Rules of this harness (GATE_METRICS Gate 3, as amended Oct 28 and
clarified Oct 29):
  - EVERY scenario's plan passes the same admission boundary before
    anything executes: strict syntax (plan_schema.validate_syntax),
    then semantics against the LIVE scene state derived from the
    set-up simulator, with the parts table keyed by the actual body
    name bound in the cell - so the permitted part_id IS the bound
    simulator body. `expect` controls assertions only, never whether
    validation runs. (Oct 29 bypass: a part_ghost plan on an
    execution scenario executed and scored success.)
  - Execution outcomes are judged ONLY by scoring.evaluate_attempt
    over real telemetry. A plan rejected at admission is recorded as
    rejected (expectation missed if success was expected), with the
    executor never invoked.
  - Rejection scenarios are judged ONLY by validation. Scene
    construction happens OUTSIDE the validation try: a construction
    failure is a harness failure row, never a rejection.
  - A timeout, IK error, or failed grasp is a FAILURE - never a
    rejection.
  - Gate 3 pass (ratified amendment, Oct 28): ALL scenarios meet their
    declared expectations AND a fresh-draw rerun agrees on >= 7/8
    scenario outcomes (same outcome CLASS: success|rejected|failure).
  - The <= 20 min suite bound is WALL-CLOCK for one full suite run,
    measured by gate3_run.py.
  - A scenario may relocate the target zone for its run
    ("target_zone_pos": [x, y]): the geom moves at setup and every
    downstream reader (controller, scorer zone bounds) follows it.
    This is how Gate 3's target-variation coverage is demonstrated.

Perturbation rule (ratified Oct 24): the seed DRIVES the perturbations
- position jitter, yaw, friction - it is not a label.
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
REQUIRED_SCENARIO_KEYS = {"name", "seed", "part_position", "expect", "plan"}


def perturb(scenario: dict) -> dict:
    rng = random.Random(scenario["seed"])
    x, y = scenario["part_position"]
    return {
        **scenario,
        "part_position": [x + rng.uniform(-0.010, 0.010), y + rng.uniform(-0.010, 0.010)],
        "yaw_deg": scenario.get("yaw_deg", 0.0) + rng.uniform(-10.0, 10.0),
        "friction_scale": scenario.get("friction_scale", 1.0) * rng.uniform(0.9, 1.1),
    }


def _preflight(scenarios) -> None:
    """Manifest check (Astra review #4): required keys, unique names,
    supported expectations - verified BEFORE any execution or output,
    so a malformed fixture fails visibly instead of crashing mid-suite
    and leaving stale evidence looking current."""
    names = set()
    for sc in scenarios:
        if not isinstance(sc, dict):
            raise ValueError("scenario is not an object")
        missing = REQUIRED_SCENARIO_KEYS - sc.keys()
        if missing:
            raise ValueError(
                f"scenario {sc.get('name', '?')!r}: missing keys {sorted(missing)}")
        if sc["name"] in names:
            raise ValueError(f"duplicate scenario name: {sc['name']!r}")
        names.add(sc["name"])
        if sc["expect"] not in ("success", "reject"):
            raise ValueError(
                f"scenario {sc['name']!r}: unsupported expect {sc['expect']!r}")


def _zone_bounds(model):
    gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "target_zone")
    zp, zs = model.geom_pos[gid], model.geom_size[gid]
    return {"min": [float(zp[0] - zs[0]), float(zp[1] - zs[1])],
            "max": [float(zp[0] + zs[0]), float(zp[1] + zs[1])]}


def _setup_scene(draw):
    """Fresh cell with the draw applied (friction on part/table/pads,
    part at the jittered pose, optional target relocation), settled.
    Returns (model, data, ids, rest_z, zone)."""
    model, data, pad_geoms = load_cell()
    reset_home(model, data)
    ids = CellIds(model, pad_geoms)
    zone_pos = draw.get("target_zone_pos")
    if zone_pos is not None:
        gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "target_zone")
        model.geom_pos[gid] = [float(zone_pos[0]), float(zone_pos[1]),
                               float(model.geom_pos[gid][2])]
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


def _live_scene_state(model, data, ids):
    """Scene state derived from the ACTUAL set-up simulator, keyed by
    the bound body name - admission semantics run against this, never
    against a hand-built approximation."""
    bound_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY,
                                    ids.part_body)
    pos = data.xpos[ids.part_body]
    return {"parts": {bound_name: {"position": [float(pos[0]), float(pos[1]),
                                                float(pos[2])]}},
            "zones": {"target_zone": _zone_bounds(model)},
            "table_height_m": 0.0, "workspace": WORKSPACE}


def _reject_scene_state(nominal_xy):
    """Scene state for the validation path (reject scenarios). Zone
    bounds are read from the real cell; nothing is executed. Called
    OUTSIDE the validation try by the caller."""
    model, data, _ = load_cell()
    return {"parts": {"part": {"position": [nominal_xy[0], nominal_xy[1], 0.025]}},
            "zones": {"target_zone": _zone_bounds(model)},
            "table_height_m": 0.0, "workspace": WORKSPACE}


def _outcome_class(row) -> str:
    if row.get("failure_cause") == "admission_rejected":
        return "rejected"
    if row["expect"] == "reject":
        return "rejected" if row["passed"] else "failure"
    return "success" if row.get("success") else "failure"


def run_suite(scenarios: list[dict], out_path: str | Path,
              seed_offset: int = 0, execute_fn=None) -> dict:
    """Run every scenario; write the machine-readable summary; return it.

    execute_fn(model, data, plan, ids) -> samples; defaults to
    grasp.execute_plan and receives the VALIDATED Plan. Injectable
    for tests only.
    """
    _preflight(scenarios)
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
            # Scene construction FIRST, outside the validation try: a
            # construction failure is a harness failure, not a rejection.
            try:
                state = _reject_scene_state(sc["part_position"])
            except Exception as exc:
                row.update({"passed": False, "success": False,
                            "failure_cause": "harness_error",
                            "error": f"{type(exc).__name__}: {exc}"})
            else:
                try:
                    plan = validate_syntax(sc["plan"])
                    validate_semantics(plan, state)
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
            if draw.get("target_zone_pos") is not None:
                row["target_zone_pos"] = [float(v) for v in draw["target_zone_pos"]]
            try:
                model, data, ids, rest_z, zone = _setup_scene(draw)
            except Exception as exc:
                row.update({"success": False, "passed": False,
                            "failure_cause": "sim_error",
                            "error": f"{type(exc).__name__}: {exc}"})
            else:
                if "shift" in sc:
                    before, after = _apply_shift(model, data, ids, sc["shift"])
                    row["shift"] = {"before": [round(v, 4) for v in before],
                                    "after": [round(v, 4) for v in after]}
                # SHARED ADMISSION BOUNDARY: every execution-bound plan
                # is validated against the live scene first. `expect`
                # never decides whether this runs.
                try:
                    plan = validate_syntax(sc["plan"])
                    validate_semantics(
                        plan, _live_scene_state(model, data, ids))
                except ValueError as exc:
                    row.update({"success": False, "passed": False,
                                "failure_cause": "admission_rejected",
                                "rejection": str(exc)})
                else:
                    row["executor_called"] = True
                    try:
                        samples = execute_fn(model, data, plan, ids)
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
    flips = [{"scenario": name, "run_a": a[name], "run_b": b.get(name)}
             for name in a if a[name] != b.get(name)]
    return {"total": len(a), "agreement": len(a) - len(flips),
            "flips": flips}
