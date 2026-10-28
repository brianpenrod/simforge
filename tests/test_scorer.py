"""Telemetry-scorer tests (Gate 2, Oct 28).

The scorer is a pure function of a telemetry trace, so most tests use
synthetic traces: a good full cycle must pass, and each way of almost
passing must fail with the right cause. The final test is the red
cell's NC-1 closure: the PRODUCTION scorer, fed REAL telemetry from a
no-op run of the actual cell, must reject it - a scorer that has never
been shown to say "fail" to the real system proves nothing.
"""
import pytest

from simforge.scoring import evaluate_attempt
from simforge.sim.cell import load_cell, reset_home, step_checked

DT = 0.002
REST_Z = 0.025
ZONE = {"min": [0.38, 0.21], "max": [0.52, 0.35]}   # the frozen cell's target_zone geom bounds
START = (0.45, 0.0)
HELD_Z = REST_Z + 0.10


def trace(states):
    """states: list of (duration_s, part_xyz, grip_force_n, table_contact).
    The hand is placed directly above the part (zero tracking offset)
    unless a state overrides it via a 4-tuple part + explicit hand -
    see trace_with_hand for the offset test."""
    out = []
    t = 0.0
    for dur, part, grip, table in states:
        hand = (part[0], part[1], part[2] + 0.10)
        for _ in range(int(round(dur / DT))):
            out.append({"t": t, "part": list(part), "hand": list(hand),
                        "grip_force_n": grip, "table_contact": table})
            t += DT
    return out


def good_cycle():
    return trace([
        (0.5, (START[0], START[1], REST_Z), 0.0, True),     # resting
        (1.0, (START[0], START[1], HELD_Z), 5.0, False),    # lifted, held
        (2.5, (0.45, 0.28, HELD_Z), 5.0, False),            # carried over zone, hold completes
        (1.5, (0.45, 0.28, REST_Z), 0.0, True),             # released, resting in zone
    ])


@pytest.mark.unit
def test_good_full_cycle_passes():
    r = evaluate_attempt(good_cycle(), REST_Z, ZONE)
    assert r["success"] is True, r
    assert r["lift_ok"] and r["transfer_ok"] and r["release_ok"]
    assert r["failure_cause"] is None


@pytest.mark.unit
def test_noop_trace_fails_as_miss():
    r = evaluate_attempt(trace([(3.0, (START[0], START[1], REST_Z), 0.0, True)]),
                         REST_Z, ZONE)
    assert r["success"] is False
    assert r["failure_cause"] == "miss"


@pytest.mark.unit
def test_split_hold_does_not_add_up():
    # 1.9 s good + a one-sample grip loss + 1.9 s good: total 3.8 s in
    # the air, but no SINGLE unbroken 2 s window - must fail.
    samples = trace([
        (1.9, (START[0], START[1], HELD_Z), 5.0, False),
        (DT, (START[0], START[1], HELD_Z), 0.0, False),     # grip lost for one sample
        (1.9, (START[0], START[1], HELD_Z), 5.0, False),
        (1.5, (START[0], START[1], REST_Z), 0.0, True),
    ])
    r = evaluate_attempt(samples, REST_Z, ZONE)
    assert r["success"] is False
    assert r["lift_ok"] is False
    assert r["longest_hold_s"] < 2.0


@pytest.mark.unit
def test_tracking_offset_breaks_the_hold():
    out = []
    t = 0.0
    states = [
        (3.0, (START[0], START[1], HELD_Z), (START[0] + 0.03, START[1], HELD_Z + 0.10), 5.0, False),
        (1.5, (0.45, 0.28, REST_Z), (0.45, 0.28, REST_Z + 0.10), 0.0, True),
    ]
    for dur, part, hand, grip, table in states:
        for _ in range(int(round(dur / DT))):
            out.append({"t": t, "part": list(part), "hand": list(hand),
                        "grip_force_n": grip, "table_contact": table})
            t += DT
    r = evaluate_attempt(out, REST_Z, ZONE)
    assert r["success"] is False
    assert r["lift_ok"] is False


@pytest.mark.unit
def test_table_contact_breaks_the_hold():
    samples = trace([
        (3.0, (START[0], START[1], HELD_Z), 5.0, True),     # "lifted" but touching the table
        (1.5, (0.45, 0.28, REST_Z), 0.0, True),
    ])
    r = evaluate_attempt(samples, REST_Z, ZONE)
    assert r["success"] is False
    assert r["lift_ok"] is False


@pytest.mark.unit
def test_hold_without_transfer_fails_as_transfer():
    samples = trace([
        (3.5, (START[0], START[1], HELD_Z), 5.0, False),    # perfect hold, wrong place
        (1.5, (START[0], START[1], REST_Z), 0.0, True),     # set back down at the start
    ])
    r = evaluate_attempt(samples, REST_Z, ZONE)
    assert r["success"] is False
    assert r["lift_ok"] is True
    assert r["failure_cause"] == "transfer"


@pytest.mark.unit
def test_release_outside_zone_fails_as_release():
    samples = trace([
        (1.0, (START[0], START[1], HELD_Z), 5.0, False),
        (2.5, (0.45, 0.28, HELD_Z), 5.0, False),            # over the zone, held
        (1.5, (START[0], START[1], REST_Z), 0.0, True),     # ...but ends resting at the start
    ])
    r = evaluate_attempt(samples, REST_Z, ZONE)
    assert r["success"] is False
    assert r["transfer_ok"] is True
    assert r["failure_cause"] == "release"


@pytest.mark.e2e
def test_scorer_rejects_real_noop_run():
    from simforge.scoring import CellIds, sample_state
    model, data, pad_geoms = load_cell()
    reset_home(model, data)
    ids = CellIds(model, pad_geoms)
    for _ in range(250):            # 0.5 s settle
        step_checked(model, data, 1)
    rest_z = float(data.xpos[ids.part_body][2])
    samples = []
    for _ in range(1000):           # 2 s, no commands at all
        step_checked(model, data, 1)
        samples.append(sample_state(model, data, ids))
    r = evaluate_attempt(samples, rest_z, ZONE)
    assert r["success"] is False
    assert r["failure_cause"] == "miss"
