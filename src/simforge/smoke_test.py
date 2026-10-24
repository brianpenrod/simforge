"""Weekend toolchain smoke test — run BEFORE build week (target: Oct 24-25).

Checks, in order:
  1. Python + mujoco installed and pinned at exactly 3.15.0 (locked Oct 23)
  2. MuJoCo can load, step, and deterministically reproduce a minimal model
  3. .env present with META_MODEL_API_KEY set (value is never printed)
  4. OPTIONAL (--live): one minimal chat call through ModelAdapter

Usage:
    python smoke_test.py            # offline checks only, no API spend
    python smoke_test.py --live     # also makes ONE small API call

Exit code 0 = all run checks passed. Any FAIL line names the fix.
"""
from __future__ import annotations

import sys

EXPECTED_MUJOCO = "3.15.0"
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    live = "--live" in sys.argv

    # 1. MuJoCo version pin
    try:
        import mujoco

        check(
            "MuJoCo version pin",
            mujoco.__version__ == EXPECTED_MUJOCO,
            f"found {mujoco.__version__}, locked pin is {EXPECTED_MUJOCO}"
            + ("" if mujoco.__version__ == EXPECTED_MUJOCO else " — fix: pip install mujoco==3.15.0"),
        )
    except ImportError:
        check("MuJoCo version pin", False, "mujoco not installed — fix: pip install -r requirements.txt")
        mujoco = None  # type: ignore

    # 2. Deterministic step test (Gate 1 determinism in miniature)
    if mujoco is not None:
        xml = """
        <mujoco><worldbody>
          <body name="part" pos="0 0 0.5"><freejoint/>
            <geom type="box" size="0.03 0.03 0.03" mass="0.1"/>
          </body>
        </worldbody></mujoco>"""
        try:
            outcomes = []
            for _ in range(3):
                m = mujoco.MjModel.from_xml_string(xml)
                d = mujoco.MjData(m)
                for _ in range(100):
                    mujoco.mj_step(m, d)
                outcomes.append(tuple(round(float(x), 9) for x in d.qpos))
            check(
                "MuJoCo determinism (same model, 3 runs)",
                outcomes[0] == outcomes[1] == outcomes[2],
                f"final qpos run1={outcomes[0]}",
            )
        except Exception as exc:  # noqa: BLE001
            check("MuJoCo determinism (same model, 3 runs)", False, str(exc))

    # 3. .env / API key presence (never print the value)
    import os
    from pathlib import Path

    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists() and not os.environ.get("META_MODEL_API_KEY"):
        for line in env_path.read_text().splitlines():
            if line.startswith("META_MODEL_API_KEY="):
                os.environ["META_MODEL_API_KEY"] = line.split("=", 1)[1].strip()
    check(
        "META_MODEL_API_KEY set",
        bool(os.environ.get("META_MODEL_API_KEY")),
        ".env found beside project root" if env_path.exists() else "no .env — fix: copy .env.example to .env and add the key",
    )

    # 4. Optional live adapter call
    if live:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
            from simforge.model_adapter import ModelAdapter, ModelConfig

            adapter = ModelAdapter(ModelConfig.from_env())
            reply = adapter.chat([{"role": "user", "content": "Reply with exactly: SMOKE_OK"}])
            check("Live Meta Model API call via adapter", "SMOKE_OK" in reply, f"reply starts: {reply[:40]!r}")
        except Exception as exc:  # noqa: BLE001
            check("Live Meta Model API call via adapter", False, str(exc))
    else:
        print("[SKIP] Live API call — rerun with --live to test it (one small call)")

    print()
    if failures:
        print(f"SMOKE TEST FAILED: {len(failures)} check(s): {', '.join(failures)}")
        return 1
    print("SMOKE TEST PASSED — toolchain is ready for Gate 1 on Tue Oct 27.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
