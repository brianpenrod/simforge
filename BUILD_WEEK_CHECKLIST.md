# Build Week Checklist — Oct 27–Nov 3, 2026

Submission deadline: **Wed Nov 4, 9:00 PM EST** (DST ends Nov 1 — post-change clocks). **Real deadline: complete submission by Tue Nov 3 EOD** (Red Cell lock, Oct 24); draft submitted Mon Nov 2 if the portal allows edits; Nov 4 is a phone verification glance only.

## Before build week (weekend Oct 24–25 + Mon Oct 26 evening)
- [ ] Weekend smoke test run (smoke_test.py): MuJoCo 3.15 pin, determinism, API key, ONE live adapter call; confirm Standard (non-training) mode in API + Muse Code
- [ ] GitHub repo created (private), full pinned requirements, clean-venv clone passes determinism check
- [ ] Panda grasp pre-tuned: ONE successful lift working before Gate 1 (Menagerie Panda + mink spike)
- [ ] VR&E paperwork inventoried and finished; Nous cancel finished
- [ ] Mon Oct 26 evening (60–90 min, non-negotiable): accept Official Rules, read eligibility vs own facts, map submission portal fields, secure Discord access, watch kickoff replay

## Tue Oct 27 — Gate 1: Freeze the scene
- [ ] Minimal cell per scene/SCENE_SPEC.md committed (table + Panda + box part + target zone) with friction config pinned
- [ ] Assets pinned; seeds manifest recorded in `scene/`
- [ ] Scene loads and steps deterministically from a clean checkout
- Note: VR&E paperwork due today; keep the day light. Pitch + kickoff were Oct 26.

## Wed–Thu Oct 28–29 — Gate 2: Repeatable grasp (highest priority)
- [ ] Grasp routine implemented against the frozen scene
- [ ] Grasp success measured by the Gate 2 metrics across repeated seeded runs
- [ ] If not repeatable by end of Thu: cut scope elsewhere, NOT here

## Fri Oct 30 — Gate 3: Plan + outcome evaluator
- [ ] Structured scenario definitions in `scenarios/`
- [ ] Evaluator runs the suite and writes recorded outputs to `results/`
- Note: Muse weekly limit resets 6:07 PM today.

## Sat–Sun Oct 31–Nov 1 — Gate 4: In-app model
- [ ] Demo video recorded THIS weekend from logged trajectories (offline render, narrated) — Nov 3 is re-record-the-ending only
- [ ] `model_adapter.py` wired to Meta Model API (Muse Spark) via .env config
- [ ] Vision and/or task-planning call producing a structured plan for the scene
- [ ] Adapter swap test: point config at a placeholder endpoint without code changes
- [ ] Stretch ONLY if Gates 1–3 are solid: SAM 3.1 segmentation in-scene
- Nous note: any Nous Research renewal lands Nov 1 — cancellation already handled by founder.

## Mon Nov 2 — Gate 5: Human-approval UX
- [ ] Loop live: plan proposed → human approves → action executes → outcome recorded
- [ ] Full scenario suite re-run through the approval loop

## Tue Nov 3 — Demo + packaging
- [ ] Demo ending re-recorded if needed (full video was recorded Nov 1–2); submission submitted in full TODAY
- [ ] Submission write-up drafted and checked against hackathon rules
- [ ] Repo clean, README accurate, results committed
- Note: VA doctor appt 9:30 AM today. Nov 4 = Biltmore departure; nothing left for Nov 4 except submit.
