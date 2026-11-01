"""Guard v3.1 contract tests (Astra review #7 remediation, Oct 31).

Pin the three review-#7 guard corrections: a plan damaged by the
approval callback still ends in an audited terminal (the binding
re-check is protected and logging uses the post-validation plan
snapshot), and interruption identity survives the early phases -
KeyboardInterrupt during initial validation is
validation_interrupted, and during the fresh-scene re-check is
approval_interrupted - so callers halt instead of continuing.
"""
import json

import pytest

import simforge.guard as guard
from simforge.guard import AuditLog, run_guarded

SCENE = {"parts": {"part": {"position": [0.45, 0.0, 0.025]}},
         "zones": {"target_zone": {"min": [0.38, 0.21], "max": [0.52, 0.35]}},
         "table_height_m": 0.0,
         "workspace": {"min": [-0.5, -0.4], "max": [0.7, 0.4]}}
PLAN = {"part_id": "part", "target_zone": "target_zone",
        "approach_height_m": 0.15, "speed_scale": 0.5}
TERMINAL = {"executed", "rejected", "validation_failed",
            "validation_interrupted", "execution_failed",
            "approval_invalidated", "approval_error",
            "approval_interrupted", "execution_interrupted"}


def _events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.unit
def test_plan_damaged_by_approval_callback_is_audited_terminal(tmp_path):
    """Review #7 reproduction: approve() deletes plan.speed_scale
    and returns True. The binding re-check must not raise - the run
    ends approval_invalidated, executor untouched, audit terminal,
    and the audit's plan payloads are the intact snapshot."""
    audit = AuditLog(tmp_path / "audit.jsonl")
    calls = {"n": 0}

    def counting_executor(plan):
        calls["n"] += 1
        return {}

    def damaging_approve(plan):
        del plan.speed_scale
        return True

    result = run_guarded(PLAN, SCENE, counting_executor,
                         damaging_approve, audit, run_id="run-101")
    assert result.status == "approval_invalidated"
    assert calls["n"] == 0  # executor never invoked
    events = _events(audit.path)
    assert events[-1]["event"] == "approval_invalidated"
    assert events[-1]["event"] in TERMINAL
    assert events[-1]["run_id"] == "run-101"
    # The snapshot protected the logging: the approved event carries
    # the full validated plan even though the object was damaged.
    approved = [e for e in events if e["event"] == "approved"]
    assert approved and approved[0]["plan"]["speed_scale"] == 0.5
    assert events[-1]["plan"]["speed_scale"] == 0.5


@pytest.mark.unit
def test_keyboard_interrupt_during_validation_is_validation_interrupted(
        tmp_path, monkeypatch):
    def interrupting_semantics(plan, scene_state):
        raise KeyboardInterrupt

    monkeypatch.setattr(guard, "validate_semantics",
                        interrupting_semantics)
    audit = AuditLog(tmp_path / "audit.jsonl")
    calls = {"n": 0}

    def counting_executor(plan):
        calls["n"] += 1
        return {}

    result = run_guarded(PLAN, SCENE, counting_executor,
                         lambda plan: True, audit, run_id="run-102")
    assert result.status == "validation_interrupted"
    assert calls["n"] == 0
    events = _events(audit.path)
    assert events[-1]["event"] == "validation_interrupted"
    assert events[-1]["event"] in TERMINAL
    assert events[-1]["error_type"] == "KeyboardInterrupt"
    assert events[-1]["run_id"] == "run-102"


@pytest.mark.unit
def test_keyboard_interrupt_at_scene_recheck_is_approval_interrupted(
        tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    calls = {"n": 0}

    def counting_executor(plan):
        calls["n"] += 1
        return {}

    def interrupting_scene_provider():
        raise KeyboardInterrupt

    result = run_guarded(PLAN, SCENE, counting_executor,
                         lambda plan: True, audit,
                         scene_provider=interrupting_scene_provider,
                         run_id="run-103")
    assert result.status == "approval_interrupted"
    assert calls["n"] == 0
    events = _events(audit.path)
    assert events[-1]["event"] == "approval_interrupted"
    assert events[-1]["event"] in TERMINAL
    assert events[-1]["error_type"] == "KeyboardInterrupt"
    assert events[-1]["run_id"] == "run-103"


@pytest.mark.unit
def test_ordinary_approve_and_execute_still_executes(tmp_path):
    """Control: the v3.1 changes did not disturb the normal path -
    full audit chain, terminal executed, outcome returned."""
    audit = AuditLog(tmp_path / "audit.jsonl")
    result = run_guarded(PLAN, SCENE, lambda plan: {"ok": True},
                         lambda plan: True, audit, run_id="run-104")
    assert result.status == "executed"
    assert result.outcome == {"ok": True}
    events = _events(audit.path)
    assert [e["event"] for e in events] == [
        "plan_received", "validated", "approved", "executed"]
    assert all(e.get("run_id") == "run-104" for e in events)
    assert events[-1]["plan"]["speed_scale"] == 0.5
