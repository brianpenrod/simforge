"""Gate 5 demonstration runs + viewer boundary check (Oct 30, 2026).

Design lock (founder decision A, Astra-reviewed): the acceptance
suite runs HEADLESS. Video footage comes from these separate,
genuine demonstration runs - real proposals, human decisions,
guarded executions, scoring, audit records - each with its own
run ID linked to its fixture definition in gate5_suite.json.

Viewer boundary (Astra correction, adopted): a passive MuJoCo
viewer is NOT automatically read-only - GUI synchronization can
write perturbations/controls back into the simulation. Before any
filmed run, `viewer-check` must prove the configuration preserves
the execution boundary for an untouched run:

  - the same fixture executed headless and with the viewer
    attached produces the same scorer verdict, final XY (<= 1e-9),
    and simulated duration (identical);
  - the applied-force array (xfrc_applied) is all-zero after the
    viewer run - the GUI wrote nothing back.

Demo runs refuse to start unless viewer_check.json records a pass
against the CURRENT candidate hashes. If the check fails, the
fallback is terminal capture plus clearly labeled replay.
Determinism claims are limited to final positions and duration -
no bit-for-bit trajectory claims anywhere.
"""
import argparse
import hashlib
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

RESULTS = ROOT / "results" / "gate5"
SUITE_MANIFEST = ROOT / "gate5_suite.json"


def _sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def _candidate_hashes():
    return {"guard": _sha("src/simforge/guard.py"),
            "gate5_suite": _sha("gate5_suite.json"),
            "gate5_demo": _sha("gate5_demo.py")}


def _imports():
    import mujoco
    import mujoco.viewer
    from simforge import evaluator, grasp
    from simforge.guard import AuditLog, run_guarded
    from simforge.scoring import evaluate_attempt
    return mujoco, evaluator, grasp, AuditLog, run_guarded, evaluate_attempt


def _build(evaluator, case):
    scenario = {"name": case["id"], "seed": case["seed"],
                "part_position": list(case["part_start"]),
                "expect": "success", "plan": {}}
    if case.get("target_zone_pos") is not None:
        scenario["target_zone_pos"] = list(case["target_zone_pos"])
    draw = evaluator.perturb(scenario)
    return evaluator._setup_scene(draw)


def _execute_with_viewer(mujoco, grasp, evaluate_attempt, model, data,
                         ids, rest_z, zone, plan, use_viewer):
    """Execute a plan; optionally with a passive viewer attached.

    Viewer sync happens ONLY on the executing thread, from the
    executor's log hook, which fires between motion segments - never
    while mj_step is running and never from a side thread. (A
    side-thread sync raced mj_step and MuJoCo refused the visual
    copy with 'mjData stack in use', observed Oct 31 on the first
    viewer-check run; this shape is the fix.) The viewer therefore
    updates at segment boundaries. Returns (verdict, xfrc_max_abs).
    """
    t0 = float(data.time)
    if not use_viewer:
        samples = grasp.execute_plan(model, data, plan, ids,
                                     log=lambda *a: None)
        verdict = dict(evaluate_attempt(samples, rest_z, zone))
        verdict["final_part_pos"] = [float(v) for v in data.xpos[ids.part_body]]
        verdict["sim_duration_s"] = float(data.time) - t0
        return verdict, 0.0
    import mujoco.viewer as viewer_mod
    with viewer_mod.launch_passive(model, data) as viewer:
        viewer.sync()
        samples = grasp.execute_plan(model, data, plan, ids,
                                     log=lambda *a: viewer.sync())
        verdict = dict(evaluate_attempt(samples, rest_z, zone))
        verdict["final_part_pos"] = [float(v) for v in data.xpos[ids.part_body]]
        verdict["sim_duration_s"] = float(data.time) - t0
        viewer.sync()
    xfrc_max = float(abs(data.xfrc_applied).max())
    return verdict, xfrc_max


def _guarded_case(imports, audit, case, run_id, approve, use_viewer):
    mujoco, evaluator, grasp, _AL, run_guarded, evaluate_attempt = imports
    model, data, ids, rest_z, zone = _build(evaluator, case)
    scene_state = evaluator._live_scene_state(model, data, ids)
    calls = {"n": 0}

    def executor(plan):
        calls["n"] += 1
        verdict, _xf = _execute_with_viewer(
            mujoco, grasp, evaluate_attempt, model, data, ids,
            rest_z, zone, plan, use_viewer)
        return verdict

    result = run_guarded(case["plan"], scene_state, executor, approve,
                         audit,
                         scene_provider=lambda: evaluator._live_scene_state(
                             model, data, ids),
                         run_id=run_id)
    return result, calls["n"]


