# Gate 1 Scene Spec — frozen definition (Red Cell revision, Oct 24, 2026)

The frozen scene is a MINIMAL CELL, not a machine shop diorama:
table + Franka Panda + one box part + one target zone. Shop dressing is
post-Gate-5 cosmetics only.

- Robot: MuJoCo Menagerie `franka_emika_panda` (arrives with parallel
  gripper; UR5e rejected — ships gripperless, merging a Robotiq 2F85 in
  MJCF is Gate-1-burning work). Clone menagerie at Gate 1; record commit.
- Control: mink 1.3.0 differential IK, Cartesian targets + timed gripper
  waypoints. No hand-rolled IK.
- Part: plain box (~5 cm). No cylinders or "machine part" geometry — the
  battery must test the grasp, not part geometry.
- Friction config (PINNED, from Senua findings via Oct 24 recon + Red Cell):
  frictioncone="elliptic", noslip_iterations set (start 10), finger-pad
  geoms condim="4" (torsional friction — MuJoCo docs: substantially
  improves grasp stability). Record all values in the Gate 1 manifest.
- Perturbation battery (ratified amendment): seed drives position jitter
  ±10 mm, yaw ±10°, friction scale 0.9–1.1. Five nominal positions x four
  perturbation draws = the 20-attempt Gate 2 battery.
- Determinism scope: same MuJoCo version AND same architecture only.
  The submission must not claim cross-machine reproducibility.
