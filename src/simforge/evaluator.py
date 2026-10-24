"""Gate 3 outcome evaluator — skeleton (Oct 24, Red Cell hardening).

Built BEFORE the real grasp exists, against a stub, so Gate 3 becomes
"plug in the real grasp" instead of "invent the harness on Friday."
A scenario is a dict: {name, seed, part_position, yaw_deg, friction_scale,
expect} where expect is "success" or "reject" (invalid-plan cases).
Perturbation rule (ratified amendment, Oct 24): the seed DRIVES the
perturbations — position jitter, yaw, friction — it is not a label.
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path


def perturb(scenario: dict) -> dict:
    rng = random.Random(scenario["seed"])
    x, y = scenario["part_position"]
    return {
        **scenario,
        "part_position": [x + rng.uniform(-0.010, 0.010), y + rng.uniform(-0.010, 0.010)],
        "yaw_deg": scenario.get("yaw_deg", 0.0) + rng.uniform(-10.0, 10.0),
        "friction_scale": scenario.get("friction_scale", 1.0) * rng.uniform(0.9, 1.1),
    }


def run_suite(scenarios: list[dict], grasp_fn, out_path: str | Path) -> dict:
    """grasp_fn(scenario) -> {"success": bool, "failure_cause": str | None}.
    Writes machine-readable results; returns the summary dict."""
    results = []
    for raw in scenarios:
        sc = perturb(raw)
        t0 = time.time()
        outcome = grasp_fn(sc)
        ok = outcome["success"] == (sc["expect"] == "success")
        results.append({
            "scenario": sc["name"], "seed": sc["seed"], "expect": sc["expect"],
            "success": outcome["success"], "failure_cause": outcome.get("failure_cause"),
            "passed": ok, "wall_s": round(time.time() - t0, 3),
            "perturbed": {"part_position": sc["part_position"], "yaw_deg": sc["yaw_deg"],
                          "friction_scale": sc["friction_scale"]},
        })
    summary = {"total": len(results), "passed": sum(r["passed"] for r in results),
               "results": results}
    Path(out_path).write_text(json.dumps(summary, indent=2))
    return summary


def _stub_grasp(scenario: dict) -> dict:
    """Always-succeed stub so the harness is testable before Gate 2 exists."""
    if scenario["expect"] == "reject":
        return {"success": False, "failure_cause": "rejected_invalid_plan"}
    return {"success": True, "failure_cause": None}


if __name__ == "__main__":
    scenarios = json.loads(Path(__file__).with_name("..").joinpath(
        "..", "scenarios", "example_scenarios.json").resolve().read_text())
    print(run_suite(scenarios, _stub_grasp, "results/gate3/stub_run.json")["passed"],
          "scenarios passed (stub)")
