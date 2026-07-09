"""Tests de REGRESIÓN del score mecánico 5.1 (sección 16.6: cambiar el score
ante entradas fijas debe ser una decisión explícita, no un accidente)."""
from types import SimpleNamespace

import pytest

from market.models import AssetType
from recommendation import scoring
from recommendation.guardrails import contains_forbidden_phrases, sanitize_text
from recommendation.models import Recommendation, Signal, signal_for_score
from tests.factories import AssetFactory

pytestmark = pytest.mark.django_db


def _fixed_components(monkeypatch, technical=70.0, news=(60.0, 5), fund=55.0, risk=80.0):
    monkeypatch.setattr(
        scoring, "latest_technical_snapshot",
        lambda asset: {"score": technical, "signals": ["señal técnica de prueba"]},
    )
    monkeypatch.setattr(scoring, "news_score", lambda asset: news)
    monkeypatch.setattr(
        scoring, "latest_ratios",
        lambda asset: SimpleNamespace(
            fundamental_score=fund, per=15.0, roe=0.18, net_margin=0.2,
            dcf_upside=0.1, net_debt_to_ebitda=1.0,
        ) if fund is not None else None,
    )
    monkeypatch.setattr(
        scoring, "latest_risk",
        lambda asset: SimpleNamespace(
            risk_score=risk, volatility_annual=0.2, max_drawdown=-0.15, beta=1.05,
        ),
    )
    monkeypatch.setattr(scoring, "risk_summary_text", lambda m, a: ["Riesgo de mercado general."])


def test_signal_table_boundaries():
    assert signal_for_score(80) == Signal.STRONG_BUY
    assert signal_for_score(79.9) == Signal.MODERATE_BUY
    assert signal_for_score(65) == Signal.MODERATE_BUY
    assert signal_for_score(64.9) == Signal.HOLD
    assert signal_for_score(50) == Signal.HOLD
    assert signal_for_score(49.9) == Signal.HIGH_RISK
    assert signal_for_score(35) == Signal.HIGH_RISK
    assert signal_for_score(34.9) == Signal.AVOID


def test_mechanical_score_regression_weighted_formula(monkeypatch):
    """30%·70 + 25%·60 + 25%·55 + 20%·80 = 65.75 → 65.8, compra moderada."""
    _fixed_components(monkeypatch)
    asset = AssetFactory(ticker="SCOR1")
    result = scoring.compute_mechanical_score(asset)
    assert result["score"] == pytest.approx(65.8)
    assert result["signal"] == Signal.MODERATE_BUY
    assert result["technical_score"] == 70.0
    assert result["news_score"] == 60.0
    assert result["fundamental_score"] == 55.0
    assert result["risk_score"] == 80.0


def test_crypto_without_fundamentals_is_capped(monkeypatch):
    """Sección 12: cripto sin fundamentos no puede pasar de 'mantener' (64)."""
    _fixed_components(monkeypatch, technical=95.0, news=(90.0, 10), fund=None, risk=90.0)
    asset = AssetFactory(ticker="SCOR2-USD", asset_type=AssetType.CRYPTO)
    result = scoring.compute_mechanical_score(asset)
    assert result["score"] == pytest.approx(64.0)
    assert result["signal"] == Signal.HOLD
    assert "cripto_capado_sin_fundamentos" in result["flags"]


def test_stock_without_fundamentals_uses_neutral(monkeypatch):
    _fixed_components(monkeypatch, fund=None)
    asset = AssetFactory(ticker="SCOR3")
    result = scoring.compute_mechanical_score(asset)
    # 21 + 15 + 12.5 + 16 = 64.5
    assert result["score"] == pytest.approx(64.5)
    assert "sin_fundamentales" in result["flags"]


def test_explanation_and_risks_are_present_and_prudent(monkeypatch):
    """Reglas 18/20: desglose auditable, riesgos explícitos, sin frases absolutas."""
    _fixed_components(monkeypatch)
    asset = AssetFactory(ticker="SCOR4")
    result = scoring.compute_mechanical_score(asset)
    assert "30%" in result["explanation"] or "Técnico (30%)" in result["explanation"]
    assert result["risks"].strip()
    assert not contains_forbidden_phrases(result["explanation"])
    assert "no constituye asesoramiento" in result["explanation"]


def test_persist_recommendation_attaches_evidence(monkeypatch):
    _fixed_components(monkeypatch)
    asset = AssetFactory(ticker="SCOR5")
    result = scoring.compute_mechanical_score(asset)
    recommendation = scoring.persist_recommendation(asset, result)
    assert Recommendation.objects.filter(asset=asset).count() == 1
    # Regla 18: ninguna recomendación sin fuentes explícitas
    assert recommendation.evidence_sources.count() >= 1
    levels = {e.reliability_level for e in recommendation.evidence_sources.all()}
    assert levels  # toda fuente lleva su nivel calculado


def test_guardrails_sanitize_forbidden_phrases():
    text = "Es una COMPRA SEGURA con ganancia garantizada y no hay riesgo."
    sanitized, removed = sanitize_text(text)
    assert len(removed) == 3
    assert "compra segura" not in sanitized.lower()
    assert "ganancia garantizada" not in sanitized.lower()
    assert "no hay riesgo" not in sanitized.lower()
    assert sanitize_text("Señal de compra moderada con riesgo alto.")[1] == []
