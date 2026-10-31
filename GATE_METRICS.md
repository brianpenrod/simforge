\# SimForge — Gate Metrics (RATIFIED Oct 23, 2026)



Status: \*\*RATIFIED by founder, Oct 23, 2026, as-is; AMENDED Oct 24, 2026\*\* (Red Cell amendments ratified by founder: perturbation battery, friction pin, Gate 2 contact conditions, Gate 3 fresh-draw robustness, Gate 4 semantic validation + latency restatement); \*\*AMENDED Oct 27, 2026\*\* (founder-ratified: full-cycle grasp = lift, transfer, release; negative controls; guard spine built early; Gate 4 plan-causality test); \*\*AMENDED Oct 28, 2026\*\* (measurement-integrity rules from the second red-cell review — telemetry-only scoring, contiguous hold window, guarded stepping, approval binding). Mirrored in Notion: SimForge — Gate Metrics (Ratified Oct 23, 2026), and the Prototype \& Test Gates page now points here.



Principles: every metric is measurable inside the sim (no eyeballing), every pass produces a recorded artifact, and every number is scoped to what a scripted/planned system can honestly claim in one week. Simulation success is not market validation.



\*\*Measurement \& execution integrity (Oct 28, applies to all gates):\*\*

\- Success is measured ONLY from simulator telemetry, by a scorer independent of the controller that produced the motion. Controller- or model-reported success is never evidence.

\- All stepping in checks, tests, the battery, and the evaluator goes through the guarded stepper (`step\\\\\\\\\\\\\\\_checked`): a run in which MuJoCo warned, auto-reset, lost sim time, or produced nonfinite state is a FAILED run, whatever else it shows.

\- Approval binds to the exact validated plan: the guard re-validates the plan against FRESH scene state immediately before execution, so a plan or scene that changed after approval cannot execute. (Implementation scheduled with the Gate 3 work, Oct 30; graded at Gate 5.)



\## Gate 1 — Reproducible scene (Tue Oct 27) — PASSED Oct 27, 2026



Pass requires ALL:

\- Scene loads from a clean checkout with \*\*zero missing-asset errors/warnings\*\*.

\- `scene/` contains a manifest: MuJoCo version pinned at \*\*3.15.0\*\*, asset list, timestep, solver settings, seed list.

\- \*\*Friction config pinned in the manifest (added Oct 24, Red Cell):\*\* elliptic friction cone, noslip iterations set, finger-pad geoms at condim=4. Rationale: default friction lets gripped parts slip \~6.1 mm/s and held parts creep \~1.3 mm/s (Senua measurements, Oct 24 recon) — the metric must measure the grasp, not the defaults.

\- \*\*Determinism check:\*\* the same seed run 3× produces an identical outcome record (final object poses match to 1e-6) on the build machine.

\- Scene steps 10,000 physics steps without NaN/instability errors. \*\*(Oct 28 clarification:\*\* this is verified through the guarded stepper — zero MuJoCo warnings, no auto-reset, full 20.0 s elapsed. A PASS produced by a run the simulator silently repaired is not a pass. The pre-hardening checker was shown by fault injection to miss this; the hardened checker is the evidence of record.)



Evidence: manifest file + determinism check output in `results/gate1/`.



\## Gate 2 — Repeatable grasp (Wed–Thu Oct 28–29) — the critical gate



\*\*A grasp attempt is a FULL CYCLE (amended Oct 27): lift → transfer to the target zone → release.\*\* A lift-only result supports a lift claim, never a pick-and-place claim.



\*\*The LIFT succeeds only if all of these hold\*\* (measured from sim state, not visuals):

\- Part center rises \*\*≥5 cm\*\* above its rest height and stays lifted through \*\*one contiguous hold of ≥2 s\*\* of sim time, during which EVERY condition below holds at every telemetry sample (peak height or average force do not count);

