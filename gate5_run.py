"""Gate 5 runner + audit verifier - design lock RATIFIED Oct 30, 2026.

Modes:
  freeze           Record the candidate hash inventory - the
                   COMPLETE runtime: the tree under src/simforge/
                   (nested modules included, review #8), the scene
                   tree the loader actually reads (scene/cell.xml
                   and its assets, review #9), the Panda model tree
                   under third_party/mujoco_menagerie/, this runner,
                   the demo and repair entry points AND the Gate 4
                   runner/stub the repairs import and launch, both
                   manifests, the Gate 3 scenarios file - + git HEAD
                   + an inventory digest into
                   results/gate5/freeze.json,
                   preserving any prior freeze as
                   freeze_<head8>.json. The freeze record does not
                   hash itself. After freezing, changes to code,
                   scenario inputs, or grading rules require a
                   new candidate; evidence and documents may be
                   added.
  suite            The headless acceptance run. Every case is
                   pre-registered from the frozen manifest; its run
                   record is persisted BEFORE setup, so a crash
                   cannot vanish from the denominator. Human cases
                   prompt the founder at the console. On an
                   interrupted status the runner halts deliberately
                   and exits non-success. On a harness defect it
                   stops (protocol: preserve, new candidate, full
                   rerun with new attempt IDs). An honest physics
                   failure is recorded and the suite CONTINUES.
  probes           The bounded fault-probe segment (own inventory,
                   gate5_probes.json). The interruption probe is
                   LAST: its expected outcome is the stop itself.
  verify           The independent audit verifier: binds the
                   attempt to its freeze record via the attempt
                   header (a changed candidate is a defect), then
                   reads the run records and the audit JSONL and
                   reports SUITE COMPLETION, AUDIT COMPLETENESS,
                   and BEHAVIORAL PASS as three distinct verdicts.
                   Shares no code with the guard.
  verify-selftest  The verifier's negative controls, run on
                   synthetic copies BEFORE the acceptance run: an
                   intact control must pass; planted defects
                   (deleted terminal, duplicated terminal, orphan
                   run_id, malformed line, whole case removed from
                   records AND audit, terminal-only audit events,
                   a missing run_id, a preregistered run that never
                   terminated, a behavioral mismatch) must each be
                   caught, and foreign-attempt audit events must NOT
                   fail a valid attempt. Review #8 added: a terminal
                   record whose preregistration and audit trail were
                   both deleted, an executed record flipped to
                   rejected/not_executed, an executed terminal whose
                   plan was substituted, and a nonterminal orphan
                   event - all must be caught.
  freeze-selftest  The freeze's targeted controls (reviews #9-#11),
                   run on a synthetic tree BEFORE freezing. The intact
                   fixture mirrors the real scene structure: a
                   parent-relative Panda include, the Panda compiler
                   meshdir, and an asset-directory link. Controls: an
                   intact freeze is accepted and the parent-relative
                   include resolves; byte edits to the root scene,
                   the Panda XML, a Panda asset, gate4_run.py, and
                   gate4_stub.py each invalidate it; an added scene
                   file invalidates it; a missing required dependency
                   prevents freezing at all; the loader-facing
                   scene/assets alias is inventoried, and a byte edit
                   through it or a redirected alias invalidates the
                   freeze; an XML-referenced mesh that is missing
                   prevents freezing, and a same-named shadow file in
                   the wrong directory does not conceal the gap.

Sim imports are lazy so verify / verify-selftest / freeze run
without the simulator stack.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

RESULTS = ROOT / "results" / "gate5"
SUITE_MANIFEST = ROOT / "gate5_suite.json"
PROBES_MANIFEST = ROOT / "gate5_probes.json"


def _freeze_inventory():
    """The acceptance candidate is the WHOLE runtime, wherever it
    lives: every file under src/simforge/ RECURSIVELY - nested
    modules (sim/cell.py), not just top-level .py files (review
    #8; the nonrecursive glob silently excluded the simulator
    loader) - plus the trees the loader ACTUALLY reads, which are
    NOT under src/simforge (review #9): scene/ (cell.xml selects
    the Panda model through the scene/assets junction) and the
    Panda tree under third_party/mujoco_menagerie/ (the XML and
    asset bytes themselves). The walk FOLLOWS directory links
    (review #10: a plain recursive glob omits a symlinked
    scene/assets entirely, so the loader-facing paths were never
    bound) - files are inventoried under every path that reaches
    them, the loader-facing scene/assets/... paths AND the real
    third_party/... paths, so an edit or a redirected alias is
    caught whichever route the loader takes; only true link
    cycles (a link to an ancestor directory) are pruned. Plus
    this runner, the demo and repair entry points, gate4_run.py
    and gate4_stub.py (the repairs import and launch them, so
    their bytes shape filed evidence), both manifests, and the
    Gate 3 scenarios file. __pycache__/.pyc are interpreter
    artifacts, not source. A change to ANY inventoried file - or
    a file added or removed - is a new candidate."""
    rels = []

    def _walk(base):
        if not base.is_dir():
            return

        def rec(directory, ancestors):
            try:
                entries = sorted(os.scandir(directory),
                                 key=lambda e: e.name)
            except OSError:
                return
            for entry in entries:
                if entry.name == "__pycache__":
                    continue
                if entry.is_dir(follow_symlinks=True):
                    real = os.path.realpath(entry.path)
                    if real in ancestors:
                        continue  # link cycle: a link to an ancestor
                    rec(entry.path, ancestors | {real})
                elif entry.is_file(follow_symlinks=True):
                    p = Path(entry.path)
                    if p.suffix != ".pyc":
                        rels.append(p.relative_to(ROOT).as_posix())

        rec(str(base), {os.path.realpath(base)})

    _walk(ROOT / "src" / "simforge")
    _walk(ROOT / "scene")
    _walk(ROOT / "third_party" / "mujoco_menagerie"
          / "franka_emika_panda")
    rels += ["gate5_run.py", "gate5_demo.py", "gate4_repairs.py",
             "gate4_run.py", "gate4_stub.py",
             "gate5_suite.json", "gate5_probes.json",
             "scenarios/example_scenarios.json"]
    return sorted(set(rels))


FREEZE_FILES = _freeze_inventory()
# Dependencies whose absence must prevent freezing entirely
# (review #9): if a tree above is missing at inventory time its
# files silently drop out of the inventory, so presence is
# asserted explicitly at freeze time.
REQUIRED_DEPS = [
    "scene/cell.xml",
    "third_party/mujoco_menagerie/franka_emika_panda/panda.xml",
    "gate4_run.py", "gate4_stub.py"]
TERMINAL_EVENTS = {"executed", "rejected", "validation_failed",
                   "validation_interrupted", "execution_failed",
                   "approval_invalidated", "approval_error",
                   "approval_interrupted", "execution_interrupted",
                   "suite_terminal"}
INTERRUPTED = {"approval_interrupted", "execution_interrupted",
               "validation_interrupted"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inventory_digest(files: dict) -> str:
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _git_head():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except Exception:
        return None


# ------------------------------------------------------------------ freeze
def mode_freeze() -> None:
    missing = [rel for rel in FREEZE_FILES if not (ROOT / rel).is_file()]
    if missing:
        raise SystemExit("REFUSED: inventoried runtime files missing "
                         "on disk: " + ", ".join(missing[:8]))
    absent = [rel for rel in REQUIRED_DEPS if rel not in FREEZE_FILES]
    if absent:
        raise SystemExit("REFUSED: required runtime dependencies are "
                         "not in the freeze inventory (their trees "
                         "were not found on disk): " + ", ".join(absent))
    _assert_referenced_assets()
    RESULTS.mkdir(parents=True, exist_ok=True)
    freeze_path = RESULTS / "freeze.json"
    if freeze_path.exists():
        # Preserve the superseded freeze record (review #7): an
        # earlier attempt stays bound to ITS candidate.
        old_text = freeze_path.read_text()
        try:
            old_head = json.loads(old_text).get("candidate_head") or "unknown"
        except Exception:
            old_head = "unknown"
        preserved = RESULTS / f"freeze_{str(old_head)[:8]}.json"
        preserved.write_text(old_text)
        print(f"Previous freeze preserved as {preserved.name}")
    files = {rel: _sha(ROOT / rel) for rel in FREEZE_FILES}
    payload = {"frozen_at": _now(), "candidate_head": _git_head(),
               "files": files,
               "inventory_digest": _inventory_digest(files)}
    freeze_path.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))
    print("FROZEN. Suite/probes refuse to run against a changed candidate.")


def _check_freeze() -> dict:
    freeze_path = RESULTS / "freeze.json"
    if not freeze_path.exists():
        raise SystemExit("REFUSED: no freeze.json - commit candidate C, "
                         "then run --mode freeze")
    frozen = json.loads(freeze_path.read_text())
    if set(frozen["files"]) != set(_freeze_inventory()):
        raise SystemExit("REFUSED: candidate file SET changed since "
                         "freeze (a runtime file was added or "
                         "removed) - a new candidate requires a "
                         "new freeze")
    current = {rel: _sha(ROOT / rel) for rel in FREEZE_FILES}
    if frozen["files"] != current:
        raise SystemExit("REFUSED: candidate changed since freeze - "
                         "a new candidate requires a new freeze")
    _assert_referenced_assets()
    return frozen


def _referenced_assets():
    """Assets the loader will open, per the inventoried XMLs
    (reviews #10-#11). A directory scan cannot see a referenced
    mesh that is missing - the file simply never enters the
    inventory - so the references themselves are validated.
    Resolution is EXACT, the way MuJoCo resolves it - never a
    list of fallback directories (review #11: a same-named file
    in the wrong directory must not conceal a missing mesh):
      mesh     -> compiler meshdir, else assetdir, else the
                  XML's own directory
      texture  -> compiler texturedir, else assetdir, else the
                  XML's own directory
      include  -> the including XML's directory, always
      other    -> compiler assetdir, else the XML's directory
    Resolved paths are normalized before comparison - a
    parent-relative reference like the scene's real
    ../third_party/... include collapses to the same form the
    inventory carries (review #11). Returns (resolved, missing):
    resolved = repo-relative paths the references land on;
    missing = human-readable broken references."""
    import posixpath
    import xml.etree.ElementTree as ET
    resolved, missing = set(), []
    for rel in FREEZE_FILES:
        if not rel.endswith(".xml"):
            continue
        xpath = ROOT / rel
        try:
            root_el = ET.parse(xpath).getroot()
        except Exception as exc:
            missing.append(f"{rel}: unparseable XML ({exc})")
            continue
        compiler = root_el.find("compiler")

        def _setting(name, _c=compiler):
            return _c.get(name) if _c is not None else None

        xdir = xpath.parent
        for el in root_el.iter():
            ref = el.get("file")
            if not ref or ref.startswith("/") or "://" in ref:
                continue
            if el.tag == "mesh":
                sub = _setting("meshdir") or _setting("assetdir")
            elif el.tag == "texture":
                sub = _setting("texturedir") or _setting("assetdir")
            elif el.tag == "include":
                sub = None
            else:
                sub = _setting("assetdir")
            raw = (xdir / sub / ref) if sub else (xdir / ref)
            if not raw.is_file():
                missing.append(f"{rel}: referenced file {ref!r} "
                               f"not found at its resolved location")
                continue
            try:
                rel_resolved = posixpath.normpath(
                    raw.relative_to(ROOT).as_posix())
            except ValueError:
                missing.append(f"{rel}: referenced file {ref!r} "
                               f"resolves outside the repository")
                continue
            resolved.add(rel_resolved)
    return resolved, missing


def _assert_referenced_assets() -> None:
    resolved, missing = _referenced_assets()
    if missing:
        raise SystemExit("REFUSED: scene/model XML references assets "
                         "that do not exist: " + "; ".join(missing[:8]))
    outside = sorted(r for r in resolved if r not in FREEZE_FILES)
    if outside:
        raise SystemExit("REFUSED: XML-referenced assets resolve "
                         "outside the freeze inventory: "
                         + ", ".join(outside[:8]))


def mode_freeze_selftest() -> None:
    """Targeted freeze controls (reviews #9-#11), run on a
    synthetic tree in a temp directory: the module globals are
    pointed at the fixture, the REAL inventory/freeze/check code
    runs, and every mutation must invalidate the freeze. The real
    tree is never touched."""
    import contextlib
    import io
    import tempfile
    global ROOT, RESULTS, FREEZE_FILES
    saved = (ROOT, RESULTS, FREEZE_FILES)
    checks = {}
    try:
        with tempfile.TemporaryDirectory() as td:
            troot = Path(td)

            def w(rel, text="x"):
                p = troot / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text)

            w("src/simforge/__init__.py", "")
            w("src/simforge/sim/cell.py", "# loader fixture")
            # The intact fixture mirrors the REAL repository
            # structure (review #11): the scene XML includes the
            # Panda model by a PARENT-RELATIVE path, the Panda XML
            # resolves its mesh through its compiler meshdir, and
            # scene/assets is a directory LINK to the Panda assets
            # (a real directory of copies stands in where link
            # creation is not permitted, e.g. stock Windows).
            w("scene/cell.xml",
              '<mujoco><include file="../third_party/'
              'mujoco_menagerie/franka_emika_panda/panda.xml"/>'
              '</mujoco>')
            w("third_party/mujoco_menagerie/franka_emika_panda/"
              "panda.xml",
              '<mujoco><compiler meshdir="assets"/><asset>'
              '<mesh name="panda" file="link0.stl"/></asset></mujoco>')
            w("third_party/mujoco_menagerie/franka_emika_panda/"
              "assets/link0.stl", "solid fixture")
            w("altassets/link0.stl", "DIFFERENT bytes fixture")
            assets_link = troot / "scene" / "assets"
            assets_target = (troot / "third_party" / "mujoco_menagerie"
                             / "franka_emika_panda" / "assets")
            link_mode = "dir"
            try:
                os.symlink(assets_target, assets_link,
                           target_is_directory=True)
                link_mode = "symlink"
            except OSError:
                assets_link.mkdir(parents=True, exist_ok=True)
                (assets_link / "link0.stl").write_text("solid fixture")

            def _unlink_link(p):
                try:
                    p.unlink()
                except OSError:
                    os.rmdir(p)

            for rel in ("gate5_run.py", "gate5_demo.py",
                        "gate4_repairs.py", "gate4_run.py",
                        "gate4_stub.py"):
                w(rel, "# fixture")
            for rel in ("gate5_suite.json", "gate5_probes.json",
                        "scenarios/example_scenarios.json"):
                w(rel, "{}")
            ROOT = troot
            RESULTS = troot / "results" / "gate5"
            FREEZE_FILES = _freeze_inventory()
            checks["inventory_covers_scene"] = \
                "scene/cell.xml" in FREEZE_FILES
            checks["inventory_covers_panda"] = any(
                p.startswith("third_party/mujoco_menagerie/"
                             "franka_emika_panda/")
                for p in FREEZE_FILES)
            checks["inventory_covers_gate4"] = \
                "gate4_run.py" in FREEZE_FILES \
                and "gate4_stub.py" in FREEZE_FILES
            checks["inventory_covers_loader_assets"] = \
                "scene/assets/link0.stl" in FREEZE_FILES
            _res, _miss = _referenced_assets()
            checks["parent_relative_include_resolves"] = (
                "third_party/mujoco_menagerie/franka_emika_panda/"
                "panda.xml" in _res and not _miss)
            with contextlib.redirect_stdout(io.StringIO()):
                mode_freeze()
            try:
                _check_freeze()
                checks["intact_freeze_accepted"] = True
            except SystemExit:
                checks["intact_freeze_accepted"] = False
            targets = {
                "scene_mutation_rejected": "scene/cell.xml",
                "panda_xml_mutation_rejected":
                    "third_party/mujoco_menagerie/"
                    "franka_emika_panda/panda.xml",
                "panda_asset_mutation_rejected":
                    "third_party/mujoco_menagerie/"
                    "franka_emika_panda/assets/link0.stl",
                "gate4_run_mutation_rejected": "gate4_run.py",
                "gate4_stub_mutation_rejected": "gate4_stub.py",
                "loader_asset_mutation_rejected":
                    "scene/assets/link0.stl",
            }
            for name, rel in targets.items():
                p = troot / rel
                original = p.read_text()
                p.write_text(original + " ")
                try:
                    _check_freeze()
                    checks[name] = False
                except SystemExit:
                    checks[name] = True
                p.write_text(original)
            w("scene/added.xml", "<mujoco/>")
            try:
                _check_freeze()
                checks["added_file_rejected"] = False
            except SystemExit:
                checks["added_file_rejected"] = True
            (troot / "scene" / "added.xml").unlink()
            # Redirecting the assets alias at different bytes
            # invalidates the freeze (review #11).
            if link_mode == "symlink":
                _unlink_link(assets_link)
                os.symlink(troot / "altassets", assets_link,
                           target_is_directory=True)
            else:
                (assets_link / "link0.stl").write_text(
                    "DIFFERENT bytes fixture")
            try:
                _check_freeze()
                checks["alias_redirect_rejected"] = False
            except SystemExit:
                checks["alias_redirect_rejected"] = True
            if link_mode == "symlink":
                _unlink_link(assets_link)
                os.symlink(assets_target, assets_link,
                           target_is_directory=True)
            else:
                (assets_link / "link0.stl").write_text("solid fixture")
            # An XML-referenced mesh missing BEFORE freezing
            # blocks the freeze (review #10): the file drops out
            # of the directory scan entirely, so only the
            # reference validation can catch it.
            panda_assets = (troot / "third_party" / "mujoco_menagerie"
                            / "franka_emika_panda" / "assets")
            (panda_assets / "link0.stl").unlink()
            FREEZE_FILES = _freeze_inventory()
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    mode_freeze()
                checks["referenced_mesh_missing_blocks_freeze"] = False
            except SystemExit:
                checks["referenced_mesh_missing_blocks_freeze"] = True
            w("third_party/mujoco_menagerie/franka_emika_panda/"
              "assets/link0.stl", "solid fixture")
            FREEZE_FILES = _freeze_inventory()
            # A same-named file in the WRONG directory must not
            # conceal the missing mesh (review #11): resolution
            # is exact - the meshdir location or nothing.
            (panda_assets / "link0.stl").unlink()
            w("third_party/mujoco_menagerie/franka_emika_panda/"
              "link0.stl", "shadow fixture")
            FREEZE_FILES = _freeze_inventory()
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    mode_freeze()
                checks["shadow_file_does_not_conceal_missing_mesh"] = False
            except SystemExit:
                checks["shadow_file_does_not_conceal_missing_mesh"] = True
            (troot / "third_party" / "mujoco_menagerie"
             / "franka_emika_panda" / "link0.stl").unlink()
            w("third_party/mujoco_menagerie/franka_emika_panda/"
              "assets/link0.stl", "solid fixture")
            FREEZE_FILES = _freeze_inventory()
            # A missing required dependency prevents freezing.
            (troot / "scene" / "cell.xml").unlink()
            FREEZE_FILES = _freeze_inventory()
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    mode_freeze()
                checks["missing_dependency_blocks_freeze"] = False
            except SystemExit:
                checks["missing_dependency_blocks_freeze"] = True
    finally:
        ROOT, RESULTS, FREEZE_FILES = saved
    print(json.dumps(checks, indent=2))
    print("FREEZE SELFTEST:", "PASS" if all(checks.values()) else "FAIL")


# ------------------------------------------------------------------ verify
def verify(manifest_cases, records, prereg_ids, all_audit_events, attempt,
           malformed_lines=0):
    """Pure verifier core (v2, Astra review #7). Returns a report
    dict with THREE verdicts, kept separate:
      suite_completion    terminal records / manifest total
      audit_completeness  fully matched runs / preregistered starts
      behavioral_pass     every terminal record follows its case's
                          filed expected_path, with the decision
                          history to match
    passed requires all three AND zero defects.

    Verifies audit CONTENTS (a timestamp on every in-scope event,
    the plan on executed terminals, phase-appropriate decisions),
    not just terminal correspondence. Audit scope is the attempt
    prefix; foreign-attempt events are ignored, but an event with
    NO run_id is a defect, never silently dropped. A preregistered
    run that never terminated stays in the started denominator.
    Denominators come from the MANIFEST and the PREREGISTRATION,
    never from the returned records alone - a case removed from
    both stores still counts against the verdicts."""
    defects = []

    def defect(kind, detail):
        defects.append({"kind": kind, "detail": detail})

    if malformed_lines:
        defect("malformed_audit_line", f"{malformed_lines} unparseable line(s)")

    cases_by_id = {c["id"]: c for c in manifest_cases}
    manifest_ids = [c["id"] for c in manifest_cases]

    records_by_id = {}
    for rec in records:
        rid = rec.get("run_id")
        if rid in records_by_id:
            defect("duplicate_run_record", rid)
        records_by_id[rid] = rec

    prefix = f"{attempt}:"
    scoped = []
    for ev in all_audit_events:
        rid = ev.get("run_id")
        if rid is None:
            defect("missing_run_id",
                   f"audit event {ev.get('event')!r} carries no run_id")
        elif isinstance(rid, str) and rid.startswith(prefix):
            scoped.append(ev)

    terminals = {}
    events_by_run = {}
    field_bad_runs = set()
    for ev in scoped:
        rid = ev.get("run_id")
        events_by_run.setdefault(rid, []).append(ev)
        if "ts" not in ev:
            defect("missing_audit_fields",
                   f"{rid}: event {ev.get('event')!r} has no ts")
            field_bad_runs.add(rid)
        if ev.get("event") in TERMINAL_EVENTS:
            terminals.setdefault(rid, []).append(ev)
    for rid, evs in terminals.items():
        if len(evs) > 1:
            defect("duplicate_terminal", rid)
    prereg_set = set(prereg_ids)
    # Orphan detection covers EVERY scoped audit run (review #8):
    # a nonterminal event (e.g. an approval) under an unknown run
    # ID is an orphan too - checking terminals only let it pass.
    for rid in events_by_run:
        if rid not in records_by_id and rid not in prereg_set:
            defect("orphan_audit_run", rid)

    # The matching universe is the UNION of preregistrations and
    # terminal records (review #8): a record whose preregistration
    # and audit trail were both deleted must still count - and
    # fail - instead of vanishing from the denominator.
    union_ids = list(prereg_ids) + [r.get("run_id") for r in records
                                    if r.get("run_id") not in prereg_set]
    matched = 0
    for rid in union_ids:
        rec = records_by_id.get(rid)
        term = terminals.get(rid, [])
        if rec is not None and rid not in prereg_set:
            defect("record_without_preregistration", rid)
        if rec is None or len(term) != 1:
            continue  # counts against started; never silently dropped
        ev = term[0]
        status = rec.get("guard_status")
        expected_event = ("suite_terminal" if status == "harness_error"
                          else status)
        if ev.get("event") != expected_event:
            defect("outcome_mismatch",
                   f"{rid}: record {status} vs audit {ev.get('event')}")
            continue
        run_ok = rid not in field_bad_runs
        if rid not in prereg_set:
            run_ok = False
        # Decision/outcome consistency of the RECORD itself
        # (review #8): an executed run recorded as rejected /
        # not_executed is contradictory evidence, whatever the
        # audit says.
        dec, out = rec.get("decision"), rec.get("outcome")
        if status == "executed":
            if dec != "approved" or out not in ("executed_success",
                                                "executed_failure"):
                defect("outcome_mismatch",
                       f"{rid}: executed record carries decision "
                       f"{dec!r} / outcome {out!r}")
                run_ok = False
        elif status == "rejected":
            if dec != "rejected" or out != "not_executed":
                defect("outcome_mismatch",
                       f"{rid}: rejected record carries decision "
                       f"{dec!r} / outcome {out!r}")
                run_ok = False
        elif status in ("execution_failed", "execution_interrupted"):
            if dec != "approved" or out != status:
                defect("outcome_mismatch",
                       f"{rid}: {status} record carries decision "
                       f"{dec!r} / outcome {out!r}")
                run_ok = False
        elif status in ("approval_error", "approval_interrupted",
                        "approval_invalidated"):
            if dec != status or out != "not_executed":
                defect("outcome_mismatch",
                       f"{rid}: {status} record carries decision "
                       f"{dec!r} / outcome {out!r}")
                run_ok = False
        # Event order within the run (review #8): the terminal
        # event is the run's LAST audit event; an approval precedes
        # any execution and follows validation.
        run_evs = events_by_run.get(rid, [])
        names = [e.get("event") for e in run_evs]
        if run_evs and run_evs[-1] is not ev:
            defect("event_order",
                   f"{rid}: terminal event is not the run's last "
                   f"audit event")
            run_ok = False
        if "approved" in names and "validated" in names \
                and names.index("approved") < names.index("validated"):
            defect("event_order",
                   f"{rid}: approved precedes validated")
            run_ok = False
        if "executed" in names and "approved" in names \
                and names.index("executed") < names.index("approved"):
            defect("event_order",
                   f"{rid}: executed precedes approved")
            run_ok = False
        # Plan correspondence (review #8): for an executed run the
        # plan carried by validated, approved, and executed must be
        # THE SAME plan - presence of a plan key proves nothing
        # about which plan ran.
        if status == "executed":
            plans = {}
            for e in run_evs:
                if e.get("event") in ("validated", "approved",
                                      "executed") and "plan" in e:
                    plans[e["event"]] = json.dumps(
                        e["plan"], sort_keys=True, default=str)
            if len(plans) != 3:
                defect("missing_audit_fields",
                       f"{rid}: executed run lacks a plan on one of "
                       f"validated/approved/executed")
                run_ok = False
            elif len(set(plans.values())) != 1:
                defect("plan_mismatch",
                       f"{rid}: validated/approved/executed plans "
                       f"differ")
                run_ok = False
        if status == "executed" and "plan" not in ev:
            defect("missing_audit_fields",
                   f"{rid}: executed terminal carries no plan")
            run_ok = False
        run_events = {e.get("event") for e in events_by_run.get(rid, [])}
        if status == "executed" and "approved" not in run_events:
            defect("decision_mismatch",
                   f"{rid}: executed with no approved event")
            run_ok = False
        if status == "rejected" and "rejected" not in run_events:
            defect("decision_mismatch",
                   f"{rid}: rejected record with no rejected event")
            run_ok = False
        if status in ("validation_failed", "validation_interrupted"):
            if "approved" in run_events:
                defect("decision_mismatch",
                       f"{rid}: {status} but an approved event exists")
                run_ok = False
            if not (rec.get("decision") == "not_requested"
                    and rec.get("outcome") == "not_executed"):
                defect("outcome_mismatch",
                       f"{rid}: validation outcome must carry decision "
                       f"not_requested / outcome not_executed")
                run_ok = False
        if run_ok:
            matched += 1

    for cid in manifest_ids:
        if not any(r.get("case_id") == cid for r in records):
            defect("missing_run_record", cid)

    behavioral_ok = True
    for rec in records:
        case = cases_by_id.get(rec.get("case_id"))
        if case is None:
            continue
        expected = case.get("expected_path")
        status = rec.get("guard_status")
        calls = rec.get("executor_calls") or 0
        bad = None
        if expected == "executed":
            if status != "executed" or calls < 1:
                bad = (f"expected executed, recorded {status} with "
                       f"{calls} executor call(s)")
        elif expected == "rejected":
            if (status != "rejected" or calls != 0
                    or (rec.get("motion_steps") or 0) != 0):
                bad = (f"expected rejected with zero execution/motion, "
                       f"recorded {status} with {calls} call(s) and "
                       f"{rec.get('motion_steps')} motion step(s)")
        elif expected == "validation_failed":
            if status != "validation_failed" or calls != 0:
                bad = (f"expected validation_failed with zero calls, "
                       f"recorded {status} with {calls} call(s)")
        if bad:
            defect("behavioral_mismatch", f"{rec.get('run_id')}: {bad}")
            behavioral_ok = False
    behavioral_pass = behavioral_ok and not any(
        d["kind"] == "decision_mismatch" for d in defects)

    completed = sum(1 for r in records
                    if r.get("guard_status") in TERMINAL_EVENTS
                    or r.get("guard_status") == "harness_error")
    completion = (completed / len(manifest_ids)) if manifest_ids else 0.0
    completeness = (matched / len(union_ids)) if union_ids else 0.0
    return {"manifest_total": len(manifest_ids),
            "records": len(records), "started": len(union_ids),
            "completed": completed, "matched": matched,
            "suite_completion": completion,
            "audit_completeness": completeness,
            "behavioral_pass": behavioral_pass,
            "defects": defects,
            "passed": bool(manifest_ids) and completion == 1.0
            and completeness == 1.0 and behavioral_pass and not defects}


def _load_jsonl(path):
    events, malformed = [], 0
    if not path.exists():
        return events, malformed
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            malformed += 1
    return events, malformed


def mode_verify(attempt: str) -> None:
    records, rec_malformed = _load_jsonl(RESULTS / f"records_{attempt}.jsonl")
    events, audit_malformed = _load_jsonl(RESULTS / "audit.jsonl")
    # Candidate binding (review #7): the attempt header written by
    # mode_suite names the freeze it ran under. Find that freeze
    # record (current or preserved) and recompute the tree against
    # ITS inventory - a changed runtime/scorer/manifest since the
    # attempt is a defect, and only the hash match makes the current
    # manifest trustworthy as the attempt's manifest.
    header = next((r for r in records
                   if r.get("event") == "attempt_header"), None)
    candidate_defects = []
    frozen = None
    if header is None:
        candidate_defects.append(
            {"kind": "candidate_changed",
             "detail": f"attempt {attempt} has no attempt header - "
                       f"it cannot be bound to a freeze record"})
    else:
        digest = header.get("freeze_digest")
        freeze_candidates = [RESULTS / "freeze.json"] + sorted(
            RESULTS.glob("freeze_*.json"))
        for fp in freeze_candidates:
            if not fp.exists():
                continue
            try:
                data = json.loads(fp.read_text())
            except Exception:
                continue
            if data.get("inventory_digest") == digest:
                frozen = data
                break
        if frozen is None:
            candidate_defects.append(
                {"kind": "candidate_changed",
                 "detail": "no freeze record matches the attempt's "
                           "freeze digest"})
        else:
            if set(frozen["files"]) != set(_freeze_inventory()):
                candidate_defects.append(
                    {"kind": "candidate_changed",
                     "detail": "working tree file SET differs from "
                               "the attempt's frozen inventory "
                               "(runtime file added or removed)"})
            current = {}
            for rel in frozen["files"]:
                p = ROOT / rel
                if p.exists():
                    current[rel] = _sha(p)
            if current != frozen["files"]:
                candidate_defects.append(
                    {"kind": "candidate_changed",
                     "detail": "working tree differs from the "
                               "attempt's frozen inventory"})
            # Referenced-asset presence (review #10): a freeze
            # written while a referenced mesh was already missing
            # matches its own inventory - only the XML references
            # expose the gap.
            _resolved, _missing = _referenced_assets()
            _outside = sorted(r for r in _resolved
                              if r not in frozen["files"])
            if _missing or _outside:
                candidate_defects.append(
                    {"kind": "candidate_changed",
                     "detail": "XML-referenced assets missing or "
                               "outside the frozen inventory: "
                               + "; ".join((_missing + _outside)[:8])})
    manifest = json.loads(SUITE_MANIFEST.read_text())
    manifest_cases = manifest["cases"]
    # Run-record files also carry the attempt header, preregistered
    # placeholders, and rejection-reason annotations (lines WITH an
    # "event" key); the verifier sees terminal run records only
    # (no "event" key) plus the preregistration inventory.
    terminal_records = [r for r in records
                        if r.get("attempt") == attempt
                        and r.get("event") is None]
    prereg_ids = [r["run_id"] for r in records
                  if r.get("event") == "preregistered"
                  and r.get("attempt") == attempt]
    report = verify(manifest_cases, terminal_records, prereg_ids,
                    events, attempt,
                    malformed_lines=rec_malformed + audit_malformed)
    if candidate_defects:
        report["defects"] = candidate_defects + report["defects"]
        report["passed"] = False
    report["attempt"] = attempt
    report["candidate_head"] = frozen["candidate_head"] if frozen else None
    report["freeze_digest"] = header.get("freeze_digest") if header else None
    (RESULTS / f"verify_{attempt}.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print("VERIFY:", "PASS" if report["passed"] else "FAIL")


def mode_verify_selftest() -> None:
    plan = {"part_id": "part", "target_zone": "target_zone",
            "approach_height_m": 0.15, "speed_scale": 0.5}

    def ev(rid, event, ts, **extra):
        return {"run_id": rid, "event": event, "ts": ts, **extra}

    base_records = [
        {"run_id": "T:C1", "attempt": "T", "case_id": "C1",
         "started_ts": "2026-01-01T00:00:00+0000", "guard_status": "executed",
         "decision": "approved", "outcome": "executed_success",
         "executor_calls": 1, "motion_steps": 42},
        {"run_id": "T:C2", "attempt": "T", "case_id": "C2",
         "started_ts": "2026-01-01T00:00:01+0000",
         "guard_status": "validation_failed", "decision": "not_requested",
         "outcome": "not_executed", "executor_calls": 0, "motion_steps": 0},
        {"run_id": "T:C3", "attempt": "T", "case_id": "C3",
         "started_ts": "2026-01-01T00:00:02+0000", "guard_status": "rejected",
         "decision": "rejected", "outcome": "not_executed",
         "executor_calls": 0, "motion_steps": 0},
    ]
    base_events = [
        ev("T:C1", "plan_received", "2026-01-01T00:00:00+0000"),
        ev("T:C1", "validated", "2026-01-01T00:00:01+0000", plan=plan),
        ev("T:C1", "approved", "2026-01-01T00:00:02+0000", plan=plan),
        ev("T:C1", "executed", "2026-01-01T00:00:03+0000", plan=plan),
        ev("T:C2", "plan_received", "2026-01-01T00:00:01+0000"),
        ev("T:C2", "validation_failed", "2026-01-01T00:00:01+0000"),
        ev("T:C3", "plan_received", "2026-01-01T00:00:02+0000"),
        ev("T:C3", "validated", "2026-01-01T00:00:02+0000", plan=plan),
        ev("T:C3", "rejected", "2026-01-01T00:00:03+0000", plan=plan),
    ]
    base_prereg = ["T:C1", "T:C2", "T:C3"]
    manifest_cases = [{"id": "C1", "expected_path": "executed"},
                      {"id": "C2", "expected_path": "validation_failed"},
                      {"id": "C3", "expected_path": "rejected"}]
    results = {}

    def run(name, records, prereg, events, malformed=0):
        rep = verify(manifest_cases, records, prereg, events, "T",
                     malformed)
        results[name] = rep
        return rep

    intact = run("intact", base_records, base_prereg, base_events)
    d1 = run("deleted_terminal", base_records, base_prereg,
             [e for e in base_events if not (e["run_id"] == "T:C1"
                                             and e["event"] == "executed")])
    d2 = run("duplicated_terminal", base_records, base_prereg,
             base_events + [ev("T:C3", "rejected",
                               "2026-01-01T00:00:04+0000", plan=plan)])
    d3 = run("orphan_run", base_records, base_prereg,
             base_events + [ev("T:C9", "executed",
                               "2026-01-01T00:00:05+0000", plan=plan)])
    d4 = run("malformed_line", base_records, base_prereg, base_events,
             malformed=1)
    d5 = run("case_removed_everywhere",
             [r for r in base_records if r["case_id"] != "C2"],
             [r for r in base_prereg if r != "T:C2"],
             [e for e in base_events if e["run_id"] != "T:C2"])
    # Review #7 controls: contents, identity, denominators, scoping,
    # behavior - not just terminal correspondence.
    d6 = run("terminal_only_audit", base_records, base_prereg,
             [{"run_id": "T:C1", "event": "executed"},
              {"run_id": "T:C2", "event": "validation_failed"},
              {"run_id": "T:C3", "event": "rejected"}])
    d7 = run("missing_run_id", base_records, base_prereg,
             base_events + [{"run_id": None, "event": "approved",
                             "ts": "2026-01-01T00:00:06+0000"}])
    d8 = run("prereg_gap", base_records,
             base_prereg + [f"T:C{i}" for i in range(4, 12)],
             base_events)
    d9 = run("foreign_attempt_events", base_records, base_prereg,
             base_events + [
                 ev("U:C1", "plan_received", "2026-01-01T00:00:00+0000"),
                 ev("U:C1", "approved", "2026-01-01T00:00:01+0000",
                    plan=plan),
                 ev("U:C1", "executed", "2026-01-01T00:00:02+0000",
                    plan=plan)])
    rejected_c1_records = [
        dict(base_records[0], guard_status="rejected",
             decision="rejected", outcome="not_executed",
             executor_calls=0, motion_steps=0)] + base_records[1:]
    rejected_c1_events = [
        e for e in base_events
        if not (e["run_id"] == "T:C1"
                and e["event"] in ("approved", "executed"))]
    rejected_c1_events.append(
        ev("T:C1", "rejected", "2026-01-01T00:00:03+0000", plan=plan))
    d10 = run("behavioral_mismatch", rejected_c1_records, base_prereg,
              rejected_c1_events)
    # Review #8 controls: denominator vanishing, contradictory
    # record fields, substituted executed plan, nonterminal orphan.
    d11 = run("record_without_preregistration",
              base_records,
              [r for r in base_prereg if r != "T:C1"],
              [e for e in base_events if e["run_id"] != "T:C1"])
    flipped_c1_records = [
        dict(base_records[0], decision="rejected",
             outcome="not_executed")] + base_records[1:]
    d12 = run("executed_decision_flipped", flipped_c1_records,
              base_prereg, base_events)
    substituted_events = [
        dict(e, plan={"part_id": "wrong_part"})
        if (e["run_id"] == "T:C1" and e["event"] == "executed") else e
        for e in base_events]
    d13 = run("executed_plan_substituted", base_records, base_prereg,
              substituted_events)
    d14 = run("nonterminal_orphan", base_records, base_prereg,
              base_events + [ev("T:ORPHAN", "approved",
                                "2026-01-01T00:00:07+0000", plan=plan)])
    checks = {
        "intact_passes": intact["passed"],
        "deleted_terminal_caught": (not d1["passed"]
                                    and d1["audit_completeness"] < 1.0),
        "duplicated_terminal_caught": any(
            x["kind"] == "duplicate_terminal" for x in d2["defects"]),
        "orphan_caught": any(x["kind"] == "orphan_audit_run"
                             for x in d3["defects"]),
        "malformed_caught": any(x["kind"] == "malformed_audit_line"
                                for x in d4["defects"]),
        "case_removal_caught": any(x["kind"] == "missing_run_record"
                                   for x in d5["defects"]),
        "terminal_only_audit_caught": (
            not d6["passed"] and any(
                x["kind"] == "missing_audit_fields" for x in d6["defects"])),
        "missing_run_id_caught": (
            not d7["passed"] and any(
                x["kind"] == "missing_run_id" for x in d7["defects"])),
        "prereg_gap_completeness": (
            not d8["passed"] and d8["audit_completeness"] < 1.0),
        "foreign_attempt_scoped": d9["passed"],
        "behavioral_mismatch_caught": (
            not d10["passed"] and any(
                x["kind"] == "behavioral_mismatch" for x in d10["defects"])),
        "record_without_preregistration_caught": (
            not d11["passed"] and d11["audit_completeness"] < 1.0
            and any(x["kind"] == "record_without_preregistration"
                    for x in d11["defects"])),
        "executed_decision_flipped_caught": (
            not d12["passed"] and any(
                x["kind"] == "outcome_mismatch" for x in d12["defects"])),
        "executed_plan_substituted_caught": (
            not d13["passed"] and any(
                x["kind"] == "plan_mismatch" for x in d13["defects"])),
        "nonterminal_orphan_caught": (
            not d14["passed"] and any(
                x["kind"] == "orphan_audit_run" for x in d14["defects"])),
    }
    payload = {"selftest": checks, "all_passed": all(checks.values()),
               "reports": {k: v for k, v in results.items()}}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "verify_selftest.json").write_text(json.dumps(payload, indent=2))
    print(json.dumps(checks, indent=2))
    print("VERIFY SELFTEST:", "PASS" if payload["all_passed"] else "FAIL")
# ------------------------------------------------------------- suite core
def _sim_imports():
    from simforge import evaluator, grasp
    from simforge.guard import AuditLog, run_guarded
    from simforge.scoring import evaluate_attempt
    return evaluator, grasp, AuditLog, run_guarded, evaluate_attempt


def _execute_and_score(evaluator, grasp, evaluate_attempt,
                       model, data, ids, rest_z, zone, plan, cell):
    t0 = float(data.time)
    samples = None
    try:
        samples = grasp.execute_plan(model, data, plan, ids,
                                     log=lambda *a: None)
        cell["motion_steps"] = len(samples)
    finally:
        # Elapsed time is preserved on EVERY exit (review #8): an
        # exception INSIDE execute_plan (not only in the scorer)
        # must not read as zero motion. A partial sample count is
        # unknowable when execute_plan raises before returning, so
        # motion_steps stays None - recorded as unknown, never
        # asserted as zero.
        cell["sim_time_advanced_s"] = float(data.time) - t0
        if samples is None:
            cell["motion_steps"] = None
    # Partial telemetry lands in the cell BEFORE scoring (review
    # #7): if the scorer raises, the guard records execution_failed
    # and the run record still shows the motion that actually
    # happened - a scorer fault after motion never reads as zero.
    verdict = dict(evaluate_attempt(samples, rest_z, zone))
    verdict["final_part_pos"] = [float(v) for v in data.xpos[ids.part_body]]
    verdict["sim_duration_s"] = float(data.time) - t0
    return verdict


def _approval_display(run_id, case, plan_dict, scene_state, source_note):
    part_pos = scene_state["parts"][plan_dict["part_id"]]["position"] \
        if plan_dict["part_id"] in scene_state["parts"] else None
    zone = scene_state["zones"].get(plan_dict["target_zone"])
    print()
    print(f"--- APPROVAL REQUIRED: {run_id} ---")
    print(f"Case             : {case['id']} ({source_note})")
    if case.get("request_text"):
        print(f"Operator request : {case['request_text']}")
    print(f"Proposed plan    : {plan_dict}")
    if part_pos is not None:
        print(f"Scene identity   : {plan_dict['part_id']} at "
              f"[{part_pos[0]:.3f}, {part_pos[1]:.3f}, {part_pos[2]:.3f}]")
    if zone is not None:
        print(f"Destination      : {plan_dict['target_zone']} x "
              f"{zone['min'][0]:.2f}..{zone['max'][0]:.2f}, y "
              f"{zone['min'][1]:.2f}..{zone['max'][1]:.2f}")
    print("Checklist        : correct object? correct destination? "
          "reasonable parameters?")
    return input("Approve execution? [y/N] ").strip().lower() == "y"


def _append_record(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def _run_one(attempt, case, scenarios_by_index, audit, imports):
    """Execute one pre-registered case. Returns (record, halt_reason).
    halt_reason: None | 'interrupted' | 'harness'."""
    evaluator, grasp, AuditLog, run_guarded, evaluate_attempt = imports
    run_id = f"{attempt}:{case['id']}"
    rec = {"run_id": run_id, "attempt": attempt, "case_id": case["id"],
           "source": case["source"], "expectation": case.get("expectation"),
           "expected_path": case.get("expected_path"),
           "started_ts": _now(), "guard_status": None, "decision": None,
           "outcome": None, "executor_calls": 0, "motion_steps": 0,
           "sim_time_advanced_s": 0.0, "physics": None}
    records_path = RESULTS / f"records_{attempt}.jsonl"
    _append_record(records_path, {**rec, "event": "preregistered"})
    try:
        if case["source"] == "gate3_suite":
            scenario = scenarios_by_index[case["scenario_index"]]
            rec["scenario_name"] = scenario["name"]
            plan_dict = scenario["plan"]
            draw = evaluator.perturb(scenario)
            model, data, ids, rest_z, zone = evaluator._setup_scene(draw)
            if "shift" in scenario:
                # Filed scenario stimulus (review #7): G3-06's part
                # is displaced AFTER setup, before the approval
                # snapshot - same stage the Gate 3 evaluator uses.
                before, after = evaluator._apply_shift(
                    model, data, ids, scenario["shift"])
                rec["shift"] = {"dx": scenario["shift"]["dx"],
                                "dy": scenario["shift"]["dy"],
                                "before": [round(v, 4) for v in before],
                                "after": [round(v, 4) for v in after]}
            scene_state = evaluator._live_scene_state(model, data, ids)
        elif case["id"] == "G5-GHOST":
            plan_dict = case["plan"]
            model = data = ids = None
            scene_state = evaluator._reject_scene_state(case["part_start"])
        else:
            plan_dict = case["plan"]
            scenario = {"name": case["id"], "seed": case["seed"],
                        "part_position": list(case["part_start"]),
                        "expect": "success", "plan": {}}
            if case.get("target_zone_pos") is not None:
                scenario["target_zone_pos"] = list(case["target_zone_pos"])
            draw = evaluator.perturb(scenario)
            model, data, ids, rest_z, zone = evaluator._setup_scene(draw)
            scene_state = evaluator._live_scene_state(model, data, ids)
    except BaseException as exc:  # setup failure = harness defect
        rec.update({"guard_status": "harness_error",
                    "outcome": "harness_error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "finished_ts": _now()})
        audit.write("suite_terminal", run_id=run_id,
                    outcome="harness_error", error=rec["error"])
        _append_record(records_path, rec)
        return rec, "harness"

    cell = {"calls": 0, "motion_steps": 0, "sim_time_advanced_s": 0.0}

    def executor(plan, _cell=cell):
        _cell["calls"] += 1
        if model is None:
            return {"counted_only": True}
        return _execute_and_score(evaluator, grasp, evaluate_attempt,
                                  model, data, ids, rest_z, zone, plan, _cell)

    def approve(plan, _case=case, _pid=plan_dict, _ss=scene_state):
        return _approval_display(run_id, _case, _pid, _ss,
                                 _case["source"])

    def scene_provider(_m=model, _d=data, _i=ids):
        return evaluator._live_scene_state(_m, _d, _i)

    result = run_guarded(plan_dict, scene_state, executor, approve, audit,
                         scene_provider=scene_provider if model is not None
                         else None,
                         run_id=run_id)
    rec["guard_status"] = result.status
    rec["executor_calls"] = cell["calls"]
    rec["motion_steps"] = cell["motion_steps"]
    rec["sim_time_advanced_s"] = cell["sim_time_advanced_s"]
    if result.status == "executed":
        rec["decision"] = "approved"
        rec["physics"] = result.outcome
        rec["outcome"] = ("executed_success"
                          if result.outcome and result.outcome.get("success")
                          else "executed_failure")
    elif result.status == "rejected":
        rec["decision"] = "rejected"
        rec["outcome"] = "not_executed"
    elif result.status in ("validation_failed", "validation_interrupted"):
        rec["decision"] = "not_requested"
        rec["outcome"] = "not_executed"
    elif result.status in ("execution_failed", "execution_interrupted"):
        # The human approved; execution was attempted and failed or
        # was interrupted (review #7). Keep the decision and report
        # the status as the outcome - never "not_executed"; the
        # partial telemetry copied from the cell above stays.
        rec["decision"] = "approved"
        rec["outcome"] = result.status
    else:
        # approval_error / approval_interrupted / approval_invalidated
        rec["decision"] = result.status
        rec["outcome"] = "not_executed"
    rec["finished_ts"] = _now()
    _append_record(records_path, rec)
    if result.status == "rejected":
        # Terminal outcome is persisted BEFORE the optional reason.
        reason = input("Rejection reason (optional, Enter to skip): ").strip()
        if reason:
            rec["rejection_reason"] = reason
            _append_record(records_path,
                           {"run_id": run_id, "event": "rejection_reason",
                            "reason": reason, "ts": _now()})
    if result.status in INTERRUPTED:
        return rec, "interrupted"
    if result.status in ("execution_failed", "approval_error"):
        # Unexpected fault, not an honestly scored physics outcome:
        # harness-stop protocol (preserve, new candidate, rerun).
        return rec, "harness"
    return rec, None


def mode_suite(attempt: str) -> None:
    frozen = _check_freeze()
    imports = _sim_imports()
    evaluator = imports[0]
    AuditLog = imports[2]
    manifest = json.loads(SUITE_MANIFEST.read_text())
    scenarios = json.loads((ROOT / manifest["scenarios_file"]).read_text())
    if len(scenarios) != 8:
        raise SystemExit(f"Gate 3 scenarios file must contain 8 scenarios, "
                         f"found {len(scenarios)}")
    scenarios_by_index = {i: s for i, s in enumerate(scenarios)}
    records_path = RESULTS / f"records_{attempt}.jsonl"
    if records_path.exists():
        raise SystemExit(f"REFUSED: attempt {attempt} already exists - a "
                         f"rerun uses a NEW attempt id (harness protocol)")
    # Attempt header (review #7): binds this attempt's records to
    # the freeze it runs under. mode_verify re-derives the candidate
    # from it; the records reader skips it like every "event" line.
    _append_record(records_path,
                   {"event": "attempt_header", "attempt": attempt,
                    "candidate_head": frozen.get("candidate_head"),
                    "freeze_digest": frozen.get("inventory_digest")})
    audit = AuditLog(RESULTS / "audit.jsonl")
    done = []
    for case in manifest["cases"]:
        print(f"\n=== {case['id']} ({case['source']})")
        rec, halt = _run_one(attempt, case, scenarios_by_index, audit, imports)
        done.append(rec)
        print(f"-> {rec['guard_status']} | outcome {rec['outcome']} | "
              f"executor_calls {rec['executor_calls']} | "
              f"motion_steps {rec['motion_steps']}")
        if halt == "interrupted":
            print("\nSUITE HALTED: interrupted status - terminal outcome "
                  "recorded; exiting non-success by design.")
            sys.exit(2)
        if halt == "harness":
            print("\nSUITE STOPPED: harness defect - preserve this "
                  "attempt, fix under a new candidate, rerun the "
                  "complete suite with new attempt IDs.")
            sys.exit(3)
    met = sum(1 for r in done
              if r["guard_status"] == r["expected_path"])
    summary = {"attempt": attempt, "cases": len(done),
               "expected_paths_met": met,
               "records": done}
    (RESULTS / f"suite_{attempt}.json").write_text(json.dumps(summary, indent=2))
    print(f"\nSUITE {attempt} COMPLETE: expected paths met {met}/{len(done)}. "
          f"Run --mode verify --attempt {attempt} for the audit verdicts.")


# ----------------------------------------------------------------- probes
def mode_probes(attempt: str) -> None:
    _check_freeze()
    imports = _sim_imports()
    evaluator, _grasp, AuditLog, run_guarded, _score = imports
    manifest = json.loads(PROBES_MANIFEST.read_text())
    scene = evaluator._reject_scene_state([0.45, 0.0])
    plan = {"part_id": "part", "target_zone": "target_zone",
            "approach_height_m": 0.15, "speed_scale": 0.5}
    audit = AuditLog(RESULTS / "audit_probes.jsonl")
    records_path = RESULTS / f"probe_records_{attempt}.jsonl"
    if records_path.exists():
        raise SystemExit(f"REFUSED: probe attempt {attempt} already exists")
    rows = []
    for probe in manifest["probes"]:
        run_id = f"{attempt}:{probe['id']}"
        calls = {"n": 0}

        def counting_executor(p, _c=calls):
            _c["n"] += 1
            return {"counted": True}

        kind = probe["kind"]
        if kind == "approval_error":
            def approve(p):
                raise RuntimeError("simulated approval failure")
            executor = counting_executor
        elif kind == "execution_error":
            def approve(p):
                return True

            def executor(p, _c=calls):
                _c["n"] += 1  # count BEFORE throwing (review #7)
                raise RuntimeError("simulated execution failure")
        elif kind == "invalidation":
            def approve(p):
                p.speed_scale = 0.99  # mutate after validation
                return True
            executor = counting_executor
        elif kind == "interrupt":
            def approve(p):
                raise KeyboardInterrupt
            executor = counting_executor
        else:
            raise SystemExit(f"unknown probe kind: {kind}")
        result = run_guarded(plan, scene, executor, approve, audit,
                             run_id=run_id)
        ok = result.status == probe["expected_status"]
        if kind in ("approval_error", "invalidation", "interrupt"):
            ok = ok and calls["n"] == 0
        if kind == "execution_error":
            ok = ok and calls["n"] == 1
        # Probe evidence fields follow the same decision/outcome
        # semantics as suite records (review #8): an execution
        # fault was APPROVED and its outcome is the fault status -
        # never decision=<status> / outcome="executed".
        if result.status == "executed":
            p_decision, p_outcome = "approved", "executed"
        elif result.status in ("execution_failed",
                               "execution_interrupted"):
            p_decision, p_outcome = "approved", result.status
        elif result.status in ("validation_failed",
                               "validation_interrupted"):
            p_decision, p_outcome = "not_requested", "not_executed"
        elif result.status == "rejected":
            p_decision, p_outcome = "rejected", "not_executed"
        else:  # approval_error / approval_interrupted / invalidated
            p_decision, p_outcome = result.status, "not_executed"
        rec = {"run_id": run_id, "attempt": attempt,
               "case_id": probe["id"], "kind": kind,
               "expected_status": probe["expected_status"],
               "guard_status": result.status,
               "executor_calls": calls["n"], "passed": bool(ok),
               "started_ts": _now(), "decision": p_decision,
               "outcome": p_outcome}
        _append_record(records_path, rec)
        rows.append(rec)
        print(f"{probe['id']}: status={result.status} "
              f"executor_calls={calls['n']} -> {'PASS' if ok else 'FAIL'}")
        if kind == "interrupt":
            print("Interrupt probe reached: segment stops here, as "
                  "prefiled. This is the probe segment's expected end, "
                  "not an acceptance-suite interruption.")
            break
    payload = {"attempt": attempt, "all_passed": all(r["passed"] for r in rows),
               "probes": rows}
    (RESULTS / f"probes_{attempt}.json").write_text(json.dumps(payload, indent=2))
    print("PROBES:", "PASS" if payload["all_passed"] else "FAIL")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gate 5 runner + verifier")
    parser.add_argument("--mode", required=True,
                        choices=["freeze", "suite", "probes", "verify",
                                 "verify-selftest", "freeze-selftest"])
    parser.add_argument("--attempt", default=None,
                        help="attempt id, e.g. A1 (required for suite, "
                             "probes, verify)")
    args = parser.parse_args()
    if args.mode == "freeze":
        mode_freeze()
    elif args.mode == "verify-selftest":
        mode_verify_selftest()
    elif args.mode == "freeze-selftest":
        mode_freeze_selftest()
    elif args.mode in ("suite", "probes", "verify"):
        if not args.attempt:
            parser.error("--attempt is required for this mode")
        {"suite": mode_suite, "probes": mode_probes,
         "verify": mode_verify}[args.mode](args.attempt)


if __name__ == "__main__":
    main()


