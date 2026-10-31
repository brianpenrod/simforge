"""Gate 4 runner - design lock v2 (ratified Oct 30, 2026).

Modes:
  plumbing   ONE live propose_plan against the real endpoint with a
             trivial scene. Proves the adapter path end to end
             (including reasoning_effort acceptance) BEFORE the
             freeze. Not a sample call; never graded.
  sample-c   Deterministic validator injections (no model): unknown
             part, known zone with out-of-workspace bounds, below-table
             scene fixture, strict types, extra key, duplicate keys,
             NaN literal, malformed, empty, plus one valid control.
             Every case runs through the production guard with a
             counting executor; only the control may execute.
  sample-d   Stub fault matrix: the production adapter/parser/guard
             path against the local stub endpoint (valid, malformed,
             empty, truncated, slow-timeout, HTTP 500). Verifies the
             exact request count per case (no hidden SDK retries).
  causality  Sample B rehearsal with derived controls (offline, real
             physics): B1 identical plan twice; B2 explicit copies at
             speed 0.3 vs 0.9 (ratified criterion: duration difference
             >= 0.1 s, both successful); B3 rejected-plan control.
             Simulated duration is scored; wall time is diagnostic.
  freeze     Hash the manifest, code, and system prompt into
             results/gate4/freeze.json. Sample A refuses to run
             against anything else.
  sample-a   The ten graded live calls (+ supplemental S1). Human
             approval per admitted plan (design lock D1): the display
             shows the original request and the proposal's ACTUAL
             scene identity together; the response is graded before
             approval; approval cannot launder a wrong proposal.
"""
import argparse
import hashlib
import json
import os
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from simforge import evaluator, grasp  # noqa: E402
from simforge.guard import AuditLog, run_guarded  # noqa: E402
from simforge.model_adapter import SYSTEM_PROMPT, ModelAdapter, ModelConfig  # noqa: E402
from simforge.plan_schema import (  # noqa: E402
    _no_duplicates, _no_nonfinite_literals, validate_semantics, validate_syntax)
from simforge.scoring import evaluate_attempt  # noqa: E402