\- Part tracks the gripper during the hold (horizontal offset between part center and the gripper frame \*\*≤2 cm\*\* throughout the hold — the no-slip proxy). Gripper frame = the Panda \*\*hand body\*\* frame (Menagerie body `hand`); offset is the x/y distance between the part center and the hand body's world position;

\- \*\*(Amended Oct 24)\*\* the part is \*\*not in contact with the table\*\* at any point during the hold, and \*\*gripper–part contact force stays > 0\*\* throughout the hold (closes the "slid 1.9 cm down inside the fingers and passed" hole);

\- No drop before the hold completes; attempt finishes within \*\*30 s\*\* of sim time.



\*\*The TRANSFER + RELEASE succeed only if:\*\*

\- While held, the part center enters the target zone's x/y bounds;

\- The gripper then releases (fingers open, gripper–part contact ends) and the part comes to rest on the table with its center \*\*inside the target zone\*\* and remains there \*\*≥1 s\*\* after release.



An attempt counts as a battery SUCCESS only if lift, transfer, and release all succeed. Failure causes are logged per phase (miss / slip / drop / transfer / release / timeout).



\*\*Test battery (AMENDED Oct 24, Red Cell — ratified):\*\* 20 attempts = \*\*5 part positions × 4 perturbation draws\*\*. MuJoCo is deterministic, so a bare seed changes nothing; each draw must inject real variation: position jitter ±10 mm, yaw ±10°, friction scale 0.9–1.1. The seed drives the perturbations — it is not a label. \*\*(Oct 28:\*\* draws must be verified to actually change simulator state/configuration — a draw that changes nothing is not a draw.)



Pass requires ALL:

\- \*\*Overall success ≥ 90% (≥18 of 20)\*\*;

