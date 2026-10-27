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
