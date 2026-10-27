"""Unit tests for the approval guard (src/simforge/guard.py).

The guard's contract, proven with a fake executor:
  - an approved plan executes exactly once, fully audited;
  - a rejected plan NEVER executes, and the rejection is audited;
  - an invalid plan never reaches the human, never executes,
    and the validation failure is audited.
"""
import json

import pytest

from simforge.guard import AuditLog, run_guarded

pytestmark = pytest.mark.unit

RAW = {
    "part_id": "part",
    "target_zone": "target_zone",
    "approach_height_m": 0.10,
    "speed_scale": 0.5,
}

SCENE_STATE = {
    "parts": {"part": {"position": [0.45, 0.0, 0.025]}},
    "zones": {"target_zone": {"min": [0.38, 0.21], "max": [0.52, 0.35]}},
    "table_height_m": 0.0,
    "workspace": {"min": [-0.5, -0.4], "max": [0.7, 0.4]},
}


def _events(audit):
    return [json.loads(line) for line in audit.path.read_text(encoding="utf-8").splitlines()]


def test_approved_plan_executes_and_is_fully_audited(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    calls = []
    result = run_guarded(
        RAW, SCENE_STATE,
        executor=lambda plan: calls.append(plan) or "done",
        approve=lambda plan: True,
        audit=audit,
    )
    assert result.status == "executed"
    assert len(calls) == 1
    assert [e["event"] for e in _events(audit)] == [
        "plan_received", "validated", "approved", "executed",
    ]


def test_rejected_plan_never_executes(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    calls = []
    result = run_guarded(
        RAW, SCENE_STATE,
        executor=lambda plan: calls.append(plan),
        approve=lambda plan: False,
        audit=audit,
    )
    assert result.status == "rejected"
    assert calls == []
    assert [e["event"] for e in _events(audit)] == [
        "plan_received", "validated", "rejected",
    ]


def test_invalid_plan_never_reaches_the_human(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    calls = []
    approvals = []
    result = run_guarded(
        {**RAW, "speed_scale": 2.0}, SCENE_STATE,
        executor=lambda plan: calls.append(plan),
        approve=lambda plan: approvals.append(plan) or True,
        audit=audit,
    )
    assert result.status == "validation_failed"
    assert calls == []
    assert approvals == []
    assert [e["event"] for e in _events(audit)] == [
        "plan_received", "validation_failed",
    ]


def test_hallucinated_part_fails_validation_at_the_guard(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    calls = []
    result = run_guarded(
        {**RAW, "part_id": "ghost_part"}, SCENE_STATE,
        executor=lambda plan: calls.append(plan),
        approve=lambda plan: True,
        audit=audit,
    )
    assert result.status == "validation_failed"
    assert calls == []
