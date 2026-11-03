\# SimForge



Team: Dr Penrod \& Mayordomo — Mayordomo is Brian's Muse personal

agent and build partner on this project (Spanish for a chief

steward — the one who runs the house).



\*\*Repeatable, measured tests of robot part-handling tasks in

simulation.\*\*



SimForge tests whether a robot cell can handle a part-handling

task before anyone commits to hardware. An operator's request

becomes a structured plan; a strict admission boundary validates

the plan against the live scene; a human approves; the plan

executes in MuJoCo; and a separate evaluator applies fixed scoring

rules to simulator telemetry — the planner and controller do not

assign the verdict. Rejected plans produce no execution, and the

audit trail shows why.



\- \*\*Planner (runtime, Gate 4):\*\* Muse Spark via the Meta Model

&#x20; API, behind an OpenAI-compatible adapter.

\- \*\*Simulation/execution:\*\* MuJoCo 3.15.0 + mink 1.3.0, Franka

&#x20; Panda in a minimal cell (one 5 cm part, one target zone).

\- \*\*Controls:\*\* strict plan schema and admission boundary,

&#x20; approval-bound fingerprinting, human approval before execution,

&#x20; telemetry-only scoring, append-only audit records.



\## The demonstration (video, 2:57)



The demo deliberately combines separately recorded sources, each

labeled on screen:



\- A \*\*recorded Meta API example\*\* (Gate 4 case-10): a real Muse

&#x20; Spark request and its returned plan, with recorded checks,

&#x20; approval, and execution.

\- A \*\*D4 terminal approval recording\*\*: the operator authorizing a

&#x20; filed plan (D4:DEMO-1).

\- \*\*D2 simulation replays\*\* of three filed-plan runs — the

&#x20; standard task, a relocated destination, a harder starting

&#x20; position — each with its recorded scorer result. Replays are

&#x20; re-executions of the recorded plans, verified faithful to the

&#x20; records (final-position and duration agreement).

\- A \*\*human rejection\*\* (D4:DEMO-4): the saved Gate 4 trap

&#x20; response — a plan substituting the real part for a requested

&#x20; red gear that does not exist — re-presented for a new human

&#x20; decision and rejected, with zero execution.



Simulation audio in the video is designed sound, disclosed on

screen as illustrative. Runs 1–3 use filed demo plans; no fresh

model call generated those motions.



\## Gate results



\- \*\*Gate 1 — determinism:\*\* repeat runs, 0.0 differences.

\- \*\*Gate 2 — grasp battery:\*\* 20/20.

\- \*\*Gate 3 — scenario robustness:\*\* 8/8 expected outcomes, zero

&#x20; flips on fresh draws; target variation demonstrated at a

&#x20; relocated zone.

\- \*\*Gate 4 — live model planning: NOT PASSED.\*\* Conformance

&#x20; 10/10; latency median 2,031.5 ms / max 4,532 ms; physics 10/10.

&#x20; The trap case failed: asked to move a nonexistent red gear, the

&#x20; model substituted the real part; the substituted plan was

&#x20; displayed, approved by the operator, and executed. The test

&#x20; exposed a substitution that proceeded to execution; independent

&#x20; review caught an incorrect verdict; the runtime did not stop

&#x20; it. Separate repair checks later passed (guarded-causality

&#x20; checks using an offline approval fixture; six stub-orchestration

&#x20; cases) — remediation evidence only; the verdict is unchanged.

\- \*\*Gate 5 — acceptance on a frozen candidate:\*\* candidate

&#x20; `8dacc16` (inventory digest `fe9ea672…`), frozen Nov 1, 2026.

&#x20; Probes 4/4; acceptance suite 11/11 expected paths (seven

&#x20; executed successes, two validation stops with zero executor

&#x20; calls, two human rejections with zero motion); independent

&#x20; verification PASS. Evidence in `results/gate5/`.



Full criteria, dated amendments, and build history:

`GATE\_METRICS.md` and `BUILD\_LOG.md`.



\## Pre-existing work



Work present before October 27 includes repository scaffolding,

the initial plan schema and validators, a Meta API adapter with

mock support, a stub scenario evaluator and perturbation helpers,

smoke tests, scene specifications, and gate documents. The

initial commit is dated October 24; the build log records a live

API smoke test on October 26. From October 27 onward, the work

added the working MuJoCo cell, grasp controller and telemetry

scoring, strengthened admission and approval controls, live

planning experiments, frozen acceptance evidence, and the

submission demonstration. The commit history distinguishes these

additions from the earlier foundations.



\## What this does not claim



No confirmed buyer, no paid pilot, no product-market fit.

SimForge is an exploratory discovery program; the business

hypothesis remains untested by interviews. Simulation results

are evidence about the simulated cell, not proof of physical

feasibility.



\## Layout



\- `src/simforge/` — runtime: scene, controller, evaluator,

&#x20; admission boundary, guard, audit, model adapter.

\- `results/` — recorded evidence, organized by gate.

\- `docs/` — submission materials.

\- Packaging note: the frozen candidate is `8dacc16`. Commits

&#x20; after the evidence commit `e31d8ab` are documentation and

&#x20; evidence packaging only; no frozen runtime file is changed.



