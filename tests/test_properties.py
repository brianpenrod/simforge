"""Property-based checks (Hypothesis) - Astra repo recommendation,
adopted Oct 29 as a SUPPLEMENT to the gate suites, not a gate criterion.

Targets are the fast, pure functions a hostile input can actually
reach: the telemetry scorer and the plan validators. Three contracts:

1. No contiguous 2 s hold window, no lift - however the violations are
   distributed (grip loss, table contact, tracking offset, dip), and
   however good the surrounding samples look on average.
2. validate_syntax either raises ValueError or returns a plan fully
   inside the ratified ranges with finite numbers.
3. validate_semantics either raises ValueError or the part position is
   finite, inside the workspace, and at/above the table. (NaN
   coordinates are the case to watch: NaN comparisons are False, so a
   check written as "z < table" alone waves NaN through.)
"""
import math

import pytest

pytest.importorskip("hypothesis")

from hypothesis import example, given, settings, strategies as st

from simforge.plan_schema import Plan, validate_semantics, validate_syntax
from simforge.scoring import evaluate_attempt

DT = 0.002
REST_Z = 0.025
ZONE = {"min": [0.38, 0.21], "max": [0.52, 0.35]}
START = (0.45, 0.0)
HELD_Z = REST_Z + 0.10
VIOLATIONS = ["grip_zero", "table_contact", "offset", "dip"]


@st.composite
def broken_hold_traces(draw):
    """Good lifted segments, each strictly under 2 s, separated by a
    violating sample group of a drawn type."""
    segments = draw(st.lists(
        st.tuples(st.integers(min_value=50, max_value=950),
                  st.sampled_from(VIOLATIONS)),
        min_size=1, max_size=4))
    samples = []
    t = 0.0

    def push(part, hand, grip, table, n=1):
        nonlocal t
        for _ in range(n):
            samples.append({"t": t, "part": list(part), "hand": list(hand),
                            "grip_force_n": grip, "table_contact": table})
            t += DT

    start = (START[0], START[1], REST_Z)
    above_start = (start[0], start[1], start[2] + 0.10)
    held = (START[0], START[1], HELD_Z)
    above_held = (held[0], held[1], held[2] + 0.10)
    push(start, above_start, 0.0, True, 250)
    for steps, violation in segments:
        push(held, above_held, 5.0, False, steps)
        if violation == "grip_zero":
            push(held, above_held, 0.0, False, 3)
        elif violation == "table_contact":
            push(held, above_held, 5.0, True, 3)
        elif violation == "offset":
            push(held, (held[0] + 0.05, held[1], held[2] + 0.10), 5.0, False, 3)
        else:  # dip
            push(start, above_start, 5.0, False, 3)
    push(start, above_start, 0.0, True, 250)
    return samples


@settings(max_examples=40, deadline=None)
@given(samples=broken_hold_traces())
def test_no_contiguous_hold_means_no_lift(samples):
    r = evaluate_attempt(samples, REST_Z, ZONE)
    assert r["lift_ok"] is False
    assert r["success"] is False


@settings(max_examples=60, deadline=None)
@given(h=st.floats(allow_nan=True, allow_infinity=True),
       s=st.floats(allow_nan=True, allow_infinity=True),
       pid=st.sampled_from(["part", "part_ghost", "", "PART"]),
       zone=st.sampled_from(["target_zone", "zone_b", ""]))
def test_syntax_contract(h, s, pid, zone):
    raw = {"part_id": pid, "target_zone": zone,
           "approach_height_m": h, "speed_scale": s}
    try:
        plan = validate_syntax(raw)
    except ValueError:
        return
    assert plan.part_id and plan.target_zone
    assert math.isfinite(plan.approach_height_m)
    assert 0.02 <= plan.approach_height_m <= 0.50
    assert math.isfinite(plan.speed_scale)
    assert 0.1 <= plan.speed_scale <= 1.0


@settings(max_examples=60, deadline=None)
@given(x=st.floats(allow_nan=True, allow_infinity=True),
       y=st.floats(allow_nan=True, allow_infinity=True),
       z=st.floats(allow_nan=True, allow_infinity=True))
@example(x=0.45, y=0.0, z=float("nan"))
@example(x=0.45, y=0.0, z=float("inf"))
def test_semantics_contract(x, y, z):
    scene = {"parts": {"part": {"position": [x, y, z]}},
             "zones": {"target_zone": ZONE},
             "table_height_m": 0.0,
             "workspace": {"min": [-0.5, -0.4], "max": [0.7, 0.4]}}
    plan = Plan("part", "target_zone", 0.10, 0.5)
    try:
        validate_semantics(plan, scene)
    except ValueError:
        return
    assert all(math.isfinite(v) for v in (x, y, z))
    assert -0.5 <= x <= 0.7 and -0.4 <= y <= 0.4
    assert z >= 0.0