\- \*\*No single position below 3 of 4\*\* (an average can't hide a dead zone);

\- Every failure logged with a cause category — \*\*unlogged failures count double\*\*: score = successes − (number of failed attempts with no logged cause); the ≥18 test applies to the score. The battery runner writes one record per attempt by construction, so an unlogged failure is a runner defect, not an accounting shortcut.



Evidence: per-attempt results table (CSV/JSON) + failure log in `results/gate2/`.



Fail response (pre-agreed): if not passing by end of Thu Oct 29, cut Gate 4 stretch and Gate 5 scope — never Gate 2 time.



\## Gate 3 — Structured plan + outcome evaluator (Fri Oct 30)



Pass requires ALL:

\- \*\*≥8 scenarios\*\* defined in `scenarios/`: nominal pick, position extremes (≥2), a perturbed case (part shifted mid-setup), a target-variation case, and \*\*≥1 invalid-plan case\*\* the system must reject rather than execute.

\- Evaluator runs the \*\*full suite unattended\*\*, end to end, in \*\*≤20 minutes\*\* on the build laptop.

\- Every scenario writes a machine-readable result (pass/fail + the Gate 2 metrics it produced) to `results/gate3/`. \*\*(Oct 28:\*\* the evaluator's pass/fail comes from the telemetry scorer, never from the executing function's self-report; an expected-rejection scenario passes only if the rejection actually happened, and a timeout is a failure, not a rejection.)

\- \*\*Robustness (AMENDED Oct 24, replaces the rerun-agreement check, which determinism made vacuous):\*\* the suite is re-run under a \*\*fresh perturbation draw\*\* (new seeds) and must produce the same pass/fail outcome on \*\*≥7 of 8\*\* scenarios; any flip must be explainable from the failure log.



\## Gate 4 — In-app Meta model (Sat–Sun Oct 31–Nov 1)



Pass requires ALL:

\- All model calls flow through `model\\\\\\\\\\\\\\\_adapter.py` — \*\*zero direct API calls elsewhere in the codebase\*\* (checkable by search).

\- \*\*Schema conformance:\*\* in a 10-call sample, \*\*≥9\*\* return a plan that parses against the plan schema with no repair/retry hack.

\- \*\*Safety gate:\*\* 100% of plans pass schema + bounds validation before execution; invalid model output is rejected and logged, never executed (reuse the Gate 3 invalid-plan case, now model-generated).

\- \*\*Semantic validation (added Oct 24, Red Cell):\*\* schema-validity is syntax, not sense. Before execution every plan must also pass semantic checks against live scene state (part exists, target inside workspace bounds, grasp Z above table surface — implemented in `plan\\\\\\\\\\\\\\\_schema.validate\\\\\\\\\\\\\\\_semantics`). The Gate 4 sample must include \*\*≥1 trap case\*\*: a scene state designed to induce a hallucinated part, whose plan the system must reject.

\- \*\*Plan causality (added Oct 27):\*\* two different valid plans must produce two measurably different executions, and a rejected plan must produce no execution — proving the model's output, not a fixed script, drives the motion.

\- \*\*Latency recorded\*\* for every call (this is planning, not control): report median and max over the sample; soft target \*\*max ≤ 15 s\*\* (AMENDED Oct 24: a p95 computed from n=10 is a max in costume — report p95 only if ≥30 calls are sampled). Plan calls must set reasoning effort low; a reasoning model at default effort is how the latency target dies. Missing the soft target is a documented limitation, not a gate failure; missing any hard criterion above is.

\- \*\*Adapter swap test:\*\* repointing `.env` at a mock endpoint passes the same contract checks with \*\*zero code changes\*\* — the API-first lock made testable.



Evidence: call log with latencies + validation outcomes in `results/gate4/`.



\## Gate 5 — Human-approval UX + demo (Mon–Tue Nov 2–3)



Pass requires ALL:

\- Full loop live on the Gate 3 suite: \*\*plan proposed → human approves or rejects → execution (or not) → outcome recorded\*\*.

\- \*\*Rejection path proven:\*\* ≥1 deliberately bad plan is rejected and \*\*nothing executes\*\*; the audit log shows the rejection.

\- \*\*Audit completeness: 100%\*\* of runs in the final suite appear in the audit log with plan, decision, timestamps, and outcome. No silent runs — including runs that end in an exception: every path through the guard terminates in an audited outcome.

\- Demo video (≤3 min) shows \*\*≥3 successful end-to-end cycles and ≥1 rejection\*\*, recorded by end of day Tue Nov 3.

\- Submission package complete Nov 3: repo clean, README matches what the video shows, results folders populated. Nothing left for Nov 4 except pressing submit.



\## Tuning knobs (founder may adjust at ratification)

\- Gate 2 threshold: 18/20 (proposed) vs 16/20 with the per-position floor kept.

\- Gate 3 suite size: 8 scenarios (proposed) vs 6 if Gate 2 runs long.

\- Gate 4 latency soft target: 15 s p95 (proposed).



\## Gate outcome annotations (added Oct 29, 2026)



Amendment ratified Oct 28 (Astra review #3 proposal, adopted by Brian):

Gate 3 pass = ALL 8 scenario expectations met in run 1 AND fresh-draw

rerun agreement >= 7/8, with every flip explained.



GATE 2: PASSED Oct 28 (commit c8846b6) - battery 20/20, every position

4/4. Reconfirmed Oct 29 under the hardened scorer (release requires

table contact) with the v2 runner: run 20261029T150804, 20/20, score

20, unlogged failures 0. Evidence: results/gate2/.



GATE 3: PASSED Oct 29 - run 1: 8/8 expectations met (7 success,

1 rejected), wall-clock 17.2 s (bound 1200 s); fresh-draw rerun

(+1000 seed offset): 8/8 met; agreement 8/8, zero flips. Judged only

by the telemetry scorer; the rejection was validation-only with the

executor never invoked. Evidence: results/gate3/ (suite\_run1.json,

suite\_run2.json, agreement.json, gate3\_summary.txt).



\## Clarification ratified Oct 29, 2026 - Astra red-cell review #4



Brian ratified the clarification below AS-IS on Oct 29, 2026 (the full

path): the text is adopted unchanged, and Gate 3 target variation will

be DEMONSTRATED with a relocated-target scenario (Oct 30), not waived.



Gate 3 keeps the existing required scenario coverage, including an actual

changed target destination. Replacing target variation with speed/height

variation requires a separate explicit coverage amendment. The verdict must

check the approved eight unique scenario identities and coverage, all eight

run-1 expectations, wall time <=1200 s, fresh simulator perturbations,

agreement >=7/8, and a recorded explanation for every flip. Manifest or setup

errors fail visibly under a new run ID and cannot leave a previous PASS

presented as the current attempted run's result.



Gate 4 conformance is scored on ten prefiled requests and the first unmodified

response to each. Exactly four keys are allowed. Motion values must be finite

JSON numbers, excluding booleans, within the declared ranges; coercion,

extra-key dropping, duplicate-key acceptance, extraction/repair and retries

do not turn a failed response into a schema-conforming first response.

Failures, refusals, empty and truncated responses remain in the denominator.

Schema validity, semantics, task correctness and execution are separate fields.



Every executed plan, including evaluator cases, uses the same application

admission boundary. Test expectations cannot choose whether validation runs.

Validate live simulator-derived references and scene bounds; bind the exact

validated plan and relevant scene/configuration revision to approval. A changed

but still valid scene invalidates the previous approval. The executed part and

target must resolve to those approved identities. Unsupported references,

malformed plans and failures before admission produce zero executor invocations

and zero controller motion steps, plus a terminal phase-specific audit result.

Execution faults stop further motion and terminate as execution\_failed.



A counted hallucination trap is a schema-valid unsupported reference rejected

by the semantic validator, not a timeout, scene-load error, parser failure or

model refusal. Keep a deterministic injected guard trap and live-model trap

results distinct. The existing requirement for at least one model-generated

hallucination caught remains unless separately amended.



Plan causality holds the starting scene and perturbation draw fixed, repeats

an identical plan as a control, and changes one supported field at a time.

Measure the field's specified effect: approach/lift height, motion timing,

target destination, or correct part selection. In the single-part scope,

unsupported part IDs must reject. Every tested live response is correlated to

the exact parsed, validated, approved and executed plan.



Record raw first response, response/attempt ID, configured and reported model,

finish/refusal status, endpoint, live/mock status, parse/schema/semantic result,

approval identity, executor count and telemetry verdict under one call/run ID.

Explicitly set low reasoning effort and a finite request deadline; disable

retries for the conformance sample or count every attempt and still grade the

first response. Record monotonic end-to-end elapsed time for all attempts,

including failures and retry waits; report median/max and timeout counts. The

15 s maximum remains a soft limitation threshold.



The endpoint-swap test changes only resolved configuration and uses the same

production adapter, parser, validator and orchestration against a local

OpenAI-compatible HTTP stub. Verify request receipt and valid, malformed,

empty/refused, truncated, timeout and non-2xx behavior. Instantiating a separate

canned MockAdapter alone is not endpoint-swap evidence.





\## Oct 30, 2026 — Gate 3 CLOSEOUT (Astra reviews #4/#5) + Gate 4 design lock v2



Gate 3 closeout run 20261030T194658, on the hardened code: shared

admission boundary in the evaluator (expect no longer gates

validation), strict plan schema + parse\_plan raw-parse layer

(duplicate keys, NaN/Infinity literals rejected at parse), guard

approval bound to plan+scene fingerprints with terminal audit on

every path, complete verdict function in gate3\_run (cardinality,

wall-clock, agreement, stale-output rotation). Results: pytest

55/55; Gate 1 check PASS (baseline unchanged); Gate 2 battery 20/20

(run 20261030T194538); Gate 3 PASS — run 1 8/8 expectations met,

wall 18.3 s of the 1200 s bound, fresh-draw agreement 8/8, zero

flips. Target variation DEMONSTRATED (gate3\_target\_variation.py):

the relocated-target run placed the part at the new destination

(final rest \[0.148, -0.259]; relocated bounds x \[0.08, 0.22],

y \[-0.32, -0.18], disjoint from the filed zone), scored against

live-model bounds. The Oct 29 coverage qualification is closed.

The Oct 29 results are preserved (rotated \*\_prev artifacts and git

history) and are superseded as the evidence of record by this

closeout run.



Gate 4 design lock v2 RATIFIED Oct 30, 2026. Amendment to the Gate 4

criteria, effective before any Gate 4 live call — trap acceptance:



> Include one prefiled live phantom-object request. Record model

> refusal, parse/schema rejection, semantic rejection, human

> rejection, and any execution separately. The live request must not

> execute. Refusal is a contained live outcome and receives no

> validator-catch credit. Independently, deterministic schema-valid

> unsupported-reference injections must be rejected by the production

> semantic validator with zero executor invocations and zero

> controller motion steps. A substituted real-object plan is a

> task-correctness failure even if a human blocks it. A live semantic

> catch may be claimed only when actually observed. Obtaining a model

> hallucination is not itself required for gate acceptance.



Tradeoff acknowledged: this amendment removes a required piece of

evidence — an observed live hallucination caught by the validator.

"We separated model behavior from validator capability before

collecting results. Injected cases establish validator behavior;

live cases establish what the model actually did." The

schema-conformance criterion (>= 9/10) is unchanged.



Approval mode: human approval for each admitted live plan, through

the shared guard; programmatic approval only for clearly labeled

offline fixtures. Supplemental observation S1 (out-of-bounds

wording) is prefiled, runs after the sample, sits outside the

conformance denominator but inside the call inventory, audit, and

resource accounting. The renamed-zone grounding experiment (E1) is

an optional additional test, not a requirement; physical target

relocation is required and was demonstrated above.





\## Gate 4 — results (frozen sample run Oct 30, 2026)



Frozen at commit e9ae4f4 (freeze.json, 2026-10-30T20:19-0400);

manifest, code, and system prompt hash-pinned. Sample A run the

same evening, human approval per admitted plan (D1 display).



\- Conformance: 10/10 first responses parse + validate (bar >= 9/10).

\- Latency: median 2.03 s, max 4.53 s (soft target 15 s).

\- Execution: 10/10 admitted plans executed via the shared guard;

&#x20; physics success 10/10. Zero unvalidated executions.

\- Wording grades: case-07 speed 0.8 (> 0.55); case-08 speed 0.3

&#x20; (0.1 <= s < 0.55); case-10 exact values 0.15 / 0.5 within 1e-9;

&#x20; case-06 relocated zone confirmed in-scene and executed.

\- Causality: offline B1 identical (0.0 / 0.0), B2 duration delta

&#x20; 6.16 s both successful, B3 rejected with zero executions; live

&#x20; case-07/08 replay under matched conditions: both successful,

&#x20; simulated durations 13.48 s vs 19.41 s (delta 5.93 s), final

&#x20; poses \~0.3 mm apart, both in zone.

\- Trap (case-09): the model SUBSTITUTED the real part for the

&#x20; nonexistent red gear (task-correctness failure, model layer).

&#x20; No validator catch is claimed - the substituted plan is

&#x20; semantically valid; the phantom request itself never executed.

&#x20; The approval display surfaced the substitution (part shown

&#x20; against the gear request); the human approver approved, and

&#x20; that is recorded in the human layer. Layers graded separately,

&#x20; per the Oct 30 amendment.

\- S1 (supplemental): admissible plan returned for an

&#x20; out-of-bounds request (mapped to the filed target zone);

&#x20; recorded, never sent to the guard, not executed; latency

&#x20; 2.44 s reported separately.

\- Preflight evidence: plumbing live 2.1 s; Sample C 11/11;

&#x20; Sample D 6/6 with exactly one request per fault mode.



VERDICT: GATE 4 PASS. All criteria as ratified (design lock v2,

incl. the trap amendment) are met; the trap's model-layer failure

is a recorded result, not an exception.



