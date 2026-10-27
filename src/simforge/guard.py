"""Approval guard + audit log spine (ratified Oct 27, 2026: build early).

Every plan execution in SimForge flows through run_guarded:

    plan -> validate (syntax + semantics) -> human approve/reject
         -> execute (only if approved) -> outcome recorded

Nothing executes unvalidated. Nothing executes unapproved. Every step is
written to an append-only JSONL audit log. Gate 5 builds its UX on this
spine; the executor is injected, so tests drive it with a fake and the
real motion stack plugs in at Gate 2/3 without changing the guard.
"""
from __future__ import annotations

import json
import pathlib
import time
from dataclasses import dataclass

from .plan_schema import Plan, validate_semantics, validate_syntax

DEFAULT_AUDIT_PATH = pathlib.Path("results/audit/audit_log.jsonl")


class AuditLog:
    """Append-only JSONL audit log. One JSON object per line, timestamped."""

    def __init__(self, path=DEFAULT_AUDIT_PATH):
        self.path = pathlib.Path(path)

    def write(self, event: str, **fields) -> dict:
        record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event, **fields}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        return record


@dataclass
class GuardResult:
    status: str  # executed | rejected | validation_failed
    plan: Plan | None = None
    outcome: object = None
    error: str | None = None


def run_guarded(raw_plan, scene_state, executor, approve, audit: AuditLog) -> GuardResult:
    """Validate, seek approval, execute if approved, audit everything.

    executor: callable(Plan) -> outcome (called ONLY after approval)
    approve:  callable(Plan) -> bool   (the human gate)
    """
    audit.write("plan_received", raw_plan=raw_plan)
    try:
        plan = validate_syntax(raw_plan)
        validate_semantics(plan, scene_state)
    except ValueError as exc:
        audit.write("validation_failed", error=str(exc))
        return GuardResult(status="validation_failed", error=str(exc))
    audit.write("validated", plan=plan.__dict__)

    if not approve(plan):
        audit.write("rejected", plan=plan.__dict__)
        return GuardResult(status="rejected", plan=plan)
    audit.write("approved", plan=plan.__dict__)

    outcome = executor(plan)
    audit.write("executed", plan=plan.__dict__, outcome=str(outcome))
    return GuardResult(status="executed", plan=plan, outcome=outcome)
