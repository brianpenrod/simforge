"""Guard v3 contract tests (Astra review #6 remediation, Oct 30).

Pin the two review-#6 guard requirements: every audit event of a
run carries the caller's run_id, and an operator interruption at
approval or during execution terminates in an audited non-success
outcome instead of escaping and leaving the audit unterminated.
"""
import json

import pytest

from simforge.guard import AuditLog, run_guarded

SCENE = {"parts": {"part": {"position": [0.45, 0.0, 0.025]}},
         "zones": {"target_zone": {"min": [0.38, 0.21], "max": [0.52, 0.35]}},
         "table_height_m": 0.0,
         "workspace": {"min": [-0.5, -0.4], "max": [0.7, 0.4]}}
PLAN = {"part_id": "part", "target_zone": "target_zone",
        "approach_height_m": 0.15, "speed_scale": 0.5}


def _events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.unit
def test_run_id_on_every_audit_event(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    result = run_guarded(PLAN, SCENE, lambda plan: {"ok": True},
                         lambda plan: True, audit, run_id="run-001")
    assert result.status == "executed"
    events = _events(audit.path)
    assert events and all(e.get("run_id") == "run-001" for e in events)
    assert events[-1]["event"] == "executed"


@pytest.mark.unit
def test_keyboard_interrupt_at_approval_is_terminal_and_audited(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    calls = {"n": 0}

    def counting_executor(plan):
        calls["n"] += 1
        return {}

    def interrupting_approve(plan):
        raise KeyboardInterrupt

    result = run_guarded(PLAN, SCENE, counting_executor,
                         interrupting_approve, audit, run_id="run-002")
    assert result.status == "approval_interrupted"
    assert calls["n"] == 0  # executor never invoked
    events = _events(audit.path)
    assert events[-1]["event"] == "approval_interrupted"
    assert events[-1]["error_type"] == "KeyboardInterrupt"
    assert events[-1]["run_id"] == "run-002"


@pytest.mark.unit
def test_keyboard_interrupt_during_execution_is_terminal_and_audited(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")

    def interrupting_executor(plan):
        raise KeyboardInterrupt

    result = run_guarded(PLAN, SCENE, interrupting_executor,
                         lambda plan: True, audit, run_id="run-003")
    assert result.status == "execution_interrupted"
    events = _events(audit.path)
    assert events[-1]["event"] == "execution_interrupted"
    assert events[-1]["error_type"] == "KeyboardInterrupt"


@pytest.mark.unit
def test_ordinary_exception_at_approval_keeps_approval_error(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")

    def broken_approve(plan):
        raise RuntimeError("prompt failed")

    result = run_guarded(PLAN, SCENE, lambda plan: {}, broken_approve,
                         audit, run_id="run-004")
    assert result.status == "approval_error"
    assert _events(audit.path)[-1]["event"] == "approval_error"
