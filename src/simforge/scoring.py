"""Gate 2 telemetry scorer.

The ONLY judge of grasp success. It reads a recorded telemetry trace -
never the controller - and applies the ratified Gate 2 criteria
(GATE_METRICS.md, as amended Oct 27-28):

- LIFT: part rises >= 5 cm and stays up through ONE contiguous >= 2 s
  window in which, at every sample: lift >= 5 cm, part-to-gripper
  horizontal offset <= 2 cm, no part-table contact, gripper-part
  contact force > 0.
- TRANSFER: while held and lifted, the part center enters the target
  zone's x/y bounds.
- RELEASE: after transfer, the gripper lets go and the part rests on
  the table inside the zone for >= 1 s.

evaluate_attempt is a pure function of the trace: the same code judges
real attempts, negative controls, and synthetic traces in unit tests.
The battery runner owns the 30 s attempt limit; when it truncates an
attempt it logs cause "timeout" itself.
"""
from __future__ import annotations

import mujoco
import numpy as np

LIFT_MIN_M = 0.05
HOLD_S = 2.0
TRACK_MAX_M = 0.02
RELEASE_REST_S = 1.0
REST_BAND_M = 0.002        # |part z - rest z| within this = resting on the table
REST_DRIFT_M = 0.002       # max x/y drift inside the post-release rest window
CONTACT_EPS_N = 1e-3       # force above this counts as real contact


# ---------------------------------------------------------------- capture

class CellIds:
    """Resolved body/geom ids for telemetry capture. Strict, like the
    loader: a missing hand body or table geom is an error, not a skip."""

    def __init__(self, model, pad_geoms):
        self.part_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "part")
        self.hand_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "hand")
        if self.part_body < 0 or self.hand_body < 0:
            raise RuntimeError("cell model is missing the part or hand body")
        self.pad_geoms = set(int(g) for g in pad_geoms)
        self.part_geoms = {g for g in range(model.ngeom)
                           if int(model.geom_bodyid[g]) == self.part_body}
        table_gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "table_top")
        if table_gid < 0:
            raise RuntimeError("cell model is missing the table_top geom")
        self.table_geoms = {int(table_gid)}


def sample_state(model, data, ids: CellIds) -> dict:
    """One telemetry sample from live sim state."""
    grip_force = 0.0
    table_contact = False
    force = np.zeros(6)
    for i in range(data.ncon):
        c = data.contact[i]
        pair = {int(c.geom1), int(c.geom2)}
        if pair & ids.part_geoms:
            if pair & ids.pad_geoms:
                mujoco.mj_contactForce(model, data, i, force)
                grip_force += abs(float(force[0]))
            if pair & ids.table_geoms:
                table_contact = True
    return {
        "t": float(data.time),
        "part": [float(v) for v in data.xpos[ids.part_body]],
        "hand": [float(v) for v in data.xpos[ids.hand_body]],
        "grip_force_n": grip_force,
        "table_contact": table_contact,
    }


# ---------------------------------------------------------------- scoring

def _offset_xy(part, hand) -> float:
    return float(np.hypot(part[0] - hand[0], part[1] - hand[1]))


def _in_zone(pos, zone) -> bool:
    return (zone["min"][0] <= pos[0] <= zone["max"][0]
            and zone["min"][1] <= pos[1] <= zone["max"][1])


