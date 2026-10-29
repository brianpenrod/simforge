"""Release-predicate regression tests (Astra review #3, Oct 28).

Astra constructed a false pass against the Oct 28 scorer: after a valid
lift and transfer, a "release" phase with the part hovering 1 mm above
rest height - zero grip force, NO table contact - satisfied the release
predicate, because rest_sample_ok never required the part to actually
be supported by the table. These tests pin the fix: hovering is not
resting; table-supported rest still passes.
"""
import pytest

from simforge.scoring import evaluate_attempt

DT = 0.002
REST_Z = 0.025
ZONE = {"min": [0.38, 0.21], "max": [0.52, 0.35]}
START = (0.45, 0.0)
HELD_Z = REST_Z + 0.10


def trace(states):
    """states: list of (duration_s, part_xyz, grip_force_n, table_contact)."""
    out = []
    t = 0.0
    for dur, part, grip, table in states:
        hand = (part[0], part[1], part[2] + 0.10)
        for _ in range(int(round(dur / DT))):
            out.append({"t": t, "part": list(part), "hand": list(hand),
                        "grip_force_n": grip, "table_contact": table})
            t += DT
    return out


def cycle_ending(final_state):
    return trace([
        (0.5, (START[0], START[1], REST_Z), 0.0, True),   # resting
        (1.0, (START[0], START[1], HELD_Z), 5.0, False),  # lifted, held
        (2.5, (0.45, 0.28, HELD_Z), 5.0, False),          # over the zone
        final_state,                                      # the "release"
    ])


@pytest.mark.unit
def test_hovering_part_is_not_a_release():
    # Astra's probe: 1 mm above rest height, grip zero, touching NOTHING,
    # sustained well past RELEASE_REST_S. Must fail as "release".
    r = evaluate_attempt(
        cycle_ending((1.5, (0.45, 0.28, REST_Z + 0.001), 0.0, False)),
        REST_Z, ZONE)
    assert r["success"] is False, r
    assert r["release_ok"] is False
    assert r["failure_cause"] == "release"


@pytest.mark.unit
def test_table_supported_rest_still_passes():
    # Control: the same cycle ending in a genuine table-supported rest.
    r = evaluate_attempt(
        cycle_ending((1.5, (0.45, 0.28, REST_Z), 0.0, True)),
        REST_Z, ZONE)
    assert r["success"] is True, r
    assert r["release_ok"] is True