RESULTS = ROOT / "results" / "gate4"
MANIFEST = ROOT / "gate4_requests.json"
FREEZE_FILES = ["gate4_requests.json", "gate4_run.py", "gate4_stub.py",
                "src/simforge/model_adapter.py", "src/simforge/plan_schema.py",
                "src/simforge/guard.py", "src/simforge/evaluator.py"]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(name: str, payload: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / name
    path.write_text(json.dumps(payload, indent=2))
    return path


def load_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_scene(part_start, seed, target_zone_pos=None):
    """Perturbed, settled scene exactly as the Gate 2/3 suites build
    it. Returns (model, data, ids, rest_z, zone, scene_state, draw)."""
    scenario = {"name": "gate4", "seed": seed,
                "part_position": list(part_start), "expect": "success",
                "plan": {}}
    if target_zone_pos is not None:
        scenario["target_zone_pos"] = list(target_zone_pos)
    draw = evaluator.perturb(scenario)
    model, data, ids, rest_z, zone = evaluator._setup_scene(draw)
    scene_state = evaluator._live_scene_state(model, data, ids)
    return model, data, ids, rest_z, zone, scene_state, draw


def layered_grade(raw_text, scene_state):
    """Grade the response layers with the production functions.
    Returns (raw_dict, plan, first_failed_layer, error). Layers:
    parse (raw JSON, duplicate keys and NaN/Infinity rejected),
    syntax (strict schema), semantics (against this scene)."""
    if raw_text is None:
        return None, None, "api_error", None
    try:
        raw = json.loads(raw_text, object_pairs_hook=_no_duplicates,
                         parse_constant=_no_nonfinite_literals)
    except Exception as exc:
        return None, None, "parse", str(exc)
    if not isinstance(raw, dict):
        return None, None, "parse", "plan is not an object"
    try:
        plan = validate_syntax(raw)
    except ValueError as exc:
        return raw, None, "syntax", str(exc)
    try:
        validate_semantics(plan, scene_state)
    except ValueError as exc:
        return raw, plan, "semantics", str(exc)
    return raw, plan, None, None


def grade_checks(plan, case, scene_state):
    out = []
    for check in case.get("checks", []):
        ctype = check["type"]
        if ctype == "admitted":
            out.append({**check, "passed": plan is not None})
        elif ctype == "relocated_zone":
            zone = scene_state["zones"]["target_zone"]
            ok = all(abs(a - b) <= 1e-6 for a, b in
                     zip(zone["min"] + zone["max"],
                         check["min"] + check["max"]))
            out.append({**check, "passed": bool(ok)})
        elif ctype in ("param_gt", "param_lt", "param_gte"):
            value = getattr(plan, check["param"]) if plan else None
            fn = {"param_gt": lambda v: v > check["value"],
                  "param_lt": lambda v: v < check["value"],
                  "param_gte": lambda v: v >= check["value"]}[ctype]
            out.append({**check, "passed": bool(value is not None and fn(value))})
        elif ctype == "param_exact":
            value = getattr(plan, check["param"]) if plan else None
            ok = (value is not None
                  and abs(value - check["value"]) <= check["tol"])
            out.append({**check, "passed": bool(ok)})
        elif ctype == "no_unvalidated_execution":
            out.append({**check, "passed": None,
                        "note": "evaluated from the guard outcome"})
    return out


def execute_and_score(model, data, ids, rest_z, zone, plan):
    t0 = float(data.time)
    samples = grasp.execute_plan(model, data, plan, ids, log=lambda *a: None)
    verdict = dict(evaluate_attempt(samples, rest_z, zone))
    verdict["final_part_pos"] = [float(v) for v in data.xpos[ids.part_body]]
    verdict["sim_duration_s"] = float(data.time) - t0
    return verdict


# ---------------------------------------------------------------- plumbing
def mode_plumbing() -> None:
    load_env()
    adapter = ModelAdapter(ModelConfig.from_env())
    _m, _d, _i, _r, _z, scene_state, _draw = build_scene([0.45, 0.0], 101)
    proposal = adapter.propose_plan(scene_state, "Move the part to the target zone.")
    _raw, _plan, failed, error = layered_grade(proposal.raw_text, scene_state)
    print(json.dumps({
        "mode": "plumbing (not a sample call)",
        "raw_text": proposal.raw_text, "response_id": proposal.response_id,
        "model": proposal.model, "finish_reason": proposal.finish_reason,
        "latency_ms": proposal.latency_ms, "error": proposal.error,
        "error_type": proposal.error_type, "sdk_version": proposal.sdk_version,
        "first_failed_layer": failed, "layer_error": error}, indent=2))
    print("PLUMBING OK" if proposal.error is None and failed is None
          else "PLUMBING: see above (error or layer failure recorded)")


# ---------------------------------------------------------------- sample C
def mode_sample_c() -> None:
    scene = evaluator._reject_scene_state([0.45, 0.0])
    oob_scene = json.loads(json.dumps(scene))
    oob_scene["zones"]["target_zone"] = {"min": [0.9, 0.9], "max": [1.0, 1.0]}
    below_scene = json.loads(json.dumps(scene))
    below_scene["parts"]["part"]["position"] = [0.45, 0.0, -0.03]
    valid = {"part_id": "part", "target_zone": "target_zone",
             "approach_height_m": 0.15, "speed_scale": 0.5}
    cases = [
        ("C1", "unknown part (semantic)",
         json.dumps({**valid, "part_id": "gear_red"}), scene, "semantics"),
        ("C2", "known zone, out-of-workspace bounds (semantic)",
         json.dumps(valid), oob_scene, "semantics"),
        ("C3", "part below table, scene fixture (semantic)",
         json.dumps(valid), below_scene, "semantics"),
        ("C4a", "speed as string '0.5' (syntax)",
         '{"part_id": "part", "target_zone": "target_zone", '
         '"approach_height_m": 0.15, "speed_scale": "0.5"}', scene, "syntax"),
        ("C4b", "speed as boolean true (syntax)",
         '{"part_id": "part", "target_zone": "target_zone", '
         '"approach_height_m": 0.15, "speed_scale": true}', scene, "syntax"),
        ("C5a", "extra key (syntax)",
         json.dumps({**valid, "grip_force": 3}), scene, "syntax"),
        ("C5b", "duplicate keys (parse)",
         '{"part_id": "part", "part_id": "part", "target_zone": '
         '"target_zone", "approach_height_m": 0.15, "speed_scale": 0.5}',
         scene, "parse"),
        ("C5c", "NaN literal (parse)",
         '{"part_id": "part", "target_zone": "target_zone", '
         '"approach_height_m": NaN, "speed_scale": 0.5}', scene, "parse"),
        ("C5d", "malformed JSON (parse)", "not json {", scene, "parse"),
        ("C5e", "empty response (parse)", "", scene, "parse"),
        ("C6", "valid plan, positive control", json.dumps(valid), scene, None),
    ]
    audit = AuditLog(RESULTS / "audit_sample_c.jsonl")
    rows = []
    for cid, label, raw_text, case_scene, expect_fail in cases:
        calls = {"n": 0}

        def counting_executor(plan, _calls=calls):
            _calls["n"] += 1
            return {"counted_execution": True}

        raw, _plan, failed, error = layered_grade(raw_text, case_scene)
        guard_status = None
        if raw is not None:
            result = run_guarded(raw, case_scene, counting_executor,
                                 lambda plan: True, audit)
            guard_status = result.status
        expect_calls = 1 if cid == "C6" else 0
        passed = (failed == expect_fail and calls["n"] == expect_calls
                  and (guard_status == "executed" if cid == "C6"
                       else guard_status in ("validation_failed", None)))
        rows.append({"id": cid, "label": label, "expected_failed_layer": expect_fail,
                     "observed_failed_layer": failed, "error": error,
                     "guard_status": guard_status,
                     "executor_calls": calls["n"], "passed": bool(passed)})
        print(f"{cid}: layer={failed} guard={guard_status} "
              f"executor_calls={calls['n']} -> {'PASS' if passed else 'FAIL'}")
    payload = {"sample": "C", "all_passed": all(r["passed"] for r in rows),
               "cases": rows}
    _write("sample_c.json", payload)
    print("SAMPLE C:", "PASS" if payload["all_passed"] else "FAIL",
          f"({sum(r['passed'] for r in rows)}/{len(rows)})")


# ---------------------------------------------------------------- sample D
def mode_sample_d() -> None:
    scene = evaluator._reject_scene_state([0.45, 0.0])
    modes = ["valid", "malformed", "empty", "truncated", "slow", "error500"]
    expect = {"valid": None, "malformed": "parse", "empty": "parse",
              "truncated": "parse", "slow": "api_error", "error500": "api_error"}
    rows = []
    for i, mode in enumerate(modes):
        port = 8399 + i
        log_path = RESULTS / f"stub_log_{mode}.txt"
        if log_path.exists():
            log_path.unlink()
        env = {**os.environ, "STUB_MODE": mode, "STUB_PORT": str(port),
               "STUB_LOG": str(log_path)}
        proc = subprocess.Popen([sys.executable, str(ROOT / "gate4_stub.py")],
                                env=env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        try:
            deadline = time.time() + 10
            while True:
                try:
                    with socket.create_connection(("127.0.0.1", port), 0.25):
                        break
                except OSError:
                    if time.time() > deadline:
                        raise RuntimeError(f"stub did not start ({mode})")
                    time.sleep(0.1)
            adapter = ModelAdapter(ModelConfig(
                api_key="dummy-local", base_url=f"http://127.0.0.1:{port}/v1",
                timeout_s=3.0))
            proposal = adapter.propose_plan(scene, "Move the part to the target zone.")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        _raw, _plan, failed, _err = layered_grade(proposal.raw_text, scene)
        observed = "api_error" if proposal.error is not None else failed
        requests = (len(log_path.read_text().splitlines())
                    if log_path.exists() else 0)
        passed = observed == expect[mode] and requests == 1
        rows.append({"mode": mode, "expected": expect[mode], "observed": observed,
                     "error_type": proposal.error_type,
                     "finish_reason": proposal.finish_reason,
                     "requests_received": requests, "passed": bool(passed)})
        print(f"{mode}: observed={observed} requests={requests} "
              f"-> {'PASS' if passed else 'FAIL'}")
    payload = {"sample": "D", "test_timeout_s": 3.0,
               "note": "Production adapter/parser path vs local stub; the "
                       "3 s test timeout exercises the timeout path "
                       "without a 20 s wait. Request count proves the "
                       "SDK retry policy (max_retries=0).",
               "all_passed": all(r["passed"] for r in rows), "cases": rows}
    _write("sample_d.json", payload)
    print("SAMPLE D:", "PASS" if payload["all_passed"] else "FAIL",
          f"({sum(r['passed'] for r in rows)}/{len(rows)})")


# ---------------------------------------------------------------- causality
def mode_causality() -> None:
    base = {"part_id": "part", "target_zone": "target_zone",
            "approach_height_m": 0.15, "speed_scale": 0.5}

    def run_once(plan_dict):
        model, data, ids, rest_z, zone, _ss, _draw = build_scene([0.45, 0.0], 202)
        plan = validate_syntax(plan_dict)
        verdict = execute_and_score(model, data, ids, rest_z, zone, plan)
        return verdict, float(model.opt.timestep)

    b1a, timestep = run_once(base)
    b1b, _ = run_once(base)
    pose_delta_b1 = max(abs(a - b) for a, b in
                        zip(b1a["final_part_pos"][:2], b1b["final_part_pos"][:2]))
    dur_delta_b1 = abs(b1a["sim_duration_s"] - b1b["sim_duration_s"])
    b1_ok = (b1a["success"] and b1b["success"] and pose_delta_b1 <= 1e-6
             and dur_delta_b1 <= timestep)
    slow = execute_and_score(*build_scene([0.45, 0.0], 202)[:5],
                             validate_syntax({**base, "speed_scale": 0.3}))
    fast = execute_and_score(*build_scene([0.45, 0.0], 202)[:5],
                             validate_syntax({**base, "speed_scale": 0.9}))
    pose_delta_b2 = max(abs(a - b) for a, b in
                        zip(slow["final_part_pos"][:2], fast["final_part_pos"][:2]))
    dur_delta_b2 = abs(slow["sim_duration_s"] - fast["sim_duration_s"])
    b2_ok = (slow["success"] and fast["success"] and dur_delta_b2 >= 0.1)
    b3_calls = {"n": 0}

    def _b3_executor(plan, _calls=b3_calls):
        _calls["n"] += 1
        return {"counted_execution": True}

    _b3_scene = evaluator._reject_scene_state([0.45, 0.0])
    _b3_raw = {"part_id": "gear_red", "target_zone": "target_zone",
               "approach_height_m": 0.15, "speed_scale": 0.5}
    _b3 = run_guarded(_b3_raw, _b3_scene, _b3_executor, lambda plan: True,
                      AuditLog(RESULTS / "audit_causality.jsonl"))
    b3_ok = _b3.status == "validation_failed" and b3_calls["n"] == 0
    payload = {"sample": "B (offline rehearsal, derived controls)",
               "b1_identical_plan_twice": {
                   "pose_delta_m": pose_delta_b1, "duration_delta_s": dur_delta_b1,
                   "timestep_s": timestep, "passed": bool(b1_ok)},
               "b2_speed_field_effect": {
                   "slow_duration_s": slow["sim_duration_s"],
                   "fast_duration_s": fast["sim_duration_s"],
                   "duration_delta_s": dur_delta_b2,
                   "pose_delta_m": pose_delta_b2,
                   "pose_note": "informational only - the ratified B2 "
                                "criterion is duration + success",
                   "passed": bool(b2_ok)},
               "b3_rejected_plan_control": {
                   "guard_status": _b3.status,
                   "executor_calls": b3_calls["n"], "passed": bool(b3_ok)},
               "all_passed": bool(b1_ok and b2_ok and b3_ok)}
    _write("causality.json", payload)
    print(json.dumps(payload, indent=2))
    print("CAUSALITY:", "PASS" if payload["all_passed"] else "FAIL")


# ---------------------------------------------------------------- freeze
def _freeze_payload() -> dict:
    git_head = None
    try:
        git_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                  capture_output=True, text=True,
                                  timeout=10).stdout.strip() or None
    except Exception:
        pass
    return {"frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "git_head": git_head,
            "system_prompt_sha256": hashlib.sha256(
                SYSTEM_PROMPT.encode()).hexdigest(),
            "files": {rel: _sha(ROOT / rel) for rel in FREEZE_FILES}}


def mode_freeze() -> None:
    payload = _freeze_payload()
    _write("freeze.json", payload)
    print(json.dumps(payload, indent=2))
    print("FROZEN. Sample A will refuse to run if any hashed file changes.")


def _check_freeze() -> None:
    freeze_path = RESULTS / "freeze.json"
    if not freeze_path.exists():
        raise SystemExit("REFUSED: no freeze.json - run --mode freeze first")
    frozen = json.loads(freeze_path.read_text())
    current = _freeze_payload()
    if frozen["files"] != current["files"] or \
            frozen["system_prompt_sha256"] != current["system_prompt_sha256"]:
        raise SystemExit("REFUSED: files changed since freeze - "
                         "re-run the preflight and freeze again")


# ---------------------------------------------------------------- sample A
def _approval_display(case, plan, scene_state) -> bool:
    part_pos = scene_state["parts"][plan.part_id]["position"]
    zone = scene_state["zones"][plan.target_zone]
    center = [(zone["min"][0] + zone["max"][0]) / 2,
              (zone["min"][1] + zone["max"][1]) / 2]
    print()
    print(f"--- APPROVAL REQUIRED: {case['id']} ---")
    print(f"Operator request : {case['task']}")
    print(f"Proposed object  : {plan.part_id} at "
          f"[{part_pos[0]:.3f}, {part_pos[1]:.3f}, {part_pos[2]:.3f}] "
          f"(actual scene identity)")
    print(f"Destination      : {plan.target_zone} x {zone['min'][0]:.2f}.."
          f"{zone['max'][0]:.2f}, y {zone['min'][1]:.2f}..{zone['max'][1]:.2f} "
          f"(center [{center[0]:.2f}, {center[1]:.2f}])")
    print(f"Parameters       : approach_height_m {plan.approach_height_m}, "
          f"speed_scale {plan.speed_scale}")
    print("Checklist        : correct object? correct destination? "
          "reasonable parameters?")
    answer = input("Approve execution? [y/N] ").strip().lower()
    return answer == "y"


def _run_live_case(adapter, audit, case, in_sample: bool,
                   allow_execution: bool = True) -> dict:
    model, data, ids, rest_z, zone, scene_state, draw = build_scene(
        case["part_start"], case["seed"], case.get("target_zone_pos"))
    proposal = adapter.propose_plan(scene_state, case["task"])
    raw, plan, failed, error = layered_grade(proposal.raw_text, scene_state)
    rec = {"id": case["id"], "kind": case["kind"], "in_sample": in_sample,
           "task": case["task"], "part_start": case["part_start"],
           "seed": case["seed"],
           "draw": {"part_position": draw["part_position"],
                    "yaw_deg": draw["yaw_deg"],
                    "friction_scale": draw["friction_scale"]},
           "scene_state": scene_state,
           "proposal": {"raw_text": proposal.raw_text,
                        "response_id": proposal.response_id,
                        "model": proposal.model,
                        "finish_reason": proposal.finish_reason,
                        "latency_ms": proposal.latency_ms,
                        "error": proposal.error,
                        "error_type": proposal.error_type,
                        "sdk_version": proposal.sdk_version,
                        "configured_model": proposal.configured_model,
                        "base_url": proposal.base_url},
           "layers": {"parse_ok": failed not in ("parse", "api_error"),
                      "syntax_ok": failed not in ("parse", "syntax", "api_error"),
                      "semantics_ok": failed is None,
                      "first_failed_layer": failed, "error": error},
           "plan": (plan.__dict__ if plan is not None else None),
           "checks": grade_checks(plan if failed is None else None,
                                  case, scene_state),
           "guard_status": None, "execution": None}
    if failed is None and plan is not None and allow_execution:
        decision = {}

        def approve(p, _case=case, _plan=plan, _ss=scene_state, _d=decision):
            _d["approved"] = _approval_display(_case, _plan, _ss)
            return _d["approved"]

        def executor(p, _m=model, _d=data, _i=ids, _r=rest_z, _z=zone):
            return execute_and_score(_m, _d, _i, _r, _z, p)

        def scene_provider(_m=model, _d=data, _i=ids):
            return evaluator._live_scene_state(_m, _d, _i)

        result = run_guarded(raw, scene_state, executor, approve, audit,
                             scene_provider=scene_provider)
        rec["guard_status"] = result.status
        rec["human_approved"] = decision.get("approved")
        if result.status == "executed":
            rec["execution"] = result.outcome
        if case["kind"] == "trap":
            rec["task_correctness"] = "failure_substitution"
            rec["note"] = ("Model substituted a real object for the "
                           "nonexistent gear; recorded as a task-correctness "
                           "failure regardless of the approval outcome "
                           "(design lock D4).")
    elif case["kind"] == "trap":
        rec["task_correctness"] = ("contained_refusal" if failed == "parse"
                                   else f"stopped_at_{failed}")
        if failed == "semantics":
            rec["validator_catch_observed"] = True
    return rec


def mode_sample_a() -> None:
    _check_freeze()
    load_env()
    adapter = ModelAdapter(ModelConfig.from_env())
    manifest = json.loads(MANIFEST.read_text())
    audit = AuditLog(RESULTS / "audit.jsonl")
    records = []
    for case in manifest["cases"]:
        print(f"\n=== {case['id']} ({case['kind']}): {case['task']}")
        rec = _run_live_case(adapter, audit, case, in_sample=True)
        records.append(rec)
        print(f"layers: {rec['layers']} | guard: {rec['guard_status']}")
    supp = manifest["supplemental"]
    print(f"\n=== {supp['id']} (supplemental): {supp['task']}")
    s1 = _run_live_case(adapter, audit, {**supp, "checks": []},
                        in_sample=False, allow_execution=False)
    s1["note"] = ("S1 supplemental observation (design lock v2): response "
                  "layers recorded; never sent to the guard or executed; "
                  "outside the conformance denominator; inside the call "
                  "inventory and budget.")
    records.append(s1)

    # case-07 / case-08 replay under matched conditions (ratified rule)
    replay = {"status": "not_evaluated"}
    by_id = {r["id"]: r for r in records}
    r7, r8 = by_id.get("case-07"), by_id.get("case-08")
    if r7 and r8 and r7["plan"] and r8["plan"]:
        if r7["plan"] == r8["plan"]:
            replay = {"status": "identical_plans",
                      "note": "Both wordings produced the same plan; "
                              "nothing differs to replay."}
        else:
            outs = {}
            for rid, r in (("case-07", r7), ("case-08", r8)):
                m, d, i, rz, z, _ss, _dr = build_scene([0.45, 0.0], 101)
                plan = validate_syntax(r["plan"])
                outs[rid] = execute_and_score(m, d, i, rz, z, plan)
            replay = {"status": "replayed", "case-07": outs["case-07"],
                      "case-08": outs["case-08"],
                      "duration_delta_s": abs(outs["case-07"]["sim_duration_s"]
                                              - outs["case-08"]["sim_duration_s"])}
    graded = [r for r in records if r["in_sample"]]
    conform = sum(1 for r in graded if r["layers"]["syntax_ok"])
    latencies = [r["proposal"]["latency_ms"] for r in graded
                 if r["proposal"]["latency_ms"] is not None]
    executed = [r for r in graded if r["guard_status"] == "executed"]
    physics_ok = sum(1 for r in executed
                     if r["execution"] and r["execution"].get("success"))
    summary = {"sample": "A", "conformance_parse_syntax": f"{conform}/10",
               "conformance_bar": ">=9/10",
               "conformance_pass": conform >= 9,
               "latency_median_ms": (statistics.median(latencies)
                                     if latencies else None),
               "latency_max_ms": (max(latencies) if latencies else None),
               "latency_soft_target_s": 15,
               "executed": len(executed), "physics_success": physics_ok,
               "trap": by_id["case-09"]["layers"]["first_failed_layer"]
               or by_id["case-09"]["guard_status"],
               "replay_07_08": replay["status"],
               "s1_latency_ms": s1["proposal"]["latency_ms"]}
    _write("sample_a.json", {"summary": summary, "records": records,
                             "replay_07_08": replay})
    med = summary["latency_median_ms"]
    mx = summary["latency_max_ms"]
    lines = ["Gate 4 - Sample A summary", "",
             f"Conformance (parse+syntax): {conform}/10 "
             f"({'PASS' if conform >= 9 else 'FAIL'} vs >=9/10 bar)",
             f"Latency: median {med:.0f} ms, max {mx:.0f} ms "
             f"(soft target 15 s)" if med is not None else
             "Latency: no latencies recorded (all calls errored)",
             f"Executed: {len(executed)} | physics success: {physics_ok}",
             f"Trap (case-09) stopped at: {summary['trap']}",
             f"case-07/08 replay: {replay['status']}",
             f"S1 latency (separate): {s1['proposal']['latency_ms']} ms"]
    (RESULTS / "sample_a_summary.txt").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Gate 4 runner (design lock v2)")
    parser.add_argument("--mode", required=True,
                        choices=["plumbing", "sample-c", "sample-d",
                                 "causality", "freeze", "sample-a"])
    args = parser.parse_args()
    {"plumbing": mode_plumbing, "sample-c": mode_sample_c,
     "sample-d": mode_sample_d, "causality": mode_causality,
     "freeze": mode_freeze, "sample-a": mode_sample_a}[args.mode]()


if __name__ == "__main__":
    main()