def evaluate_attempt(samples, rest_z: float, zone: dict) -> dict:
    """Score one attempt's telemetry trace against the Gate 2 criteria.

    samples: time-ordered dicts from sample_state (or synthetic dicts
    with the same keys, as in the unit tests). rest_z: the part's
    resting center height, measured before the attempt moves.
    zone: {"min": [x, y, ...], "max": [x, y, ...]} target-zone bounds.
    """
    result = {
        "success": False,
        "failure_cause": None,
        "lift_ok": False,
        "transfer_ok": False,
        "release_ok": False,
        "max_rise_m": 0.0,
        "longest_hold_s": 0.0,
        "hold_min_grip_force_n": None,
        "hold_max_offset_m": None,
        "duration_s": 0.0,
        "final_part_pos": None,
    }
    if not samples:
        result["failure_cause"] = "miss"
        return result

    result["duration_s"] = samples[-1]["t"] - samples[0]["t"]
    result["final_part_pos"] = list(samples[-1]["part"])
    result["max_rise_m"] = max(s["part"][2] for s in samples) - rest_z

    def lift_sample_ok(s) -> bool:
        return (s["part"][2] - rest_z >= LIFT_MIN_M
                and _offset_xy(s["part"], s["hand"]) <= TRACK_MAX_M
                and not s["table_contact"]
                and s["grip_force_n"] > CONTACT_EPS_N)

    # --- lift: find runs of consecutive good samples; the hold must be
    # ONE contiguous run spanning >= HOLD_S (split holds do not add up).
    runs = []
    run_start = None
    for i, s in enumerate(samples):
        if lift_sample_ok(s):
            if run_start is None:
                run_start = i
        elif run_start is not None:
            runs.append((run_start, i - 1))
            run_start = None
    if run_start is not None:
        runs.append((run_start, len(samples) - 1))

    hold = None
    for a, b in runs:
        dur = samples[b]["t"] - samples[a]["t"]
        result["longest_hold_s"] = max(result["longest_hold_s"], dur)
        if hold is None and dur >= HOLD_S - 1e-9:
            hold = (a, b)
    result["lift_ok"] = hold is not None

    if not result["lift_ok"]:
        if result["max_rise_m"] < LIFT_MIN_M:
            result["failure_cause"] = "miss"      # never got it up
        else:
            first_lift = next(i for i, s in enumerate(samples)
                              if s["part"][2] - rest_z >= LIFT_MIN_M)
            dropped = any(s["table_contact"] and s["part"][2] - rest_z <= REST_BAND_M
                          for s in samples[first_lift:])
            result["failure_cause"] = "drop" if dropped else "slip"
        return result

    hold_a, hold_b = hold
    window = samples[hold_a:hold_b + 1]
    result["hold_min_grip_force_n"] = min(s["grip_force_n"] for s in window)
    result["hold_max_offset_m"] = max(_offset_xy(s["part"], s["hand"]) for s in window)

    # --- transfer: held and lifted, part center inside the zone.
    transfer_idx = None
    for i in range(hold_a, len(samples)):
        s = samples[i]
        if (s["grip_force_n"] > CONTACT_EPS_N
                and s["part"][2] - rest_z >= LIFT_MIN_M
                and _in_zone(s["part"], zone)):
            transfer_idx = i
            break
    result["transfer_ok"] = transfer_idx is not None
    if not result["transfer_ok"]:
        result["failure_cause"] = "transfer"
        return result

    # --- release: gripper lets go; part rests in the zone >= RELEASE_REST_S.
    def rest_sample_ok(s) -> bool:
        return (s["grip_force_n"] <= CONTACT_EPS_N
                and abs(s["part"][2] - rest_z) <= REST_BAND_M
                and _in_zone(s["part"], zone))

    release_ok = False
    run_start = None
    run_anchor = None
    for i in range(transfer_idx, len(samples)):
        s = samples[i]
        if rest_sample_ok(s):
            if run_start is None:
                run_start, run_anchor = i, s["part"]
            drift = float(np.hypot(s["part"][0] - run_anchor[0],
                                   s["part"][1] - run_anchor[1]))
            if drift > REST_DRIFT_M:
                run_start, run_anchor = i, s["part"]
            elif s["t"] - samples[run_start]["t"] >= RELEASE_REST_S - 1e-9:
                release_ok = True
                break
        else:
            run_start, run_anchor = None, None
    result["release_ok"] = release_ok
    if not release_ok:
        result["failure_cause"] = "release"
        return result

    result["success"] = True
    return result
