"""Model probe (Gate 2, Task 3 step A) - run BEFORE writing the controller.

Prints everything the grasp controller needs to know about the frozen
cell's Panda, so nothing is guessed: actuator list with ctrl ranges and
what each drives, finger-joint addresses, sites, the hand body, and -
definitively - what the gripper actuator's min/max ctrl values DO to
the finger joints after stepping.

Run from the repo root:  python probe_model.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import mujoco
import numpy as np

from simforge.sim.cell import load_cell, reset_home, step_checked


def name(model, obj, i):
    return mujoco.mj_id2name(model, obj, i) or f"<unnamed {i}>"


def main():
    model, data, pad_geoms = load_cell()
    print(f"nu={model.nu} nq={model.nq} nsite={model.nsite} ntendon={model.ntendon}")
    print("\n-- actuators (index: name, ctrlrange, drives) --")
    for a in range(model.nu):
        trn = model.actuator_trnid[a]
        kind = {0: "joint", 1: "tendon", 2: "site"}.get(int(model.actuator_trntype[a]),
                                                         str(int(model.actuator_trntype[a])))
        target = name(model, mujoco.mjtObj.mjOBJ_JOINT if kind == "joint"
                      else mujoco.mjtObj.mjOBJ_TENDON if kind == "tendon"
                      else mujoco.mjtObj.mjOBJ_SITE, int(trn[0]))
        print(f"  ctrl[{a}] {name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, a)!r} "
              f"range={model.actuator_ctrlrange[a]} -> {kind} {target!r}")

    print("\n-- finger joints --")
    for j in range(model.njnt):
        jn = name(model, mujoco.mjtObj.mjOBJ_JOINT, j)
        if "finger" in jn:
            print(f"  {jn!r} qposadr={model.jnt_qposadr[j]} range={model.jnt_range[j]}")

    print("\n-- sites --")
    for s in range(model.nsite):
        bid = int(model.site_bodyid[s])
        print(f"  {name(model, mujoco.mjtObj.mjOBJ_SITE, s)!r} on body "
              f"{name(model, mujoco.mjtObj.mjOBJ_BODY, bid)!r} pos={model.site_pos[s]}")

    reset_home(model, data)
    hand = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "hand")
    print(f"\nhand body id={hand} xpos at home={data.xpos[hand]}")
    print(f"hand xmat at home (row-major):\n{np.round(data.xmat[hand].reshape(3, 3), 3)}")

    gripper = model.nu - 1
    lo, hi = model.actuator_ctrlrange[gripper]
    finger_adrs = [int(model.jnt_qposadr[j]) for j in range(model.njnt)
                   if "finger" in (name(model, mujoco.mjtObj.mjOBJ_JOINT, j))]
    for label, value in (("ctrlrange MIN", lo), ("ctrlrange MAX", hi)):
        reset_home(model, data)
        data.ctrl[gripper] = value
        step_checked(model, data, 250)  # 0.5 s
        fingers = [round(float(data.qpos[a]), 4) for a in finger_adrs]
        print(f"gripper ctrl={value} ({label}) -> finger qpos after 0.5 s: {fingers}")


if __name__ == "__main__":
    main()
