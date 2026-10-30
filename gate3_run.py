"""Gate 3 suite driver (Oct 29; verdict + evidence integrity Oct 30
per Astra review #4).

Run 1: the 8 scenarios at their filed seeds.
Run 2: the same scenarios with a +1000 seed offset (fresh draws).
Agreement: outcome CLASS per scenario, matched by name.

GATE 3 verdict (GATE_METRICS as amended Oct 28, clarified Oct 29) is
computed by ONE complete verdict function:
  - exactly the 8 filed scenarios, unique names, manifest-valid
    (a preflight/harness error FAILS the run visibly under its run id
    and can never leave a prior PASS artifact looking current: prior
    outputs rotate to *_prev at startup);
  - run 1 meets ALL 8 declared expectations;
  - run 1 wall-clock <= 1200 s (the unattended-suite bound, measured
    here on the build laptop);
  - fresh-draw agreement >= 7/8. Any flip makes the verdict
    CONDITIONAL until its explanation is recorded in the GATE_METRICS
    annotation.

Evidence: results/gate3/suite_run1.json, suite_run2.json,
agreement.json, gate3_summary.txt (all carry the run id).
Run from the repo root:  python gate3_run.py
"""
import json
import pathlib
import sys
import time
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from simforge.evaluator import compare_runs, run_suite

OUT = ROOT / "results" / "gate3"
RUN_ID = datetime.now().strftime("%Y%m%dT%H%M%S")
EXPECTED_COUNT = 8
WALL_BOUND_S = 1200.0


def _rotate_prior():
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("suite_run1.json", "suite_run2.json",
                 "agreement.json", "gate3_summary.txt"):
        prior = OUT / name
        if prior.exists():
            prior.replace(OUT / name.replace(".", "_prev.", 1))


def _fail_harness(error: str) -> int:
    (OUT / "harness_error.json").write_text(json.dumps(
        {"run_id": RUN_ID, "phase": "preflight", "error": error}, indent=2))
    lines = [f"Gate 3 run {RUN_ID}: HARNESS ERROR - {error}",
             "GATE 3: FAIL"]
    (OUT / "gate3_summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 1


def main():
    _rotate_prior()
    scenarios = json.loads((ROOT / "scenarios" / "example_scenarios.json")
                           .read_text())
    try:
        t0 = time.time()
        run1 = run_suite(scenarios, OUT / "suite_run1.json", seed_offset=0)
        wall1 = time.time() - t0
    except ValueError as exc:  # manifest preflight failure
        return _fail_harness(str(exc))
    for r in run1["results"]:
        print(f"run1 {r['scenario']}: {'MET' if r['passed'] else 'MISSED'} "
              f"({r['outcome_class']})", flush=True)
    print(f"run1 wall-clock: {wall1:.1f} s (bound: {WALL_BOUND_S:.0f} s)",
          flush=True)

    run2 = run_suite(scenarios, OUT / "suite_run2.json", seed_offset=1000)
    for r in run2["results"]:
        print(f"run2 {r['scenario']}: {'MET' if r['passed'] else 'MISSED'} "
              f"({r['outcome_class']})", flush=True)

    agreement = compare_runs(run1, run2)
    agreement["run_id"] = RUN_ID
    (OUT / "agreement.json").write_text(json.dumps(agreement, indent=2))

    names = [s["name"] for s in scenarios]
    checks = {
        "eight_scenarios": len(scenarios) == EXPECTED_COUNT,
        "unique_names": len(set(names)) == len(names),
        "run1_all_expectations_met": bool(run1["all_expectations_met"]),
        "run1_wall_within_bound": wall1 <= WALL_BOUND_S,
        "agreement_at_least_7_of_8": agreement["agreement"] >= 7,
    }
    flips = agreement["flips"]
    if all(checks.values()) and not flips:
        verdict, code = "PASS", 0
    elif all(checks.values()) and flips:
        verdict = ("CONDITIONAL PASS - flips require written explanation "
                   "in the GATE_METRICS annotation")
        code = 0
    else:
        verdict, code = "FAIL", 1

    lines = [f"Gate 3 run {RUN_ID}: run 1 {run1['expectations_met']}/8 "
             f"expectations met (all met: {run1['all_expectations_met']}), "
             f"wall-clock {wall1:.1f} s (bound {WALL_BOUND_S:.0f} s)",
             f"Fresh-draw agreement: {agreement['agreement']}/8"]
    for name, ok in checks.items():
        lines.append(f"  check {name}: {'ok' if ok else 'FAILED'}")
    for flip in flips:
        lines.append(f"  FLIP {flip['scenario']}: {flip['run_a']} -> "
                     f"{flip['run_b']} (explanation required)")
    lines.append(f"GATE 3: {verdict}")
    (OUT / "gate3_summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())

