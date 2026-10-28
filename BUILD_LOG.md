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
## Oct 28, 2026 - Gate 2 day 1: measurement hardening, metrics amendments, telemetry scorer, first grasp
- Task 0 (red-cell fixes from the Oct 27 Astra review #2):
  src/simforge/sim/cell.py is now loader + guarded stepper.
  step_checked raises on MuJoCo warnings, auto-resets (time going
  backwards), lost sim time, or nonfinite state - the NaN fault
  injection that passed the old checker is now a failing pytest
  (tests/test_step_guard.py). Loader hard-fails on a missing finger
  body or a pad-geom count != 16 (was: silent skip). NC-2 displacement
  bounds are absolute. gate1_check reports clean stepping explicitly
  (warnings=0 resets=0 elapsed=20.000s); all Gate 1 numbers unchanged.
  Suite: 22 passed; CI green.
- Task 1: the Oct 27-28 amendments are committed into GATE_METRICS.md
  itself (they previously lived only in the runbook/handoff - the
  drift Astra flagged): full-cycle Gate 2 (lift -> transfer ->
  release) with placement acceptance, contiguous-window hold, hand-
  body measurement frame, unlogged-failure double-count arithmetic,
  telemetry-only scoring, guarded stepping, approval binding
  (implementation scheduled Oct 30, graded at Gate 5).
- Task 2: telemetry scorer (src/simforge/scoring.py) built BEFORE the
  controller, per the standing rule that success is measured from
  simulator telemetry by a scorer the controller cannot influence.
  evaluate_attempt is a pure function of the trace: contiguous >= 2 s
  hold window (lift >= 5 cm, tracking <= 2 cm vs the hand body, zero
  table contact, grip force > 0 at every sample), transfer = held
  part center inside the target-zone bounds, release = part resting
  in the zone >= 1 s after the grip ends. Failure causes per phase
  (miss/slip/drop/transfer/release; the runner owns "timeout").
  7 synthetic-trace unit tests + the NC-1 closure: the production
  scorer fed real telemetry from a no-op run of the actual cell
  rejects it as a miss. One API bug found by that e2e test and fixed
  (data.ncon, not data.ncontact). Suite: 30 passed; CI green.
- Task 3: grasp controller (src/simforge/grasp.py) - mink IK (daqp
  solver; quadprog not installed) waypoint execution driven by the
  plan's own fields; grasp height measured from the finger-pad span
  at the home keyframe (drop_center 0.092 m), gripper semantics
  measured by probe_model.py (ctrl 255 = open, 0 = closed).
  FIRST INSTRUMENTED ATTEMPT: full cycle SUCCESS under the telemetry
  scorer - rise 0.145 m, contiguous hold 4.68 s, hold grip force min
  2.46 N, max tracking offset 2.9 mm, part released resting inside
  the target zone at (0.444, 0.278), 14.8 s of the 30 s budget, zero
  simulator warnings. Gate 2's remaining criterion is the 20-attempt
  battery (5 positions x 4 perturbation draws), scheduled Oct 29.
- Gate 2 battery (same day): gate2_battery.py - 20 attempts =
  5 positions x 4 seeded perturbation draws (position jitter
  +-10 mm, yaw +-10 deg, friction scale 0.9-1.1 applied to the
  part, table, and finger-pad surfaces; each draw asserted to
  have changed simulator state before stepping). Every attempt
  judged only by the telemetry scorer. RESULT: 20/20 successes,
  score 20 (bar: >= 18), every position 4/4 (bar: >= 3/4),
  contiguous holds 4.2-5.7 s against the 2 s criterion, zero
  unlogged failures. GATE 2 PASSED Oct 28, 2026 - one day ahead
  of the Oct 29 deadline. Evidence: results/gate2/
  battery_results.json, results/gate2/battery_summary.txt.

