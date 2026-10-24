# Hackathon submission — asset drafts (prepared Oct 24, 2026; finalize vs Official Rules after Oct 26)

Track: **Indie** — Theme: **Push the Frontier** (locked Oct 24, Red Cell).
Real deadline: **Nov 3 EOD** complete; draft submitted Nov 2 if the portal allows edits.
Disclosure line (locked Oct 24): prototype mechanics + grasp results are public;
interview findings, segment economics, H1 evidence detail, and pricing thinking
stay OUT of the submission, demo narration, and Discord. Repo private unless
the Official Rules require otherwise.

## Project description (draft)
SimForge tests whether a small manufacturer can know — before spending on a
robot or an integrator — whether a robot can actually handle their part.
It pairs a reproducible MuJoCo simulation cell (Franka Panda, frozen physics,
seeded perturbations) with Muse Spark (Meta Model API) as the in-app planner:
the model proposes a handling plan, a human approves it, the sim executes it,
and every run is scored against pre-registered pass/fail metrics (a grasp
counts only if the part lifts, holds without slip, and lands in the target
zone across 20 perturbed attempts). Built solo in eight days as a discovery
prototype: the simulation proves the technical loop; the market question
stays open and is being tested separately through operator interviews.

## Architecture note (draft)
MuJoCo 3.15.0 (pinned) physics cell -> mink differential IK control ->
scenario evaluator (seeded perturbations, machine-readable results) ->
model adapter (OpenAI-compatible; Meta Model API primary, mock mode for
offline work; API vs hosted open-weight is a config swap) -> plan schema
(4 fields) with syntax + semantic validation -> human approval gate ->
execution + audit log -> offline-rendered demo from logged trajectories.

## Demo outline (narrated screen capture, <=3 min, recorded Nov 1-2)
1. The problem in one line (small shop, one part, one expensive guess).
2. Live loop: scene state -> model proposes plan -> human approves -> grasp.
3. The battery: 20 perturbed attempts, results table, failures shown honestly.
4. The rejection: a bad plan refused, audit log entry visible.
5. Close: what this proves (technical loop) and what it doesn't (market).
