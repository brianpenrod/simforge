# SimForge BUILD LOG

Purpose: delineate work built during the Meta Global AI Developer Hackathon
(building period Oct 27 - Nov 4, 2026) from pre-event work, per the
Participant Guide's "New work only" rule.

## Pre-event (before Oct 27, 2026) - NOT part of the judged build
- Repo scaffold committed Oct 25, 2026: plan schema + validators, scenario
  file format, Meta Model API adapter (OpenAI-compatible) with mock mode,
  smoke test, scene spec, gate metrics, build-week checklist.
- Oct 26, 2026: live API smoke test passed (SMOKE_OK); Phase 0 complete.

## Oct 27, 2026 - Gate 1: freeze the scene
- Cloned MuJoCo Menagerie into third_party/ (gitignored, NOT vendored);
  pinned commit f3b6013629c7b94f8ee93fd977b161fa8350f9bc.
- Authored scene/cell.xml: minimal cell - Franka Panda (Menagerie) on a
  table, one 5 cm box part (0.1 kg), one target zone, floor below.
- Finding: MuJoCo resolves an included model's meshdir relative to the
  ROOT MJCF folder, so the Panda meshes failed to load cross-folder.
  Fix: junction scene/assets -> Menagerie franka_emika_panda/assets
  (documented in scene/manifest.json). Third-party files unmodified.
- Physics pins enforced in the loader (gate1_check.py) and asserted on
  every run: elliptic friction cone, noslip_iterations=10, finger geoms
  condim=4.
- gate1_check.py: PASS - model loads (nq=16, nu=8, nkey=1), part rests at
  z=0.024892 m, 10,000 steps, determinism max |diff| = 0.0 across two
  fresh runs (tolerance 1e-6).
## Oct 27, 2026 - Gate 1 closeout (afternoon)
- Independent review (Astra) found four gaps vs the ratified Gate 1
  metrics; all verified against GATE_METRICS.md and fixed:
  - determinism now runs 3x per the ratified metric (was 2x); diffs 0.0, 0.0.
  - checker writes evidence to results/gate1/gate1_check_output.txt.
  - manifest now records the measured timestep (0.002), integrator
    (implicitfast), solver iterations (100) and tolerance (1e-8), the
    asset list, and the seed note (fixed home keyframe; no perturbation
    seeds at Gate 1).
  - scene/cell.xml: removed machine-specific absolute asset paths (dead
    config; the scene/assets junction is the documented mechanism).
- Loader refactored: src/simforge/sim/cell.py is the single load path
  (pins enforced); gate1_check.py imports it. All later code uses it too.
## Oct 27, 2026 - Test skeleton, CI, guard spine (afternoon)
- pytest suite live (pytest.ini + tests/): 12 plan-validator unit tests,
  2 negative controls, Gate 1 golden-baseline regression; 19 passed
  by end of day (incl. guard tests below).
  - NC-1: a no-op run cannot satisfy the Gate 2 lift criterion.
  - NC-2: friction measurably changes the physics (0.5 N push: part
    holds at friction 1.0, slides >5 cm at 0.02).
- Golden baseline recorded (tests/baselines/gate1_baseline.json) via
  make_gate1_baseline.py; re-blessing requires founder approval, git
  diff is the record.
- CI: .github/workflows/checks.yml runs on every push - clean Linux
  machine, requirements only, Menagerie at the pinned commit, assets
  linked per the manifest, gate1_check + full pytest. First run GREEN,
  including the Windows-recorded baseline reproduced on Linux within
  1e-6 (observation; the reproducibility claim stays scoped to the
  build machine per SCENE_SPEC).
- Guard spine built early per the Oct 27 amendments:
  src/simforge/guard.py (validate -> approve -> execute -> append-only
  JSONL audit), 4 contract tests, guard_demo.py driven by hand both
  ways - approval executed, rejection executed nothing, both audited.
