"""Tests del pipeline en dos etapas (5.3): umbral y top N controlan el costo."""
import pytest
from django.test import override_settings

from recommendation import agent as agent_module
from recommendation import pipeline
from tests.factories import AssetFactory

pytestmark = pytest.mark.django_db

SCORES = {"PIPA": 80.0, "PIPB": 70.0, "PIPC": 40.0}


@pytest.fixture
def three_assets(monkeypatch):
    assets = [AssetFactory(ticker=t) for t in SCORES]

    def fake_compute(asset):
        return {
            "ticker": asset.ticker,
            "score": SCORES[asset.ticker],
            "signal": "hold",
        }

    monkeypatch.setattr(pipeline, "compute_mechanical_score", fake_compute)
    monkeypatch.setattr(pipeline, "persist_recommendation", lambda asset, result: None)
    return assets


def test_stage_one_ranks_all_universe(three_assets):
    result = pipeline.run_universe_scoring(escalate=False)
    assert result["scored"] == 3
    assert [r["ticker"] for r in result["ranking"]] == ["PIPA", "PIPB", "PIPC"]
    assert result["escalated"] == []


@override_settings(AGENT_SCORE_THRESHOLD=65.0, AGENT_TOP_N=10)
def test_stage_two_escalates_only_above_threshold(three_assets, monkeypatch):
    escalated = []
    monkeypatch.setattr(
        agent_module, "run_agent_review",
        lambda asset, mechanical_score=None, **kw: escalated.append(asset.ticker),
    )
    result = pipeline.run_universe_scoring(escalate=True, sync_agent=True)
    assert result["escalated"] == ["PIPA", "PIPB"]  # PIPC (40) queda fuera
    assert escalated == ["PIPA", "PIPB"]


@override_settings(AGENT_SCORE_THRESHOLD=65.0, AGENT_TOP_N=1)
def test_top_n_caps_llm_cost(three_assets, monkeypatch):
    """El gasto crece con el top N elegido, no con el universo (5.3)."""
    escalated = []
    monkeypatch.setattr(
        agent_module, "run_agent_review",
        lambda asset, mechanical_score=None, **kw: escalated.append(asset.ticker),
    )
    result = pipeline.run_universe_scoring(escalate=True, sync_agent=True)
    assert result["escalated"] == ["PIPA"]


@override_settings(AGENT_SCORE_THRESHOLD=90.0, AGENT_TOP_N=10)
def test_no_escalation_when_nothing_clears_threshold(three_assets, monkeypatch):
    called = []
    monkeypatch.setattr(
        agent_module, "run_agent_review",
        lambda asset, **kw: called.append(asset.ticker),
    )
    result = pipeline.run_universe_scoring(escalate=True, sync_agent=True)
    assert result["escalated"] == []
    assert called == []


def test_agent_errors_do_not_break_pipeline(three_assets, monkeypatch):
    def broken_agent(asset, **kw):
        raise RuntimeError("API caída")

    monkeypatch.setattr(agent_module, "run_agent_review", broken_agent)
    result = pipeline.run_universe_scoring(escalate=True, sync_agent=True)
    assert result["scored"] == 3  # el scoring mecánico sobrevive
