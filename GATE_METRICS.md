# SimForge — Gate Metrics (RATIFIED Oct 23, 2026)

Status: **RATIFIED by founder, Oct 23, 2026, as-is; AMENDED Oct 24, 2026** (Red Cell amendments ratified by founder: perturbation battery, friction pin, Gate 2 contact conditions, Gate 3 fresh-draw robustness, Gate 4 semantic validation + latency restatement). Mirrored in Notion: SimForge — Gate Metrics (Ratified Oct 23, 2026), and the Prototype & Test Gates page now points here.

Principles: every metric is measurable inside the sim (no eyeballing), every pass produces a recorded artifact, and every number is scoped to what a scripted/planned system can honestly claim in one week. Simulation success is not market validation.

## Gate 1 — Reproducible scene (Tue Oct 27)

Pass requires ALL:
- Scene loads from a clean checkout with **zero missing-asset errors/warnings**.
- `scene/` contains a manifest: MuJoCo version pinned at **3.15.0**, asset list, timestep, solver settings, seed list.
- **Friction config pinned in the manifest (added Oct 24, Red Cell):** elliptic friction cone, noslip iterations set, finger-pad geoms at condim=4. Rationale: default friction lets gripped parts slip ~6.1 mm/s and held parts creep ~1.3 mm/s (Senua measurements, Oct 24 recon) — the metric must measure the grasp, not the defaults.
- **Determinism check:** the same seed run 3× produces an identical outcome record (final object poses match to 1e-6) on the build machine.
- Scene steps 10,000 physics steps without NaN/instability errors.

Evidence: manifest file + determinism check output in `results/gate1/`.

## Gate 2 — Repeatable grasp (Wed–Thu Oct 28–29) — the critical gate

**A grasp attempt SUCCEEDS only if all of these hold** (measured from sim state, not visuals):
- Part center rises **≥5 cm** above its rest height and stays lifted **≥2 s** of sim time;
- Part tracks the gripper during the lift (horizontal offset between part and gripper frame **≤2 cm** throughout the hold — the no-slip proxy);
- **(Amended Oct 24)** the part is **not in contact with the table** at any point during the hold, and **gripper–part contact force stays > 0** throughout the hold (closes the "slid 1.9 cm down inside the fingers and passed" hole);
- No drop before the hold completes; attempt finishes within **30 s** of sim time.

**Test battery (AMENDED Oct 24, Red Cell — ratified):** 20 attempts = **5 part positions × 4 perturbation draws**. MuJoCo is deterministic, so a bare seed changes nothing; each draw must inject real variation: position jitter ±10 mm, yaw ±10°, friction scale 0.9–1.1. The seed drives the perturbations — it is not a label.

Pass requires ALL:
- **Overall success ≥ 90% (≥18 of 20)**;
- **No single position below 3 of 4** (an average can't hide a dead zone);
- Every failure logged with a cause category (miss / slip / drop / timeout) — unlogged failures count double against the pass.

Evidence: per-attempt results table (CSV/JSON) + failure log in `results/gate2/`.

Fail response (pre-agreed): if not passing by end of Thu Oct 29, cut Gate 4 stretch and Gate 5 scope — never Gate 2 time.

## Gate 3 — Structured plan + outcome evaluator (Fri Oct 30)

Pass requires ALL:
- **≥8 scenarios** defined in `scenarios/`: nominal pick, position extremes (≥2), a perturbed case (part shifted mid-setup), a target-variation case, and **≥1 invalid-plan case** the system must reject rather than execute.
- Evaluator runs the **full suite unattended**, end to end, in **≤20 minutes** on the build laptop.
- Every scenario writes a machine-readable result (pass/fail + the Gate 2 metrics it produced) to `results/gate3/`.
- **Robustness (AMENDED Oct 24, replaces the rerun-agreement check, which determinism made vacuous):** the suite is re-run under a **fresh perturbation draw** (new seeds) and must produce the same pass/fail outcome on **≥7 of 8** scenarios; any flip must be explainable from the failure log.

## Gate 4 — In-app Meta model (Sat–Sun Oct 31–Nov 1)

Pass requires ALL:
- All model calls flow through `model_adapter.py` — **zero direct API calls elsewhere in the codebase** (checkable by search).
- **Schema conformance:** in a 10-call sample, **≥9** return a plan that parses against the plan schema with no repair/retry hack.
- **Safety gate:** 100% of plans pass schema + bounds validation before execution; invalid model output is rejected and logged, never executed (reuse the Gate 3 invalid-plan case, now model-generated).
- **Semantic validation (added Oct 24, Red Cell):** schema-validity is syntax, not sense. Before execution every plan must also pass semantic checks against live scene state (part exists, target inside workspace bounds, grasp Z above table surface — implemented in `plan_schema.validate_semantics`). The Gate 4 sample must include **≥1 trap case**: a scene state designed to induce a hallucinated part, whose plan the system must reject.
- **Latency recorded** for every call (this is planning, not control): report median and max over the sample; soft target **max ≤ 15 s** (AMENDED Oct 24: a p95 computed from n=10 is a max in costume — report p95 only if ≥30 calls are sampled). Plan calls must set reasoning effort low; a reasoning model at default effort is how the latency target dies. Missing the soft target is a documented limitation, not a gate failure; missing any hard criterion above is.
- **Adapter swap test:** repointing `.env` at a mock endpoint passes the same contract checks with **zero code changes** — the API-first lock made testable.

Evidence: call log with latencies + validation outcomes in `results/gate4/`.

## Gate 5 — Human-approval UX + demo (Mon–Tue Nov 2–3)

Pass requires ALL:
- Full loop live on the Gate 3 suite: **plan proposed → human approves or rejects → execution (or not) → outcome recorded**.
- **Rejection path proven:** ≥1 deliberately bad plan is rejected and **nothing executes**; the audit log shows the rejection.
- **Audit completeness: 100%** of runs in the final suite appear in the audit log with plan, decision, timestamps, and outcome. No silent runs.
- Demo video (≤3 min) shows **≥3 successful end-to-end cycles and ≥1 rejection**, recorded by end of day Tue Nov 3.
- Submission package complete Nov 3: repo clean, README matches what the video shows, results folders populated. Nothing left for Nov 4 except pressing submit.

## Tuning knobs (founder may adjust at ratification)
- Gate 2 threshold: 18/20 (proposed) vs 16/20 with the per-position floor kept.
- Gate 3 suite size: 8 scenarios (proposed) vs 6 if Gate 2 runs long.
- Gate 4 latency soft target: 15 s p95 (proposed).
