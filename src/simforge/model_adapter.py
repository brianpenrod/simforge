"""Gate 4 model adapter — the ONLY place model calls happen.

Design rule (locked Oct 21, 2026): every in-app model call goes through this
adapter's OpenAI-compatible interface, so switching between the hosted Meta
Model API and a hosted open-weight endpoint is a config swap (.env), not a
rewrite. Keep proprietary material off tiers that may train on prompts.

Status: skeleton. `chat()` is a thin real wrapper; the planning helpers are
stubs to be filled in during Gate 4 (Oct 31–Nov 1).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class ModelConfig:
    api_key: str
    base_url: str = "https://api.meta.ai/v1"
    model: str = "muse-spark-1.3"

    @classmethod
    def from_env(cls) -> "ModelConfig":
        key = os.environ.get("META_MODEL_API_KEY", "")
        if not key:
            raise RuntimeError("META_MODEL_API_KEY is not set (see .env.example)")
        return cls(
            api_key=key,
            base_url=os.environ.get("META_MODEL_BASE_URL", cls.base_url),
            model=os.environ.get("META_MODEL_NAME", cls.model),
        )


class ModelAdapter:
    def __init__(self, config: ModelConfig):
        from openai import OpenAI  # local import: adapter stays importable offline

        self._client = OpenAI(api_key=config.api_key, base_url=config.base_url)
        self._model = config.model

    def chat(self, messages: list[dict], **kwargs) -> str:
        """Single chat completion through the configured endpoint."""
        resp = self._client.chat.completions.create(
            model=self._model, messages=messages, **kwargs
        )
        return resp.choices[0].message.content or ""

    def propose_plan(self, scene_state: dict) -> dict:
        """TODO Gate 4: return a structured task plan for the given scene state.

        Must return a dict the Gate 5 approval UX can render and a human can
        approve/reject before anything executes.
        """
        raise NotImplementedError("Gate 4 work — build week Oct 31-Nov 1")

    def describe_view(self, image_ref: str) -> dict:
        """TODO Gate 4 (stretch): vision description / segmentation hand-off."""
        raise NotImplementedError("Gate 4 stretch — only if Gates 1-3 are solid")


# --- Mock mode (Red Cell hardening, Oct 24) ---------------------------------
# Gate 5 and the demo must be buildable even if event API keys arrive late.
# Set SIMFORGE_MODEL_MOCK=1 to run the whole stack against a canned valid
# plan. The mock proves plumbing only; never cite mock runs as model results.

CANNED_PLAN = {
    "part_id": "part_box_01",
    "target_zone": "zone_a",
    "approach_height_m": 0.12,
    "speed_scale": 0.6,
}


class MockAdapter:
    """Same interface as ModelAdapter; returns canned responses, no network."""

    def chat(self, messages: list[dict], **kwargs) -> str:
        import json

        return json.dumps(CANNED_PLAN)

    def propose_plan(self, scene_state: dict) -> dict:
        return dict(CANNED_PLAN)
