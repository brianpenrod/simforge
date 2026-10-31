"""Adapter contract tests (Gate 4, Oct 30) - fake client, no network.

Pin the design-lock v2 adapter requirements: provenance preserved,
the operator task passed explicitly, reasoning effort set low, API
failures recorded on the proposal (never raised into the runner), and
the mock's canned plan naming the frozen scene's real identifiers.
"""
import json
from types import SimpleNamespace

import pytest

from simforge.model_adapter import (ModelAdapter, ModelConfig, MockAdapter)
from simforge.plan_schema import validate_syntax

SCENE = {"parts": {"part": {"position": [0.45, 0.0, 0.025]}},
         "zones": {"target_zone": {"min": [0.38, 0.21], "max": [0.52, 0.35]}},
         "table_height_m": 0.0,
         "workspace": {"min": [-0.5, -0.4], "max": [0.7, 0.4]}}
PLAN_JSON = json.dumps({"part_id": "part", "target_zone": "target_zone",
                        "approach_height_m": 0.15, "speed_scale": 0.5})


class FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, model, messages, **kwargs):
        self.calls.append((model, messages, kwargs))
        return SimpleNamespace(
            id="resp-123", model="muse-spark-1.3",
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=PLAN_JSON),
                finish_reason="stop")])


def _adapter(completions):
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return ModelAdapter(ModelConfig(api_key="test"), client=client)


@pytest.mark.unit
def test_propose_plan_preserves_raw_response_and_provenance():
    fake = FakeCompletions()
    p = _adapter(fake).propose_plan(SCENE, "Move the part to the target zone.")
    assert p.raw_text == PLAN_JSON
    assert p.response_id == "resp-123"
    assert p.model == "muse-spark-1.3"
    assert p.finish_reason == "stop"
    assert p.latency_ms is not None and p.latency_ms >= 0
    assert p.error is None


@pytest.mark.unit
def test_propose_plan_passes_task_scene_and_low_reasoning_effort():
    fake = FakeCompletions()
    _adapter(fake).propose_plan(SCENE, "Move the part to the target zone.")
    _model, messages, kwargs = fake.calls[0]
    assert messages[0]["role"] == "system"
    user = json.loads(messages[1]["content"])
    assert user["task"] == "Move the part to the target zone."
    assert user["scene_state"] == SCENE
    assert kwargs.get("reasoning_effort") == "low"


@pytest.mark.unit
def test_api_failure_is_recorded_never_raised():
    class Boom:
        def create(self, model, messages, **kwargs):
            raise TimeoutError("deadline exceeded")

    p = _adapter(Boom()).propose_plan(SCENE, "anything")
    assert p.raw_text is None
    assert p.error_type == "TimeoutError"
    assert p.latency_ms is not None


@pytest.mark.unit
def test_mock_canned_plan_uses_real_scene_identifiers():
    p = MockAdapter().propose_plan(SCENE, "anything")
    plan = validate_syntax(json.loads(p.raw_text))
    assert plan.part_id == "part"
    assert plan.target_zone == "target_zone"
