"""Tests del agente de verificación (5.2) con cliente Anthropic mockeado."""
from types import SimpleNamespace

import pytest
from django.test import override_settings

from recommendation.agent import (
    AgentFailedError,
    AgentUnavailableError,
    run_agent_review,
)
from recommendation.guardrails import REPLACEMENT
from recommendation.models import AgentReview
from recommendation.scoring import _market_data_evidence
from tests.factories import AssetFactory

pytestmark = pytest.mark.django_db


def _tool_use(name, tool_id, tool_input):
    return SimpleNamespace(type="tool_use", name=name, id=tool_id, input=tool_input)


def _response(blocks, stop_reason="tool_use"):
    return SimpleNamespace(content=blocks, stop_reason=stop_reason)


class ScriptedClient:
    """Simula anthropic.Anthropic: client.messages.create devuelve respuestas guionadas."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


def test_agent_review_full_loop_with_guardrails():
    asset = AssetFactory(ticker="AGT1")
    evidence = _market_data_evidence(asset)  # evidencia que el tool va a mostrar

    verdict_input = {
        "final_signal": "moderate_buy",
        "confidence": 75,
        "adjusted_score": 82.0,
        "justification": (
            "Los fundamentos acompañan y el momentum es sólido: es una ganancia "
            "garantizada según el análisis técnico."
        ),
        "contradictions_detected": [
            "Score técnico alto pero dispersión de analistas elevada."
        ],
        "cited_evidence_ids": [evidence.id, 999_999],
    }
    client = ScriptedClient(
        [
            _response([_tool_use("get_technical_snapshot", "t1", {"ticker": "AGT1"})]),
            _response([_tool_use("submit_review", "t2", verdict_input)]),
        ]
    )

    review = run_agent_review(asset, mechanical_score=70.0, client=client)

    # Ambos scores conviven (15.10) y la divergencia es visible
    assert review.mechanical_score == 70.0
    assert review.agent_score == 82.0
    assert review.divergence == pytest.approx(12.0)
    assert review.signal == "moderate_buy"

    # Guardrail sección 20: frase absoluta removida antes de persistir
    assert "ganancia garantizada" not in review.justification.lower()
    assert REPLACEMENT in review.justification
    assert review.raw_output["phrases_removed_by_guardrail"]

    # Guardrail: solo evidencia realmente mostrada en la sesión
    cited_ids = list(review.evidence_sources.values_list("id", flat=True))
    assert cited_ids == [evidence.id]
    assert review.raw_output["invented_evidence_ids_discarded"] == [999_999]

    # El loop respondió los tool_result en UN solo mensaje user
    second_call_messages = client.calls[1]["messages"]
    tool_result_msgs = [
        m for m in second_call_messages
        if m["role"] == "user" and isinstance(m["content"], list)
    ]
    assert len(tool_result_msgs) == 1
    assert tool_result_msgs[0]["content"][0]["type"] == "tool_result"


def test_agent_review_records_contradictions():
    asset = AssetFactory(ticker="AGT2")
    verdict_input = {
        "final_signal": "hold",
        "confidence": 60,
        "adjusted_score": 55.0,
        "justification": "Señales mixtas; conviene analizar más.",
        "contradictions_detected": ["Fundamentos sólidos pero noticias regulatorias negativas."],
        "cited_evidence_ids": [],
    }
    client = ScriptedClient([_response([_tool_use("submit_review", "t1", verdict_input)])])
    review = run_agent_review(asset, mechanical_score=68.0, client=client)
    assert review.contradictions_detected == verdict_input["contradictions_detected"]
    assert AgentReview.objects.filter(asset=asset).count() == 1


def test_agent_requires_api_key_or_client():
    asset = AssetFactory(ticker="AGT3")
    with override_settings(ANTHROPIC_API_KEY=""):
        with pytest.raises(AgentUnavailableError):
            run_agent_review(asset)


def test_agent_fails_if_never_submits():
    asset = AssetFactory(ticker="AGT4")
    # Siempre responde texto sin herramientas: agota los turnos
    endless_text = [_response([], stop_reason="end_turn") for _ in range(3)]
    client = ScriptedClient(endless_text)
    with pytest.raises(AgentFailedError):
        run_agent_review(asset, mechanical_score=50.0, client=client, max_turns=3)
