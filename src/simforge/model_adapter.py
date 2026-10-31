"""Gate 4 model adapter — the ONLY place model calls happen.

Design rule (locked Oct 21, 2026): every in-app model call goes through this
adapter's OpenAI-compatible interface, so switching between the hosted Meta
Model API and a hosted open-weight endpoint is a config swap (.env), not a
rewrite. Keep proprietary material off tiers that may train on prompts.

Gate 4 implementation (Oct 30, 2026; design lock v2):
  - propose_plan(scene_state, task) makes ONE call and returns a
    PlanProposal carrying the RAW response text plus full provenance
    (response id, reported model, finish reason, monotonic latency,
    SDK version, endpoint). It never parses, repairs, or retries: the
    caller grades the first response exactly as received, and parsing
    is the admission layer's job (plan_schema.parse_plan).
  - The client is constructed with max_retries=0 and a finite timeout:
    the SDK default (2 retries) would silently break the no-retry
    grading rule. API failures come back as proposal.error, never as
    an exception escaping into the runner.
  - Reasoning effort is set LOW (GATE_METRICS: a reasoning model at
    default effort is how the latency target dies).
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

SYSTEM_PROMPT = (
    "You are the planning component of SimForge, a robot-cell "
    "feasibility verifier. You receive a JSON scene state and an "
    "operator task. Respond with exactly one JSON object and no other "
    "text. The object must have exactly these keys: \"part_id\" "
    "(string), \"target_zone\" (string), \"approach_height_m\" "
    "(number, 0.02 to 0.50), \"speed_scale\" (number, 0.1 to 1.0). "
    "Use only part_id and target_zone values that appear in the scene "
    "state. approach_height_m is the gripper height above the part "
    "before descent, in meters. speed_scale multiplies the nominal "
    "motion speed."
)


@dataclass
class ModelConfig:
    api_key: str
    base_url: str = "https://api.meta.ai/v1"
    model: str = "muse-spark-1.3"
    timeout_s: float = 20.0
    reasoning_effort: str = "low"

    @classmethod
    def from_env(cls) -> "ModelConfig":
        key = os.environ.get("META_MODEL_API_KEY", "")
        if not key:
            raise RuntimeError("META_MODEL_API_KEY is not set (see .env.example)")
        return cls(
            api_key=key,
            base_url=os.environ.get("META_MODEL_BASE_URL", cls.base_url),
            model=os.environ.get("META_MODEL_NAME", cls.model),
            timeout_s=float(os.environ.get("META_MODEL_TIMEOUT_S",
                                           cls.timeout_s)),
            reasoning_effort=os.environ.get("META_MODEL_REASONING_EFFORT",
                                            cls.reasoning_effort),
        )


@dataclass
class PlanProposal:
    """One model call, exactly as it happened. raw_text is the first
    response, preserved before any parsing; error is set instead when
    the call itself failed (refusal-shaped responses still arrive as
    raw_text with a finish_reason)."""
    raw_text: str | None
    response_id: str | None = None
    model: str | None = None
    finish_reason: str | None = None
    latency_ms: float | None = None
    error: str | None = None
    error_type: str | None = None
    sdk_version: str | None = None
    base_url: str | None = None
    configured_model: str | None = None


class ModelAdapter:
    def __init__(self, config: ModelConfig, client=None):
        self._config = config
        if client is None:
            from openai import OpenAI  # local import: importable offline

            client = OpenAI(api_key=config.api_key,
                            base_url=config.base_url,
                            max_retries=0,
                            timeout=config.timeout_s)
        self._client = client
        self._model = config.model

    def chat(self, messages: list[dict], **kwargs) -> str:
        """Single chat completion; returns content only. Kept for the
        smoke test and other legacy callers."""
        resp = self._client.chat.completions.create(
            model=self._model, messages=messages, **kwargs)
        return resp.choices[0].message.content or ""

    def chat_detailed(self, messages: list[dict], **kwargs) -> PlanProposal:
        """One call with provenance. Never raises for an API failure:
        the failure is recorded on the proposal."""
        try:
            import openai
            sdk_version = openai.__version__
        except Exception:
            sdk_version = None
        t0 = time.monotonic()
        try:
            resp = self._client.chat.completions.create(
                model=self._model, messages=messages, **kwargs)
        except Exception as exc:
            return PlanProposal(
                raw_text=None,
                latency_ms=(time.monotonic() - t0) * 1000.0,
                error=str(exc), error_type=type(exc).__name__,
                sdk_version=sdk_version, base_url=self._config.base_url,
                configured_model=self._model)
        latency_ms = (time.monotonic() - t0) * 1000.0
        choice = resp.choices[0] if getattr(resp, "choices", None) else None
        return PlanProposal(
            raw_text=(choice.message.content if choice is not None
                      else None),
            response_id=getattr(resp, "id", None),
            model=getattr(resp, "model", None),
            finish_reason=(getattr(choice, "finish_reason", None)
                           if choice is not None else None),
            latency_ms=latency_ms, sdk_version=sdk_version,
            base_url=self._config.base_url, configured_model=self._model)

    def propose_plan(self, scene_state: dict, task: str) -> PlanProposal:
        """Ask the model for one plan for this scene and task. The
        operator task is passed explicitly alongside the scene
        snapshot (design lock v2)."""
        user = json.dumps({"task": task, "scene_state": scene_state})
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user}]
        kwargs = {}
        if self._config.reasoning_effort:
            kwargs["reasoning_effort"] = self._config.reasoning_effort
        return self.chat_detailed(messages, **kwargs)

    def describe_view(self, image_ref: str) -> dict:
        """TODO Gate 4 (stretch): vision description / segmentation hand-off."""
        raise NotImplementedError("Gate 4 stretch — only if Gates 1-3 are solid")


# --- Mock mode (Red Cell hardening, Oct 24) ---------------------------------
# Gate 5 and the demo must be buildable even if event API keys arrive late.
# Set SIMFORGE_MODEL_MOCK=1 to run the whole stack against a canned valid
# plan. The mock proves plumbing only; never cite mock runs as model results.
# Oct 30 (design lock v2): canned identifiers fixed to the frozen scene's
# real ones (part / target_zone); the Oct 24 names (part_box_01 / zone_a)
# named objects that do not exist in the cell.

CANNED_PLAN = {
    "part_id": "part",
    "target_zone": "target_zone",
    "approach_height_m": 0.12,
    "speed_scale": 0.6,
}


class MockAdapter:
    """Same interface as ModelAdapter; returns canned responses, no network."""

    def chat(self, messages: list[dict], **kwargs) -> str:
        return json.dumps(CANNED_PLAN)

    def propose_plan(self, scene_state: dict, task: str) -> PlanProposal:
        return PlanProposal(raw_text=json.dumps(CANNED_PLAN),
                            response_id="mock-response",
                            model="mock", finish_reason="stop",
                            latency_ms=0.0)
