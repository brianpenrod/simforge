# SimForge — Hackathon Build Project

Reproducible MuJoCo machine-shop scene where a simulated robot repeatedly grasps a part; Muse Spark (Meta Model API) does vision/task planning behind an adapter; a human approves each plan; scenario tests + a demo video prove it works.

**Event:** Meta Global AI Developer Hackathon, Oct 26–Nov 4, 2026. Submissions due Nov 4, 9:00 PM ET. Build effectively closes Nov 3 (Nov 4 = travel day).
**Full day-by-day plan:** `BUILD_WEEK_CHECKLIST.md` (source scope: `~/workspace/your_files/hackathon-simforge-build-week-scope.md`).

## Locked decisions (do not re-litigate mid-build)
- **Track/theme (locked Oct 24, Red Cell):** Indie track, "Push the Frontier." SimForge is formally the entry.
- **Real deadline (locked Oct 24):** complete submission by **Tue Nov 3 EOD**; draft submitted Nov 2 if the portal allows edits. Nov 4 is a phone verification glance only.
- **Disclosure line (locked Oct 24):** prototype mechanics + grasp results are public; interview findings, segment economics, H1 evidence, and pricing thinking stay out of the submission, demo, and Discord. Repo stays private unless the Official Rules require otherwise.
- **Robot/control (locked Oct 24):** Franka Panda (Menagerie, grasp-ready) + mink 1.3.0 differential IK. Box part only. Frozen scene = minimal cell (table + Panda + part + target zone) per `scene/SCENE_SPEC.md`.
- **Demo (locked Oct 24):** narrated screen capture, rendered offline from logged trajectories, recorded Nov 1–2.
- **Physics:** MuJoCo **3.15.0** pinned. No mid-build upgrade. Post-hackathon spike evaluates 3.17.0 (batch API).
- **In-app model (Gate 4):** API-first — hosted Meta Model API (Muse Spark) primary. Open-weight serving deferred to post-hackathon evaluation.
- **Adapter rule:** all model calls go through `src/simforge/model_adapter.py` (OpenAI-compatible interface). API vs hosted open-weight must stay a config swap, never a rewrite.
- **No hardware/infrastructure spend** without founder approval. Isaac Sim is cloud-only if ever (laptop RTX 4050 / 6 GB VRAM is below Isaac Sim's 16 GB minimum) — not part of this build.
- **Truth split:** this repo is the technical truth; Notion holds milestone evidence and links.

## Layout
- `src/simforge/` — package code (model adapter skeleton in place; scene/grasp/evaluator modules land per gate)
- `scene/` — Gate 1: frozen MJCF scene, assets, seeds manifest
- `scenarios/` — Gate 3: structured scenario definitions
- `results/` — Gate 3: recorded validation outputs

## Setup
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # then add your Meta Model API key
```

## Open decisions (founder)
1. Track: Indie (recommended in scope) vs Startup — not yet locked.
2. Gate 5 demo format: screen capture vs narrated walkthrough.
