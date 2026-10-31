"""Gate 4 repair evidence - Astra review #6 remediation (Oct 30, 2026).

LABELED REPAIRS. These runs do NOT change the frozen Gate 4 verdict
(NOT PASSED) and do not modify Gate 4's original result files. They
produce the corrected-path evidence the review required:

  causality-guarded    The B1/B2/B3 causality controls re-run with
                       EVERY execution through the shared guard
                       (run_guarded) - the original run called the
                       executor directly for B1/B2. Approval here is
                       a labeled OFFLINE FIXTURE (programmatic true):
                       causality is an offline property of the
                       executor, and the record says so.
  stub-orchestration   Sample D's six stub modes re-run through the
                       full orchestration - adapter, raw-text parser,
                       AND the guard with a counting executor - the
                       original Sample D never invoked the guard.
                       Pre-guard failures (parse / adapter errors)
                       get explicit terminal audit records from this
                       runner, so every mode ends audited.

Outputs: results/gate4/causality_guarded.json,
         results/gate4/sample_d_orchestration.json,
         results/gate4/audit_repairs.jsonl (this file's own audit).
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import gate4_run as g4  # noqa: E402  (frozen Gate 4 code, reused as-is)

from simforge import evaluator  # noqa: E402
from simforge.guard import AuditLog, run_guarded  # noqa: E402
from simforge.model_adapter import ModelAdapter, ModelConfig  # noqa: E402
from simforge.plan_schema import parse_plan  # noqa: E402

RESULTS = ROOT / "results" / "gate4"
REPAIR_AUDIT = RESULTS / "audit_repairs.jsonl"
CENTER = [0.45, 0.0]


def _guarded_execution(audit, run_id, part_xy, seed, plan_dict,
                       target_pos=None, approve=None):
    """One execution through the guard. Returns (guard_result, calls,
    verdict_or_None)."""
    model, data, ids, rest_z, zone, _ss, _draw = g4.build_scene(
        part_xy, seed, target_pos)
    scene_state = evaluator._live_scene_state(model, data, ids)
    calls = {"n": 0}

    def executor(plan):
        calls["n"] += 1
        return g4.execute_and_score(model, data, ids, rest_z, zone, plan)

    def scene_provider():
        return evaluator._live_scene_state(model, data, ids)

    result = run_guarded(plan_dict, scene_state, executor,
                         approve or (lambda plan: True), audit,
                         scene_provider=scene_provider, run_id=run_id)
    return result, calls["n"]


def mode_causality_guarded() -> None:
    audit = AuditLog(REPAIR_AUDIT)
    base = {"part_id": "part", "target_zone": "target_zone",
            "approach_height_m": 0.15, "speed_scale": 0.5}
    # B1: determinism, both runs guarded.
    r1, c1 = _guarded_execution(audit, "repair:B1a", CENTER, 101, dict(base))
    r2, c2 = _guarded_execution(audit, "repair:B1b", CENTER, 101, dict(base))
    b1_ok = (c1 == c2 == 1 and r1.status == r2.status == "executed")
    detail = {}
    if b1_ok:
        dpos = max(abs(a - b) for a, b in zip(
            r1.outcome["final_part_pos"], r2.outcome["final_part_pos"]))
        ddur = abs(r1.outcome["sim_duration_s"] - r2.outcome["sim_duration_s"])
        detail = {"max_final_xy_delta_m": dpos, "duration_delta_s": ddur}
        b1_ok = dpos <= 1e-6 and ddur <= 1e-6
    # B2: isolated speed causality, both runs guarded.
    slow = dict(base, speed_scale=0.3)
    fast = dict(base, speed_scale=0.9)
    rs, cs = _guarded_execution(audit, "repair:B2-slow", CENTER, 101, slow)
    rf, cf = _guarded_execution(audit, "repair:B2-fast", CENTER, 101, fast)
    b2_ok = (cs == cf == 1 and rs.status == rf.status == "executed"
             and rs.outcome["success"] and rf.outcome["success"])
    delta = None
    if b2_ok:
        delta = rs.outcome["sim_duration_s"] - rf.outcome["sim_duration_s"]
        b2_ok = delta > 1.0
    # B3: invalid plan, guard must stop it (as before, now recorded
    # alongside the guarded B1/B2 in one inventory).
    bad = dict(base, approach_height_m=0.01)
    r3, c3 = _guarded_execution(audit, "repair:B3", CENTER, 101, bad)
    b3_ok = r3.status == "validation_failed" and c3 == 0
    payload = {
        "run": "gate4-repair-causality-guarded",
        "note": "Remediation evidence (Astra review #6). Executions "
                "through run_guarded; approval is a labeled offline "
                "fixture. Original causality file retained; Gate 4 "
                "verdict unchanged (NOT PASSED).",
        "B1": {"guarded": True, "executor_calls": [c1, c2],
               "statuses": [r1.status, r2.status], **detail,
               "passed": bool(b1_ok)},
        "B2": {"guarded": True, "executor_calls": [cs, cf],
               "duration_delta_s": delta, "passed": bool(b2_ok)},
        "B3": {"guarded": True, "status": r3.status,
               "executor_calls": c3, "passed": bool(b3_ok)},
        "passed": bool(b1_ok and b2_ok and b3_ok)}
    out = RESULTS / "causality_guarded.json"
    out.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))
    print("GUARDED CAUSALITY:", "PASS" if payload["passed"] else "FAIL")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run_stub(mode: str, port: int, log_path: Path):
    env = dict(os.environ, STUB_MODE=mode, STUB_LOG=str(log_path),
               STUB_PORT=str(port))
    proc = subprocess.Popen([sys.executable, str(ROOT / "gate4_stub.py")],
                            env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return proc
        except OSError:
            if proc.poll() is not None:
                raise RuntimeError(f"stub exited early in mode {mode}")
            time.sleep(0.1)
    proc.terminate()
    raise RuntimeError(f"stub did not start in mode {mode}")


def mode_stub_orchestration() -> None:
    audit = AuditLog(REPAIR_AUDIT)
    scene = evaluator._reject_scene_state(CENTER)
    modes = ["valid", "malformed", "empty", "truncated", "slow", "error500"]
    rows = []
    for mode in modes:
        run_id = f"repair:D-{mode}"
        port = _free_port()
        log_path = RESULTS / f"stub_requests_{mode}.log"
        if log_path.exists():
            log_path.unlink()
        proc = _run_stub(mode, port, log_path)
        calls = {"n": 0}
        outcome, guard_status = None, None
        try:
            adapter = ModelAdapter(ModelConfig(
                api_key="stub", base_url=f"http://127.0.0.1:{port}/v1",
                timeout_s=3.0))
            proposal = adapter.propose_plan(
                scene, "Move the part to the target zone.")
            if proposal.error is not None:
                outcome = ("adapter_timeout"
                           if "timeout" in (proposal.error_type or "").lower()
                           else "adapter_error")
                audit.write(outcome, run_id=run_id,
                            error=proposal.error,
                            error_type=proposal.error_type)
            if outcome is None:
                try:
                    plan = parse_plan(proposal.raw_text)
                except BaseException as exc:
                    outcome = "parse_failed"
                    audit.write("parse_failed", run_id=run_id,
                                error=f"{type(exc).__name__}: {exc}")
                else:
                    def counting_executor(plan, _c=calls):
                        _c["n"] += 1
                        return {"counted": True}

                    result = run_guarded({"part_id": plan.part_id, "target_zone": plan.target_zone, "approach_height_m": plan.approach_height_m, "speed_scale": plan.speed_scale}, scene,
                                         counting_executor,
                                         lambda plan: True, audit,
                                         run_id=run_id)
                    guard_status = result.status
                    outcome = ("guard_executed" if result.status == "executed"
                               else f"guard_{result.status}")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        requests = (len(log_path.read_text().splitlines())
                    if log_path.exists() else 0)
        expected = {"valid": "guard_executed",
                    "malformed": "parse_failed", "empty": "parse_failed",
                    "truncated": "parse_failed", "slow": "adapter_timeout",
                    "error500": "adapter_error"}[mode]
        rows.append({"mode": mode, "outcome": outcome,
                     "guard_status": guard_status, "expected": expected,
                     "requests": requests,
                     "executor_calls": calls["n"],
                     "passed": outcome == expected and requests == 1
                     and calls["n"] == (1 if mode == "valid" else 0)})
        print(f"{mode}: outcome={outcome} guard={guard_status} "
              f"requests={requests} executor_calls={calls['n']} -> "
              f"{'PASS' if rows[-1]['passed'] else 'FAIL'}")
    payload = {"run": "gate4-repair-stub-orchestration",
               "note": "Remediation evidence (Astra review #6): Sample D "
                       "modes driven through adapter + parser + guard "
                       "with a counting executor. Original Sample D "
                       "records retained; Gate 4 verdict unchanged "
                       "(NOT PASSED). Test timeout 3 s (labeled).",
               "cases": rows,
               "passed": all(r["passed"] for r in rows)}
    (RESULTS / "sample_d_orchestration.json").write_text(
        json.dumps(payload, indent=2))
    print("STUB ORCHESTRATION:", "PASS" if payload["passed"] else "FAIL")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gate 4 repair evidence")
    parser.add_argument("--mode", required=True,
                        choices=["causality-guarded", "stub-orchestration"])
    args = parser.parse_args()
    if args.mode == "causality-guarded":
        mode_causality_guarded()
    else:
        mode_stub_orchestration()


if __name__ == "__main__":
    main()
