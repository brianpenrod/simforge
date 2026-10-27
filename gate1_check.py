"""SimForge Gate 1 check (ratified metrics, GATE_METRICS.md):
- scene loads from the frozen cell with zero missing-asset errors
- physics pins enforced via the shared loader (src/simforge/sim/cell.py)
- 10,000 steps, part resting on the table
- determinism: the same run 3x produces identical final state (tol 1e-6)

Writes its full output to results/gate1/gate1_check_output.txt (gate evidence).
Run from the repo root:  python gate1_check.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import mujoco
import numpy as np

from simforge.sim.cell import load_cell, reset_home

STEPS = 10_000
RUNS = 3
TOL = 1e-6
OUT = ROOT / "results" / "gate1" / "gate1_check_output.txt"

lines = []
failures = []


def emit(s=""):
    print(s)
    lines.append(s)


def check(name, ok, detail=""):
    emit(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def run_once():
    model, data, pad_geoms = load_cell()
    reset_home(model, data)
    for _ in range(STEPS):
        mujoco.mj_step(model, data)
    return model, data, pad_geoms


def main():
    emit("SimForge Gate 1 check")
    emit(f"MuJoCo version: {mujoco.__version__}")
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
        check("finger pad geoms found", False, "no finger geoms set - see loader FINGER_BODIES")

    emit(f"effective config: timestep={model.opt.timestep} integrator={int(model.opt.integrator)} "
         f"solver_iterations={model.opt.iterations} solver_tolerance={model.opt.tolerance} "
         f"cone={int(model.opt.cone)} noslip_iterations={model.opt.noslip_iterations}")

    part_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "part")
    part_z = float(data.xpos[part_id][2])
    check("part resting on table after 10k steps", abs(part_z - 0.025) < 0.002,
          f"part z = {part_z:.6f} (expect ~0.025)")

    states = [np.concatenate([data.qpos.copy(), data.qvel.copy()])]
    for _ in range(RUNS - 1):
        _, d, _ = run_once()
        states.append(np.concatenate([d.qpos.copy(), d.qvel.copy()]))
    diffs = [float(np.max(np.abs(states[0] - s))) for s in states[1:]]
    check(f"determinism ({RUNS} fresh runs vs run 1)", all(d <= TOL for d in diffs),
          "max |diff| per run: " + ", ".join(f"{d:.3e}" for d in diffs) + f" (tol {TOL:.0e})")
    emit("final qpos: " + np.array2string(data.qpos, precision=6))

    verdict = "PASS" if not failures else f"FAIL ({len(failures)} check(s) failed)"
    emit(f"GATE 1 CHECK: {verdict}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    emit(f"output written to {OUT.relative_to(ROOT)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
