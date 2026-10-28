"""Guarded-stepping tests (Oct 28 - red-cell fix).

Astra's fault injection showed a raw mj_step loop can report PASS
after MuJoCo warned and auto-reset on a NaN. step_checked is the fix;
these tests prove it detects that failure and passes clean runs, and
that the loader enforces the frozen finger-pad count instead of
silently skipping a missing finger.
"""
import numpy as np
import pytest

from simforge.sim.cell import EXPECTED_PAD_GEOMS, load_cell, reset_home, step_checked

pytestmark = pytest.mark.e2e


def test_step_checked_clean_run_returns_full_time():
    model, data, _ = load_cell()
    reset_home(model, data)
    elapsed = step_checked(model, data, 200)
    assert abs(elapsed - 200 * float(model.opt.timestep)) < 1e-6


def test_step_checked_detects_injected_nan():
    model, data, _ = load_cell()
    reset_home(model, data)
    data.qvel[0] = np.nan  # the red cell's fault injection
    with pytest.raises(RuntimeError):
        step_checked(model, data, 10)


def test_loader_enforces_frozen_pad_count():
    model, _, pad_geoms = load_cell()
    assert len(pad_geoms) == EXPECTED_PAD_GEOMS == 16
    assert all(int(model.geom_condim[g]) == 4 for g in pad_geoms)
