"""Gate 3 suite driver (Oct 29): both runs + agreement + verdict.

Run 1: the 8 scenarios at their filed seeds.
Run 2: the same scenarios with a +1000 seed offset (fresh draws).
Agreement: outcome CLASS per scenario (success | rejected | failure),
matched by scenario name (evaluator.compare_runs).

GATE 3 PASS (GATE_METRICS as amended Oct 28) requires BOTH:
  - run 1 meets ALL 8 declared expectations, and
  - agreement >= 7/8, with every flip listed for explanation.
The <= 20 min suite bound is WALL-CLOCK for one full suite run,
measured here on the build laptop.

Evidence: results/gate3/suite_run1.json, suite_run2.json,
agreement.json, gate3_summary.txt.
Run from the repo root:  python gate3_run.py
"""
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from simforge.evaluator import compare_runs, run_suite

OUT = ROOT / "results" / "gate3"


def main():
    scenarios = json.loads((ROOT / "scenarios" / "example_scenarios.json")
                           .read_text())
    OUT.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    run1 = run_suite(scenarios, OUT / "suite_run1.json", seed_offset=0)
    wall1 = time.time() - t0
    for r in run1["results"]:
        print(f"run1 {r['scenario']}: {'MET' if r['passed'] else 'MISSED'} "
              f"({r['outcome_class']})", flush=True)
    print(f"run1 wall-clock: {wall1:.1f} s (bound: 1200 s)", flush=True)

    run2 = run_suite(scenarios, OUT / "suite_run2.json", seed_offset=1000)
    for r in run2["results"]:
        print(f"run2 {r['scenario']}: {'MET' if r['passed'] else 'MISSED'} "
              f"({r['outcome_class']})", flush=True)

    agreement = compare_runs(run1, run2)
    (OUT / "agreement.json").write_text(json.dumps(agreement, indent=2))

    gate3_pass = run1["all_expectations_met"] and agreement["agreement"] >= 7
    lines = [f"Gate 3 run 1: {run1['expectations_met']}/8 expectations met "
             f"(all met: {run1['all_expectations_met']}), "
             f"wall-clock {wall1:.1f} s",
             f"Fresh-draw agreement: {agreement['agreement']}/8"]
    for flip in agreement["flips"]:
        lines.append(f"  FLIP {flip['scenario']}: {flip['run_a']} -> "
                     f"{flip['run_b']} (explanation required)")
    lines.append(f"GATE 3: {'PASS' if gate3_pass else 'FAIL'}")
    (OUT / "gate3_summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if gate3_pass else 1


if __name__ == "__main__":
    sys.exit(main())
