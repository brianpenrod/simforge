"""Gate 3 evaluator tests (Oct 29 rebuild).

The properties under test are the ones Astra's reviews attacked:
  - A rejection scenario passes ONLY through validation, with the
    executor never invoked (no timeout/failure can masquerade as one).
  - An execution scenario's verdict comes from the telemetry scorer
    over whatever trace the executor produced - here a synthetic good
    trace anchored at the real part position.
  - An executor exception is a logged failure row, never a crash and
    never a pass.
  - compare_runs measures outcome-CLASS agreement and names flips.
"""
import pytest

from simforge.evaluator import compare_runs, run_suite

DT = 0.002
ZONE_C = (0.45, 0.28)


def good_trace(part_xy, rest_z):
    """A synthetic scorer-passing trace: rest at the part, lift, carry
    over the zone, table-supported rest in the zone."""
    states = [
        (0.5, (part_xy[0], part_xy[1], rest_z), 0.0, True),
        (1.0, (part_xy[0], part_xy[1], rest_z + 0.10), 5.0, False),
        (2.5, (ZONE_C[0], ZONE_C[1], rest_z + 0.10), 5.0, False),
        (1.5, (ZONE_C[0], ZONE_C[1], rest_z), 0.0, True),
    ]
    out, t = [], 0.0
    for dur, part, grip, table in states:
        hand = (part[0], part[1], part[2] + 0.10)
        for _ in range(int(round(dur / DT))):
            out.append({"t": t, "part": list(part), "hand": list(hand),
                        "grip_force_n": grip, "table_contact": table})
            t += DT
    return out


SUCCESS_SC = {"name": "t_success", "seed": 1, "part_position": [0.45, 0.0],
              "expect": "success",
              "plan": {"part_id": "part", "target_zone": "target_zone",
                       "approach_height_m": 0.10, "speed_scale": 0.5}}
REJECT_SC = {"name": "t_reject", "seed": 2, "part_position": [0.45, 0.0],
             "expect": "reject",
             "plan": {"part_id": "part_ghost", "target_zone": "target_zone",
                      "approach_height_m": 0.10, "speed_scale": 0.5}}


@pytest.mark.unit
def test_reject_scenario_never_touches_the_executor(tmp_path):
    calls = []

    def spy(model, data, plan, ids):
        calls.append(plan)
        return []

    s = run_suite([REJECT_SC], tmp_path / "r.json", execute_fn=spy)
    row = s["results"][0]
    assert row["passed"] is True
    assert row["outcome_class"] == "rejected"
    assert row["executor_called"] is False
    assert calls == []


@pytest.mark.unit
def test_success_scenario_is_judged_by_the_scorer(tmp_path):
    def fake_execute(model, data, plan, ids):
        part = data.xpos[ids.part_body]
        return good_trace((float(part[0]), float(part[1])), float(part[2]))

    s = run_suite([SUCCESS_SC], tmp_path / "r.json", execute_fn=fake_execute)
    row = s["results"][0]
    assert row["executor_called"] is True
    assert row["passed"] is True, row
    assert row["outcome_class"] == "success"


@pytest.mark.unit
def test_executor_exception_is_a_failure_row_not_a_crash(tmp_path):
    def boom(model, data, plan, ids):
        raise RuntimeError("IK exploded")

    s = run_suite([SUCCESS_SC], tmp_path / "r.json", execute_fn=boom)
    row = s["results"][0]
    assert row["passed"] is False
    assert row["outcome_class"] == "failure"
    assert row["failure_cause"] == "sim_error"
    assert s["all_expectations_met"] is False


@pytest.mark.unit
def test_compare_runs_counts_class_agreement_and_names_flips():
    a = {"results": [{"scenario": "x", "outcome_class": "success"},
                     {"scenario": "y", "outcome_class": "failure"}]}
    b = {"results": [{"scenario": "x", "outcome_class": "success"},
                     {"scenario": "y", "outcome_class": "success"}]}
    c = compare_runs(a, b)
    assert c["total"] == 2 and c["agreement"] == 1
    assert c["flips"] == [{"scenario": "y", "run_a": "failure",
                           "run_b": "success"}]


