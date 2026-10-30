"""Approval guard + audit log spine (ratified Oct 27, 2026: build early).

Every plan execution in SimForge flows through run_guarded:

    plan -> validate (syntax + semantics) -> human approve/reject
         -> execute (only if approved) -> outcome recorded

Nothing executes unvalidated. Nothing executes unapproved. Every step is
written to an append-only JSONL audit log. Gate 5 builds its UX on this
spine; the executor is injected, so tests drive it with a fake and the
real motion stack plugs in at Gate 2/3 without changing the guard.

Oct 30 hardening (Astra reviews #4/#5, design lock v2):
  - Terminal audit on EVERY path: validation, approval, and execution
    exceptions all end in an audited outcome. The validation catch is
    deliberately broad (not ValueError-only): plan_schema raises
    ValueError uniformly, but an unexpected exception type is still a
    validation failure and is recorded with its type, never allowed to
    escape and leave the audit unterminated.
  - Approval is BOUND to the exact validated plan and scene. At
    validation time the guard fingerprints both; immediately before
    execution it re-derives the plan fingerprint and (when the caller
    supplies scene_provider) re-validates against FRESH scene state
    and compares fingerprints. A changed plan, or a changed-but-still-
    valid scene, invalidates the approval: nothing executes and the
    invalidation is audited. Merely re-checking that a changed scene
    is still valid is NOT sufficient.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import time
from dataclasses import dataclass

from .plan_schema import Plan, validate_semantics, validate_syntax

DEFAULT_AUDIT_PATH = pathlib.Path("results/audit/audit_log.jsonl")


def _fingerprint(obj) -> str:
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                           default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _plan_fingerprint(plan: Plan) -> str:
    return _fingerprint({
        "part_id": plan.part_id,
        "target_zone": plan.target_zone,
        "approach_height_m": plan.approach_height_m,
        "speed_scale": plan.speed_scale,
    })


def _scene_fingerprint(scene_state) -> str:
    """Fingerprint the scene fields validation depends on, so any
    relevant drift after approval is detected."""
    try:
        parts = {pid: list(p["position"])
                 for pid, p in scene_state["parts"].items()}
        zones = {name: {"min": list(z["min"]), "max": list(z["max"])}
                 for name, z in scene_state["zones"].items()}
        return _fingerprint({
            "parts": parts,
            "zones": zones,
            "table_height_m": scene_state["table_height_m"],
            "workspace": scene_state["workspace"],
        })
    except Exception:
        return _fingerprint({"unstructured": str(scene_state)})


class AuditLog:
    """Append-only JSONL audit log. One JSON object per line, timestamped."""

    def __init__(self, path=DEFAULT_AUDIT_PATH):
        self.path = pathlib.Path(path)

    def write(self, event: str, **fields) -> dict:
        record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                  "event": event, **fields}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        return record


@dataclass
class GuardResult:
    # executed | rejected | validation_failed | execution_failed
    # approval_invalidated | approval_error
    status: str
    plan: Plan | None = None
    outcome: object = None
    error: str | None = None


def run_guarded(raw_plan, scene_state, executor, approve, audit: AuditLog,
                scene_provider=None) -> GuardResult:
    """Validate, seek approval, execute if approved, audit everything.

    executor: callable(Plan) -> outcome (called ONLY after approval,
              and only if the approval is still bound to the exact
              validated plan and scene)
    approve:  callable(Plan) -> bool   (the human gate)
    scene_provider: optional callable() -> fresh scene_state, consulted
              immediately before execution for the binding re-check.
    """
    audit.write("plan_received", raw_plan=raw_plan)
    try:
        plan = validate_syntax(raw_plan)
        validate_semantics(plan, scene_state)
    except Exception as exc:
        audit.write("validation_failed", error=str(exc),
                    error_type=type(exc).__name__)
        return GuardResult(status="validation_failed", error=str(exc))
    plan_fp = _plan_fingerprint(plan)
    scene_fp = _scene_fingerprint(scene_state)
    audit.write("validated", plan=plan.__dict__,
                plan_fingerprint=plan_fp, scene_fingerprint=scene_fp)

    try:
        approved = approve(plan)
    except Exception as exc:
        audit.write("approval_error", plan=plan.__dict__, error=str(exc),
                    error_type=type(exc).__name__)
        return GuardResult(status="approval_error", plan=plan,
                           error=str(exc))
    if not approved:
        audit.write("rejected", plan=plan.__dict__,
                    plan_fingerprint=plan_fp)
        return GuardResult(status="rejected", plan=plan)
    audit.write("approved", plan=plan.__dict__, plan_fingerprint=plan_fp)

    # Binding re-check: the approval covers THIS plan in THIS scene.
    if _plan_fingerprint(plan) != plan_fp:
        audit.write("approval_invalidated",
                    reason="plan changed after approval",
                    plan=plan.__dict__)
        return GuardResult(status="approval_invalidated", plan=plan,
                           error="plan changed after approval")
    if scene_provider is not None:
        try:
            fresh_scene = scene_provider()
            validate_semantics(plan, fresh_scene)
            fresh_fp = _scene_fingerprint(fresh_scene)
        except Exception as exc:
            audit.write("approval_invalidated",
                        reason="fresh scene state failed validation",
                        error=str(exc), error_type=type(exc).__name__)
            return GuardResult(status="approval_invalidated", plan=plan,
                               error=str(exc))
        if fresh_fp != scene_fp:
            audit.write("approval_invalidated",
                        reason="scene changed after approval",
                        scene_fingerprint=scene_fp,
                        fresh_scene_fingerprint=fresh_fp)
            return GuardResult(status="approval_invalidated", plan=plan,
                               error="scene changed after approval")

    try:
        outcome = executor(plan)
    except Exception as exc:
        audit.write("execution_failed", plan=plan.__dict__,
                    error=str(exc), error_type=type(exc).__name__)
        return GuardResult(status="execution_failed", plan=plan,
                           error=str(exc))
    audit.write("executed", plan=plan.__dict__, outcome=str(outcome))
    return GuardResult(status="executed", plan=plan, outcome=outcome)

