"""SimForge Gate 1 check: frozen minimal cell loads, physics pins enforced,
10,000 steps, deterministic across two fresh runs.

Run from the repo root:  python gate1_check.py
Prints PASS/FAIL lines and a final verdict. Exit code 0 = pass.

Physics pins are loader-enforced here (not in the MJCF) so they are asserted
on every run and recorded in scene/manifest.json:
  - friction cone = elliptic
  - noslip_iterations = 10
  - finger-pad geoms condim = 4 (torsional friction)
"""
import pathlib
import sys

import mujoco
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent
CELL = ROOT / "scene" / "cell.xml"
STEPS = 10_000
TOL = 1e-6

failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def load_cell():
    model = mujoco.MjModel.from_xml_path(str(CELL))
    # --- physics pins (see module docstring) ---
    model.opt.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
    model.opt.noslip_iterations = 10
    pad_geoms = []
    for body_name in ("left_finger", "right_finger"):
        bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
        if bid < 0:
            continue
        for gid in range(model.ngeom):
            if model.geom_bodyid[gid] == bid:
                model.geom_condim[gid] = 4
                pad_geoms.append(gid)
    data = mujoco.MjData(model)
    return model, data, pad_geoms


def run_once():
    model, data, pad_geoms = load_cell()
    if model.nkey > 0:
        mujoco.mj_resetDataKeyframe(model, data, 0)
    else:
        mujoco.mj_resetData(model, data)
    mujoco.mj_forward(model, data)
    for _ in range(STEPS):
        mujoco.mj_step(model, data)
    return model, data, pad_geoms


def main():
    print(f"MuJoCo version: {mujoco.__version__}")
    check("version pin 3.15.0", mujoco.__version__ == "3.15.0", mujoco.__version__)

    model, data, pad_geoms = run_once()
    check("model loads", model.nq > 0,
          f"nq={model.nq} nv={model.nv} nu={model.nu} ngeom={model.ngeom} nkey={model.nkey}")
    check("cone == elliptic",
          int(model.opt.cone) == int(mujoco.mjtCone.mjCONE_ELLIPTIC))
    check("noslip_iterations == 10", model.opt.noslip_iterations == 10)
    if pad_geoms:
        check("finger pad geoms found", True, f"{len(pad_geoms)} geoms set to condim=4")
        check("pad condim readback == 4",
              all(int(model.geom_condim[g]) == 4 for g in pad_geoms))
    else:
        check("finger pad geoms found", False,
              "no left_finger/right_finger bodies; body names are: "
              + ", ".join(mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i) or "?"
                          for i in range(model.nbody)))

    part_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "part")
    part_z = float(data.xpos[part_id][2])
    check("part resting on table after 10k steps", abs(part_z - 0.025) < 0.002,
          f"part z = {part_z:.6f} (expect ~0.025)")

    state_a = np.concatenate([data.qpos.copy(), data.qvel.copy()])
    _, data2, _ = run_once()
    state_b = np.concatenate([data2.qpos.copy(), data2.qvel.copy()])
    diff = float(np.max(np.abs(state_a - state_b))) if state_a.size else 0.0
    check("determinism (two fresh 10k-step runs)", diff <= TOL,
          f"max |diff| = {diff:.3e} (tol {TOL:.0e})")
    print("final qpos:", np.array2string(data.qpos, precision=6))

    if failures:
        print(f"GATE 1 CHECK: FAIL ({len(failures)} check(s) failed)")
        return 1
    print("GATE 1 CHECK: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
