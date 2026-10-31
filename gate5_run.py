"""Gate 5 runner + audit verifier - design lock RATIFIED Oct 30, 2026.

Modes:
  freeze           Record the candidate hashes (suite manifest,
                   probes manifest, Gate 3 scenarios file, guard,
                   schema, evaluator, this runner) + git HEAD into
                   results/gate5/freeze.json. The freeze record does
                   not hash itself. After freezing, changes to code,
                   scenario inputs, or grading rules require a new
                   candidate; evidence and documents may be added.
  suite            The headless acceptance run. Every case is
                   pre-registered from the frozen manifest; its run
                   record is persisted BEFORE setup, so a crash
                   cannot vanish from the denominator. Human cases
                   prompt the founder at the console. On an
                   interrupted status the runner halts deliberately
                   and exits non-success. On a harness defect it
                   stops (protocol: preserve, new candidate, full
                   rerun with new attempt IDs). An honest physics
                   failure is recorded and the suite CONTINUES.
  probes           The bounded fault-probe segment (own inventory,
                   gate5_probes.json). The interruption probe is
                   LAST: its expected outcome is the stop itself.
  verify           The independent audit verifier: reads the frozen
                   manifest, the run records, and the audit JSONL;
                   reports SUITE COMPLETION and AUDIT COMPLETENESS
                   as distinct verdicts. Shares no code with the
                   guard.
  verify-selftest  The verifier's negative controls, run on
                   synthetic copies BEFORE the acceptance run: an
                   intact control must pass; five planted defects
                   (deleted terminal, duplicated terminal, orphan
                   run_id, malformed line, whole case removed from
                   records AND audit) must each be caught with the
                   correct defect report.

Sim imports are lazy so verify / verify-selftest / freeze run
without the simulator stack.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

RESULTS = ROOT / "results" / "gate5"
SUITE_MANIFEST = ROOT / "gate5_suite.json"
PROBES_MANIFEST = ROOT / "gate5_probes.json"
FREEZE_FILES = ["gate5_suite.json", "gate5_probes.json",
                "scenarios/example_scenarios.json",
                "src/simforge/guard.py", "src/simforge/plan_schema.py",
                "src/simforge/evaluator.py", "gate5_run.py"]
TERMINAL_EVENTS = {"executed", "rejected", "validation_failed",
                   "execution_failed", "approval_invalidated",
                   "approval_error", "approval_interrupted",
                   "execution_interrupted", "suite_terminal"}
INTERRUPTED = {"approval_interrupted", "execution_interrupted"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _git_head():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except Exception:
        return None


# ------------------------------------------------------------------ freeze
def mode_freeze() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    payload = {"frozen_at": _now(), "candidate_head": _git_head(),
               "files": {rel: _sha(ROOT / rel) for rel in FREEZE_FILES}}
    (RESULTS / "freeze.json").write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))
    print("FROZEN. Suite/probes refuse to run against a changed candidate.")


def _check_freeze() -> dict:
    freeze_path = RESULTS / "freeze.json"
    if not freeze_path.exists():
        raise SystemExit("REFUSED: no freeze.json - commit candidate C, "
                         "then run --mode freeze")
    frozen = json.loads(freeze_path.read_text())
    current = {rel: _sha(ROOT / rel) for rel in FREEZE_FILES}
    if frozen["files"] != current:
        raise SystemExit("REFUSED: candidate changed since freeze - "
                         "a new candidate requires a new freeze")
    return frozen


# ------------------------------------------------------------------ verify
def verify(manifest_ids, records, audit_events, malformed_lines=0):
    """Pure verifier core. Returns a report dict. Two verdicts:
    completion (terminals / manifest total) and completeness
    (exactly-one-matched-terminal / started attempts)."""
    defects = []

    def defect(kind, detail):
        defects.append({"kind": kind, "detail": detail})

    if malformed_lines:
        defect("malformed_audit_line", f"{malformed_lines} unparseable line(s)")
    records_by_id = {}
    for rec in records:
        rid = rec.get("run_id")
        if rid in records_by_id:
            defect("duplicate_run_record", rid)
        records_by_id[rid] = rec
    # Denominator comes from the MANIFEST (manifest_ids), never from
    # the returned records alone - a case removed from both stores
    # still counts against completion (see the missing_run_record
    # check below and the verify-selftest denominator-shrink case).
    terminals = {}
    seen_events = []
    for ev in audit_events:
        rid = ev.get("run_id")
        if rid is not None:
            seen_events.append(rid)
        if ev.get("event") in TERMINAL_EVENTS and rid is not None:
            terminals.setdefault(rid, []).append(ev)
    for rid, evs in terminals.items():
        if len(evs) > 1:
            defect("duplicate_terminal", rid)
    known_rids = set(records_by_id)
    for rid in {e.get("run_id") for e in audit_events if e.get("run_id")}:
        if rid not in known_rids:
            defect("orphan_audit_run", rid)
    started = [r for r in records if r.get("started_ts")]
    matched = 0
    completed = 0
    for rec in records:
        rid = rec.get("run_id")
        term = terminals.get(rid, [])
        status = rec.get("guard_status")
        if status in TERMINAL_EVENTS or status == "harness_error":
            completed += 1
        if len(term) != 1:
            continue
        ev = term[0]
        expected_event = "suite_terminal" if status == "harness_error" else status
        if ev.get("event") != expected_event:
            defect("outcome_mismatch",
                   f"{rid}: record {status} vs audit {ev.get('event')}")
            continue
        if status == "validation_failed" and not (
                rec.get("decision") == "not_requested"
                and rec.get("outcome") == "not_executed"):
            defect("outcome_mismatch",
                   f"{rid}: validation failure must carry decision "
                   f"not_requested / outcome not_executed")
            continue
        matched += 1
    for cid in manifest_ids:
        if not any(r.get("case_id") == cid for r in records):
            defect("missing_run_record", cid)
    completion = (completed / len(manifest_ids)) if manifest_ids else 0.0
    completeness = (matched / len(started)) if started else 0.0
    return {"manifest_total": len(manifest_ids),
            "records": len(records), "started": len(started),
            "completed": completed, "matched": matched,
            "suite_completion": completion,
            "audit_completeness": completeness,
            "defects": defects,
            "passed": bool(manifest_ids) and completion == 1.0
            and completeness == 1.0 and not defects}


def _load_jsonl(path):
    events, malformed = [], 0
    if not path.exists():
        return events, malformed
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            malformed += 1
    return events, malformed


def mode_verify(attempt: str) -> None:
    manifest = json.loads(SUITE_MANIFEST.read_text())
    manifest_ids = [c["id"] for c in manifest["cases"]]
    records, _ = _load_jsonl(RESULTS / f"records_{attempt}.jsonl")
    events, malformed = _load_jsonl(RESULTS / "audit.jsonl")
    # Run-record files also carry preregistered placeholders and
    # rejection-reason annotations (lines WITH an "event" key); the
    # verifier sees terminal run records only (no "event" key).
    terminal_records = [r for r in records
                        if r.get("attempt") == attempt
                        and r.get("event") is None]
    report = verify(manifest_ids, terminal_records, events, malformed)
    report["attempt"] = attempt
    (RESULTS / f"verify_{attempt}.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print("VERIFY:", "PASS" if report["passed"] else "FAIL")


def mode_verify_selftest() -> None:
    base_records = [
        {"run_id": "T:C1", "attempt": "T", "case_id": "C1",
         "started_ts": "2026-01-01T00:00:00+0000", "guard_status": "executed",
         "decision": "approved", "outcome": "executed_success"},
        {"run_id": "T:C2", "attempt": "T", "case_id": "C2",
         "started_ts": "2026-01-01T00:00:01+0000",
         "guard_status": "validation_failed", "decision": "not_requested",
         "outcome": "not_executed"},
        {"run_id": "T:C3", "attempt": "T", "case_id": "C3",
         "started_ts": "2026-01-01T00:00:02+0000", "guard_status": "rejected",
         "decision": "rejected", "outcome": "not_executed"},
    ]
    base_events = [
        {"run_id": "T:C1", "event": "plan_received", "ts": "2026-01-01T00:00:00+0000"},
        {"run_id": "T:C1", "event": "executed", "ts": "2026-01-01T00:00:03+0000"},
        {"run_id": "T:C2", "event": "plan_received", "ts": "2026-01-01T00:00:01+0000"},
        {"run_id": "T:C2", "event": "validation_failed", "ts": "2026-01-01T00:00:01+0000"},
        {"run_id": "T:C3", "event": "plan_received", "ts": "2026-01-01T00:00:02+0000"},
        {"run_id": "T:C3", "event": "rejected", "ts": "2026-01-01T00:00:02+0000"},
    ]
    ids = ["C1", "C2", "C3"]
    results = {}

    def run(name, records, events, malformed=0):
        rep = verify(ids, records, events, malformed)
        results[name] = rep
        return rep

    intact = run("intact", base_records, base_events)
    d1 = run("deleted_terminal", base_records,
             [e for e in base_events if not (e["run_id"] == "T:C1"
                                             and e["event"] == "executed")])
    d2 = run("duplicated_terminal", base_records,
             base_events + [{"run_id": "T:C3", "event": "rejected",
                             "ts": "2026-01-01T00:00:02+0000"}])
    d3 = run("orphan_run", base_records,
             base_events + [{"run_id": "T:C9", "event": "executed",
                             "ts": "2026-01-01T00:00:04+0000"}])
    d4 = run("malformed_line", base_records, base_events, malformed=1)
    d5 = run("case_removed_everywhere",
             [r for r in base_records if r["case_id"] != "C2"],
             [e for e in base_events if e["run_id"] != "T:C2"])
    checks = {
        "intact_passes": intact["passed"],
        "deleted_terminal_caught": (not d1["passed"]
                                    and d1["audit_completeness"] < 1.0),
        "duplicated_terminal_caught": any(
            x["kind"] == "duplicate_terminal" for x in d2["defects"]),
        "orphan_caught": any(x["kind"] == "orphan_audit_run"
                             for x in d3["defects"]),
        "malformed_caught": any(x["kind"] == "malformed_audit_line"
                                for x in d4["defects"]),
        "case_removal_caught": any(x["kind"] == "missing_run_record"
                                   for x in d5["defects"]),
    }
    payload = {"selftest": checks, "all_passed": all(checks.values()),
               "reports": {k: v for k, v in results.items()}}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "verify_selftest.json").write_text(json.dumps(payload, indent=2))
    print(json.dumps(checks, indent=2))
    print("VERIFY SELFTEST:", "PASS" if payload["all_passed"] else "FAIL")


# ------------------------------------------------------------- suite core
def _sim_imports():
    from simforge import evaluator, grasp
    from simforge.guard import AuditLog, run_guarded
    from simforge.scoring import evaluate_attempt
    return evaluator, grasp, AuditLog, run_guarded, evaluate_attempt


def _execute_and_score(evaluator, grasp, evaluate_attempt,
                       model, data, ids, rest_z, zone, plan, cell):
    t0 = float(data.time)
    samples = grasp.execute_plan(model, data, plan, ids, log=lambda *a: None)
    verdict = dict(evaluate_attempt(samples, rest_z, zone))
    verdict["final_part_pos"] = [float(v) for v in data.xpos[ids.part_body]]
    verdict["sim_duration_s"] = float(data.time) - t0
    cell["motion_steps"] = len(samples)
    cell["sim_time_advanced_s"] = float(data.time) - t0
    return verdict


def _approval_display(run_id, case, plan_dict, scene_state, source_note):
    part_pos = scene_state["parts"][plan_dict["part_id"]]["position"] \
        if plan_dict["part_id"] in scene_state["parts"] else None
    zone = scene_state["zones"].get(plan_dict["target_zone"])
    print()
    print(f"--- APPROVAL REQUIRED: {run_id} ---")
    print(f"Case             : {case['id']} ({source_note})")
    if case.get("request_text"):
        print(f"Operator request : {case['request_text']}")
    print(f"Proposed plan    : {plan_dict}")
    if part_pos is not None:
        print(f"Scene identity   : {plan_dict['part_id']} at "
              f"[{part_pos[0]:.3f}, {part_pos[1]:.3f}, {part_pos[2]:.3f}]")
    if zone is not None:
        print(f"Destination      : {plan_dict['target_zone']} x "
              f"{zone['min'][0]:.2f}..{zone['max'][0]:.2f}, y "
              f"{zone['min'][1]:.2f}..{zone['max'][1]:.2f}")
    print("Checklist        : correct object? correct destination? "
          "reasonable parameters?")
    return input("Approve execution? [y/N] ").strip().lower() == "y"


def _append_record(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def _run_one(attempt, case, scenarios_by_index, audit, imports):
    """Execute one pre-registered case. Returns (record, halt_reason).
    halt_reason: None | 'interrupted' | 'harness'."""
    evaluator, grasp, AuditLog, run_guarded, evaluate_attempt = imports
    run_id = f"{attempt}:{case['id']}"
    rec = {"run_id": run_id, "attempt": attempt, "case_id": case["id"],
           "source": case["source"], "expectation": case.get("expectation"),
           "expected_path": case.get("expected_path"),
           "started_ts": _now(), "guard_status": None, "decision": None,
           "outcome": None, "executor_calls": 0, "motion_steps": 0,
           "sim_time_advanced_s": 0.0, "physics": None}
    records_path = RESULTS / f"records_{attempt}.jsonl"
    _append_record(records_path, {**rec, "event": "preregistered"})
    try:
        if case["source"] == "gate3_suite":
            scenario = scenarios_by_index[case["scenario_index"]]
            rec["scenario_name"] = scenario["name"]
            plan_dict = scenario["plan"]
            draw = evaluator.perturb(scenario)
            model, data, ids, rest_z, zone = evaluator._setup_scene(draw)
            scene_state = evaluator._live_scene_state(model, data, ids)
        elif case["id"] == "G5-GHOST":
            plan_dict = case["plan"]
            model = data = ids = None
            scene_state = evaluator._reject_scene_state(case["part_start"])
        else:
            plan_dict = case["plan"]
            scenario = {"name": case["id"], "seed": case["seed"],
                        "part_position": list(case["part_start"]),
                        "expect": "success", "plan": {}}
            if case.get("target_zone_pos") is not None:
                scenario["target_zone_pos"] = list(case["target_zone_pos"])
            draw = evaluator.perturb(scenario)
            model, data, ids, rest_z, zone = evaluator._setup_scene(draw)
            scene_state = evaluator._live_scene_state(model, data, ids)
    except BaseException as exc:  # setup failure = harness defect
        rec.update({"guard_status": "harness_error",
                    "outcome": "harness_error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "finished_ts": _now()})
        audit.write("suite_terminal", run_id=run_id,
                    outcome="harness_error", error=rec["error"])
        _append_record(records_path, rec)
        return rec, "harness"

    cell = {"calls": 0, "motion_steps": 0, "sim_time_advanced_s": 0.0}

    def executor(plan, _cell=cell):
        _cell["calls"] += 1
        if model is None:
            return {"counted_only": True}
        return _execute_and_score(evaluator, grasp, evaluate_attempt,
                                  model, data, ids, rest_z, zone, plan, _cell)

    def approve(plan, _case=case, _pid=plan_dict, _ss=scene_state):
        return _approval_display(run_id, _case, _pid, _ss,
                                 _case["source"])

    def scene_provider(_m=model, _d=data, _i=ids):
        return evaluator._live_scene_state(_m, _d, _i)

    result = run_guarded(plan_dict, scene_state, executor, approve, audit,
                         scene_provider=scene_provider if model is not None
                         else None,
                         run_id=run_id)
    rec["guard_status"] = result.status
    rec["executor_calls"] = cell["calls"]
    rec["motion_steps"] = cell["motion_steps"]
    rec["sim_time_advanced_s"] = cell["sim_time_advanced_s"]
    if result.status == "executed":
        rec["decision"] = "approved"
        rec["physics"] = result.outcome
        rec["outcome"] = ("executed_success"
                          if result.outcome and result.outcome.get("success")
                          else "executed_failure")
    elif result.status == "rejected":
        rec["decision"] = "rejected"
        rec["outcome"] = "not_executed"
    elif result.status == "validation_failed":
        rec["decision"] = "not_requested"
        rec["outcome"] = "not_executed"
    else:
        rec["decision"] = result.status
        rec["outcome"] = "not_executed"
    rec["finished_ts"] = _now()
    _append_record(records_path, rec)
    if result.status == "rejected":
        # Terminal outcome is persisted BEFORE the optional reason.
        reason = input("Rejection reason (optional, Enter to skip): ").strip()
        if reason:
            rec["rejection_reason"] = reason
            _append_record(records_path,
                           {"run_id": run_id, "event": "rejection_reason",
                            "reason": reason, "ts": _now()})
    if result.status in INTERRUPTED:
        return rec, "interrupted"
    return rec, None


def mode_suite(attempt: str) -> None:
    _check_freeze()
    imports = _sim_imports()
    evaluator = imports[0]
    AuditLog = imports[2]
    manifest = json.loads(SUITE_MANIFEST.read_text())
    scenarios = json.loads((ROOT / manifest["scenarios_file"]).read_text())
    if len(scenarios) != 8:
        raise SystemExit(f"Gate 3 scenarios file must contain 8 scenarios, "
                         f"found {len(scenarios)}")
    scenarios_by_index = {i: s for i, s in enumerate(scenarios)}
    records_path = RESULTS / f"records_{attempt}.jsonl"
    if records_path.exists():
        raise SystemExit(f"REFUSED: attempt {attempt} already exists - a "
                         f"rerun uses a NEW attempt id (harness protocol)")
    audit = AuditLog(RESULTS / "audit.jsonl")
    done = []
    for case in manifest["cases"]:
        print(f"\n=== {case['id']} ({case['source']})")
        rec, halt = _run_one(attempt, case, scenarios_by_index, audit, imports)
        done.append(rec)
        print(f"-> {rec['guard_status']} | outcome {rec['outcome']} | "
              f"executor_calls {rec['executor_calls']} | "
              f"motion_steps {rec['motion_steps']}")
        if halt == "interrupted":
            print("\nSUITE HALTED: interrupted status - terminal outcome "
                  "recorded; exiting non-success by design.")
            sys.exit(2)
        if halt == "harness":
            print("\nSUITE STOPPED: harness defect - preserve this "
                  "attempt, fix under a new candidate, rerun the "
                  "complete suite with new attempt IDs.")
            sys.exit(3)
    met = sum(1 for r in done
              if r["guard_status"] == r["expected_path"])
    summary = {"attempt": attempt, "cases": len(done),
               "expected_paths_met": met,
               "records": done}
    (RESULTS / f"suite_{attempt}.json").write_text(json.dumps(summary, indent=2))
    print(f"\nSUITE {attempt} COMPLETE: expected paths met {met}/{len(done)}. "
          f"Run --mode verify --attempt {attempt} for the audit verdicts.")


# ----------------------------------------------------------------- probes
def mode_probes(attempt: str) -> None:
    _check_freeze()
    imports = _sim_imports()
    evaluator, _grasp, AuditLog, run_guarded, _score = imports
    manifest = json.loads(PROBES_MANIFEST.read_text())
    scene = evaluator._reject_scene_state([0.45, 0.0])
    plan = {"part_id": "part", "target_zone": "target_zone",
            "approach_height_m": 0.15, "speed_scale": 0.5}
    audit = AuditLog(RESULTS / "audit_probes.jsonl")
    records_path = RESULTS / f"probe_records_{attempt}.jsonl"
    if records_path.exists():
        raise SystemExit(f"REFUSED: probe attempt {attempt} already exists")
    rows = []
    for probe in manifest["probes"]:
        run_id = f"{attempt}:{probe['id']}"
        calls = {"n": 0}

        def counting_executor(p, _c=calls):
            _c["n"] += 1
            return {"counted": True}

        kind = probe["kind"]
        if kind == "approval_error":
            def approve(p):
                raise RuntimeError("simulated approval failure")
            executor = counting_executor
        elif kind == "execution_error":
            def approve(p):
                return True

            def executor(p):
                raise RuntimeError("simulated execution failure")
        elif kind == "invalidation":
            def approve(p):
                p.speed_scale = 0.99  # mutate after validation
                return True
            executor = counting_executor
        elif kind == "interrupt":
            def approve(p):
                raise KeyboardInterrupt
            executor = counting_executor
        else:
            raise SystemExit(f"unknown probe kind: {kind}")
        result = run_guarded(plan, scene, executor, approve, audit,
                             run_id=run_id)
        ok = result.status == probe["expected_status"]
        if kind in ("approval_error", "invalidation", "interrupt"):
            ok = ok and calls["n"] == 0
        rec = {"run_id": run_id, "attempt": attempt,
               "case_id": probe["id"], "kind": kind,
               "expected_status": probe["expected_status"],
               "guard_status": result.status,
               "executor_calls": calls["n"], "passed": bool(ok),
               "started_ts": _now(), "decision": result.status,
               "outcome": "not_executed" if calls["n"] == 0 else "executed"}
        _append_record(records_path, rec)
        rows.append(rec)
        print(f"{probe['id']}: status={result.status} "
              f"executor_calls={calls['n']} -> {'PASS' if ok else 'FAIL'}")
        if kind == "interrupt":
            print("Interrupt probe reached: segment stops here, as "
                  "prefiled. This is the probe segment's expected end, "
                  "not an acceptance-suite interruption.")
            break
    payload = {"attempt": attempt, "all_passed": all(r["passed"] for r in rows),
               "probes": rows}
    (RESULTS / f"probes_{attempt}.json").write_text(json.dumps(payload, indent=2))
    print("PROBES:", "PASS" if payload["all_passed"] else "FAIL")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gate 5 runner + verifier")
    parser.add_argument("--mode", required=True,
                        choices=["freeze", "suite", "probes", "verify",
                                 "verify-selftest"])
    parser.add_argument("--attempt", default=None,
                        help="attempt id, e.g. A1 (required for suite, "
                             "probes, verify)")
    args = parser.parse_args()
    if args.mode == "freeze":
        mode_freeze()
    elif args.mode == "verify-selftest":
        mode_verify_selftest()
    elif args.mode in ("suite", "probes", "verify"):
        if not args.attempt:
            parser.error("--attempt is required for this mode")
        {"suite": mode_suite, "probes": mode_probes,
         "verify": mode_verify}[args.mode](args.attempt)


if __name__ == "__main__":
    main()
