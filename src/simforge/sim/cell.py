"""Shared SimForge cell loader.

THE way to load the frozen Gate 1 cell: every script, test, and controller
must load through here so the physics pins are identical everywhere.
Pins (ratified Oct 24, recorded in scene/manifest.json):
  - friction cone = elliptic
  - noslip_iterations = 10
  - finger-pad geoms (all geoms on the finger bodies) condim = 4
"""
import pathlib

import mujoco

ROOT = pathlib.Path(__file__).resolve().parents[3]  # src/simforge/sim/cell.py -> repo root
CELL_XML = ROOT / "scene" / "cell.xml"
FINGER_BODIES = ("left_finger", "right_finger")


def load_cell():
    """Load the frozen cell and enforce the physics pins.

    Returns (model, data, pad_geoms).
    """
    model = mujoco.MjModel.from_xml_path(str(CELL_XML))
    model.opt.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
    model.opt.noslip_iterations = 10
    pad_geoms = []
    for body_name in FINGER_BODIES:
        bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
        if bid < 0:
            continue
        for gid in range(model.ngeom):
            if model.geom_bodyid[gid] == bid:
                model.geom_condim[gid] = 4
                pad_geoms.append(gid)
    data = mujoco.MjData(model)
    return model, data, pad_geoms


def reset_home(model, data):
    """Reset to the Panda home keyframe if present, else zeros; then forward."""
    if model.nkey > 0:
        mujoco.mj_resetDataKeyframe(model, data, 0)
    else:
        mujoco.mj_resetData(model, data)
    mujoco.mj_forward(model, data)