def mode_viewer_check() -> None:
    imports = _imports()
    _mujoco, evaluator, _g, AuditLog, _rg, _ea = imports
    manifest = json.loads(SUITE_MANIFEST.read_text())
    case = manifest["demo_cases"][0]  # DEMO-1 center move
    audit = AuditLog(RESULTS / "audit_viewer_check.jsonl")
    headless, hc = _guarded_case(imports, audit, case,
                                 "viewer-check:headless",
                                 lambda plan: True, use_viewer=False)
    viewer_run, vc = _guarded_case(imports, audit, case,
                                   "viewer-check:viewer",
                                   lambda plan: True, use_viewer=True)
    # xfrc write-back evidence: one dedicated viewer run of the same
    # fixture, measuring the applied-force array afterwards.
    model, data, ids, rest_z, zone = _build(evaluator, case)
    from simforge.plan_schema import validate_syntax
    plan = validate_syntax(case["plan"])
    _v, xfrc_max = _execute_with_viewer(
        imports[0], imports[2], imports[5], model, data, ids,
        rest_z, zone, plan, use_viewer=True)
    same_verdict = (headless.outcome["success"] == viewer_run.outcome["success"]
                    == _v["success"])
    dpos = max(abs(a - b) for a, b in zip(headless.outcome["final_part_pos"],
                                         viewer_run.outcome["final_part_pos"]))
    ddur = abs(headless.outcome["sim_duration_s"]
               - viewer_run.outcome["sim_duration_s"])
    passed = (hc == vc == 1 and same_verdict and dpos <= 1e-9
              and ddur == 0.0 and xfrc_max == 0.0)
    payload = {"check": "viewer-boundary-equality",
               "fixture": case["id"], "passed": bool(passed),
               "headless": headless.outcome, "viewer": viewer_run.outcome,
               "max_final_xy_delta_m": dpos, "duration_delta_s": ddur,
               "xfrc_applied_max_abs_after_viewer_run": xfrc_max,
               "candidate_hashes": _candidate_hashes(),
               "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "viewer_check.json").write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))
    print("VIEWER CHECK:", "PASS" if passed else
          "FAIL - fall back to terminal capture + labeled replay")


def _display(run_id, case, plan_dict, scene_state):
    print()
    print(f"--- DEMO APPROVAL: {run_id} ---")
    if case.get("label"):
        print(f"Label            : {case['label']}")
    if case.get("request_text"):
        print(f"Operator request : {case['request_text']}")
    print(f"Proposed plan    : {plan_dict}")
    part = scene_state["parts"].get(plan_dict["part_id"])
    if part:
        pos = part["position"]
        print(f"Scene identity   : {plan_dict['part_id']} at "
              f"[{pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}]")
    zone = scene_state["zones"].get(plan_dict["target_zone"])
    if zone:
        print(f"Destination      : {plan_dict['target_zone']} x "
              f"{zone['min'][0]:.2f}..{zone['max'][0]:.2f}, y "
              f"{zone['min'][1]:.2f}..{zone['max'][1]:.2f}")
    return input("Approve execution? [y/N] ").strip().lower() == "y"


def mode_demo(attempt: str) -> None:
    check_path = RESULTS / "viewer_check.json"
    if not check_path.exists():
        raise SystemExit("REFUSED: run --mode viewer-check first")
    check = json.loads(check_path.read_text())
    if not check.get("passed"):
        raise SystemExit("REFUSED: viewer check did not pass - use the "
                         "terminal-capture fallback instead")
    if check.get("candidate_hashes") != _candidate_hashes():
        raise SystemExit("REFUSED: candidate changed since the viewer "
                         "check - re-run viewer-check")
    imports = _imports()
    _mujoco, evaluator, _g, AuditLog, _rg, _ea = imports
    manifest = json.loads(SUITE_MANIFEST.read_text())
    audit = AuditLog(RESULTS / "audit_demo.jsonl")
    records_path = RESULTS / f"demo_records_{attempt}.jsonl"
    if records_path.exists():
        raise SystemExit(f"REFUSED: demo attempt {attempt} already exists")
    mujoco, _ev, grasp, _AL, run_guarded, evaluate_attempt = imports
    for case in manifest["demo_cases"]:
        run_id = f"{attempt}:{case['id']}"
        # ONE scene build serves the approval display AND the
        # execution - the human approves the exact scene that runs.
        model, data, ids, rest_z, zone = _build(evaluator, case)
        scene_state = evaluator._live_scene_state(model, data, ids)
        calls = {"n": 0}

        def executor(plan, _c=calls):
            _c["n"] += 1
            verdict, _xf = _execute_with_viewer(
                mujoco, grasp, evaluate_attempt, model, data, ids,
                rest_z, zone, plan, use_viewer=True)
            return verdict

        def approve(plan, _case=case, _run_id=run_id, _ss=scene_state):
            return _display(_run_id, _case, _case["plan"], _ss)

        result = run_guarded(case["plan"], scene_state, executor,
                             approve, audit,
                             scene_provider=lambda: evaluator
                             ._live_scene_state(model, data, ids),
                             run_id=run_id)
        calls = calls["n"]
        rec = {"run_id": run_id, "case_id": case["id"],
               "kind": case.get("kind"), "label": case.get("label"),
               "guard_status": result.status, "executor_calls": calls,
               "physics": result.outcome
               if result.status == "executed" else None,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        with records_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        print(f"{case['id']}: {result.status} "
              f"(executor_calls={calls})")
        if result.status == "rejected":
            reason = input("Rejection reason (optional): ").strip()
            if reason:
                with records_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(
                        {"run_id": run_id, "event": "rejection_reason",
                         "reason": reason}) + "\n")
    print(f"DEMO RUNS COMPLETE ({attempt}). Records: {records_path.name}, "
          f"audit: audit_demo.jsonl")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gate 5 demo + viewer check")
    parser.add_argument("--mode", required=True,
                        choices=["viewer-check", "demo"])
    parser.add_argument("--attempt", default="D1")
    args = parser.parse_args()
    if args.mode == "viewer-check":
        mode_viewer_check()
    else:
        mode_demo(args.attempt)


if __name__ == "__main__":
    main()

