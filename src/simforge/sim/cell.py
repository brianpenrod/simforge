"""Shared SimForge cell loader + guarded stepper.

THE way to load and step the frozen Gate 1 cell: every script, test, and
controller must go through here so the physics pins and the failure
detection are identical everywhere.
Pins (ratified Oct 24, recorded in scene/manifest.json):
  - friction cone = elliptic
  - noslip_iterations = 10
  - finger-pad geoms (all geoms on the finger bodies) condim = 4

step_checked exists because of the Oct 28 red-cell finding: MuJoCo can
warn and silently auto-reset after a numerical failure, and a raw
mj_step loop reports that as success. Gate evidence must never come
from a run the simulator quietly repaired.
"""
import pathlib

import mujoco
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]  # src/simforge/sim/cell.py -> repo root
CELL_XML = ROOT / "scene" / "cell.xml"
FINGER_BODIES = ("left_finger", "right_finger")
EXPECTED_PAD_GEOMS = 16  # frozen scene: 8 pad geoms per finger (Gate 1 manifest)


def load_cell():
    """Load the frozen cell and enforce the physics pins.

    Returns (model, data, pad_geoms). Raises RuntimeError if a finger
    body is missing or the pad-geom count differs from the frozen
    scene - a silent skip here would quietly un-pin the grasp physics.
    """
    model = mujoco.MjModel.from_xml_path(str(CELL_XML))
    model.opt.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
    model.opt.noslip_iterations = 10
    pad_geoms = []
    for body_name in FINGER_BODIES:
        bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
        if bid < 0:
            raise RuntimeError(f"finger body {body_name!r} not found in cell model")
        for gid in range(model.ngeom):
            if model.geom_bodyid[gid] == bid:
                model.geom_condim[gid] = 4
                pad_geoms.append(gid)
    if len(pad_geoms) != EXPECTED_PAD_GEOMS:
        raise RuntimeError(
            f"expected {EXPECTED_PAD_GEOMS} finger pad geoms, found {len(pad_geoms)}"
        )
    data = mujoco.MjData(model)
    return model, data, pad_geoms


def reset_home(model, data):
    """Reset to the Panda home keyframe if present, else zeros; then forward."""
    if model.nkey > 0:
        mujoco.mj_resetDataKeyframe(model, data, 0)
    else:
        mujoco.mj_resetData(model, data)
    mujoco.mj_forward(model, data)


def warning_count(data) -> int:
    """Total MuJoCo warnings recorded on this data since its last reset."""
    return int(sum(data.warning[i].number for i in range(mujoco.mjtWarning.mjNWARNING)))


def step_checked(model, data, n_steps: int) -> float:
    """Step n_steps, raising RuntimeError if the simulator warns, resets,
    loses time, or produces nonfinite state.

    Returns the elapsed sim time for this call, which must equal
    n_steps * timestep: a silent auto-reset restarts the clock and
    shows up here as lost time even if its warning counters were
    cleared by the reset. Warning counts are cumulative on `data`,
    so in a chunked loop a warning fails every later call too - an
    attempt that warned once is never clean again.
    """
    dt = float(model.opt.timestep)
    start = float(data.time)
    prev = start
    for _ in range(n_steps):
        mujoco.mj_step(model, data)
        if not (np.isfinite(data.qpos).all() and np.isfinite(data.qvel).all()):
            raise RuntimeError("nonfinite state (qpos/qvel) during stepping")
        t = float(data.time)
        if t < prev - 1e-12:
            raise RuntimeError(f"simulator reset detected: time went {prev:.4f} -> {t:.4f}")
        prev = t
    elapsed = float(data.time) - start
    expected = n_steps * dt
    if abs(elapsed - expected) > 1e-6:
        raise RuntimeError(f"lost sim time: stepped {elapsed:.6f}s, expected {expected:.6f}s")
    n_warn = warning_count(data)
    if n_warn:
        raise RuntimeError(f"MuJoCo recorded {n_warn} warning(s) during stepping")
    return elapsed
