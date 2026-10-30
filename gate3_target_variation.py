"""Gate 3 target-variation demonstration (Oct 30, closing the
coverage qualification from Astra review #4).

GATE_METRICS has always required a changed-target case. The filed
suite substituted speed/height variation (plan_variation); that was
documented but never ratified as a coverage amendment, and on Oct 29
Brian ratified the full path instead: DEMONSTRATE the changed
destination.

Two runs through the ordinary evaluator, same part, same plan fields:
  - target_filed:     zone at its filed center (0.45, 0.28),
                      bounds x [0.38, 0.52], y [0.21, 0.35].
  - target_relocated: zone geom moved at setup to (0.15, -0.25),
                      bounds x [0.08, 0.22], y [-0.32, -0.18].
The two bound sets are DISJOINT, and the scorer reads the zone bounds
from the live model - so a success on the relocated run is only
possible if the part was actually placed at the new destination.

Evidence: results/gate3/target_variation.json (the run_suite summary,
including each row's scorer metrics and final rest position) and
target_variation_summary.txt.
Run from the repo root:  python gate3_target_variation.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from simforge.evaluator import run_suite

OUT = ROOT / "results" / "gate3"
PLAN = {"part_id": "part", "target_zone": "target_zone",
        "approach_height_m": 0.10, "speed_scale": 0.5}
RELOCATED = [0.15, -0.25]
RELOCATED_BOUNDS = {"min": [0.08, -0.32], "max": [0.22, -0.18]}


def main():
    scenarios = [
        {"name": "target_filed", "seed": 401, "part_position": [0.45, 0.0],
         "expect": "success", "plan": dict(PLAN)},
        {"name": "target_relocated", "seed": 401,
         "part_position": [0.45, 0.0], "expect": "success",
         "target_zone_pos": RELOCATED, "plan": dict(PLAN)},
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    summary = run_suite(scenarios, OUT / "target_variation.json")
    lines = ["Gate 3 target-variation demonstration:"]
    ok = True
    for row in summary["results"]:
        lines.append(f"  {row['scenario']}: success={row.get('success')} "
                     f"release_ok={row.get('release_ok')} "
                     f"executor_called={row['executor_called']}")
        ok = ok and bool(row.get("success"))
    lines.append("Relocated bounds x [0.08, 0.22], y [-0.32, -0.18] are "
                 "disjoint from the filed bounds x [0.38, 0.52], "
                 "y [0.21, 0.35]; the scorer reads bounds from the live "
                 "model, so the relocated success required placement at "
                 "the new destination.")
    lines.append(f"TARGET VARIATION: {'DEMONSTRATED' if ok else 'NOT DEMONSTRATED'}")
    (OUT / "target_variation_summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
