# DRAFT amendment — Gate 1/2 friction configuration (NOT ratified, NOT in Notion)

Status: prepared Sat Oct 24, 2026 in response to the Oct 24 daily recon flag.
Source of the flag: Senua AI MuJoCo accuracy deep dive (Oct 18, vendor-published, public GitHub studies) as reported in the Oct 24 recon — MuJoCo *default* friction let a gripped cube slip at 6.1 mm/s and a held cube creep at 1.3 mm/s; elliptic-cone + noslip configuration held at zero up to a 0.95 friction limit.
Brian's decision is still required. If he says go, apply the two edits below to `GATE_METRICS.md` and mirror them in Notion; nothing here changes until then.

## Edit 1 — Gate 1 manifest (add one bullet)
> - **Friction configuration pinned in the manifest:** friction cone set to elliptic and the noslip solver option enabled; per-contact friction coefficients for gripper/part contacts recorded in the asset list. Running on MuJoCo default friction does **not** satisfy Gate 1. (Implementation attribute names to be confirmed against the MuJoCo 3.15.0 docs during Gate 1 setup.)

Rationale: Gate 1 is "fixed, reproducible base" — the friction model is part of that base, and the ratified Gate 2 no-slip proxy (part within 2 cm of the gripper through the hold) is only meaningful if the sim isn't injecting its own drift.

## Edit 2 — Gate 2 evidence (add one sentence to the Evidence line)
> Each successful attempt also records a **hold-at-rest creep reading**: the part's displacement relative to the gripper frame during the final 1 s of the hold, reported in mm/s in the per-attempt results table (max across the battery reported in the summary). Evidence-only in this amendment — no pass/fail threshold is set; Brian may set one after the first Gate 2 battery if the readings warrant it.

Rationale: keeps the ratified pass standard (≥18/20, per-position floor 3/4) untouched while making creep visible instead of letting the 2 cm proxy absorb it silently.

## What this does NOT change
- No change to Gate 2 thresholds, the test battery, or the pre-agreed fail response.
- No change to the MuJoCo 3.15.0 pin or any other locked decision.
- Effort: one-time manifest/config work inside Gate 1 (Tue Oct 27), which is already the freeze-the-scene day.
