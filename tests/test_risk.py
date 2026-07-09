"""Tests de métricas de riesgo (4.8) y regla estricta cripto (sección 12)."""
import pytest

from market.models import AssetType
from risk.models import AssetRiskMetrics
from risk.services import compute_asset_risk, risk_summary_text
from tests.factories import AssetFactory
from tests.helpers import make_price_frame, store_prices

pytestmark = pytest.mark.django_db


def test_insufficient_history_returns_notes():
    asset = AssetFactory(ticker="RSK0")
    result = compute_asset_risk(asset, persist=False)
    assert result["risk_score"] is None
    assert any("insuficiente" in n.lower() for n in result["notes"])


def test_beta_against_itself_like_benchmark_is_one():
    frame = make_price_frame(seed=11)
    spy = AssetFactory(ticker="SPY")
    store_prices(spy, frame)
    asset = AssetFactory(ticker="RSK1")
    store_prices(asset, frame)  # misma serie → beta 1, correlación 1

    result = compute_asset_risk(asset, benchmark_ticker="SPY", persist=True)
    assert result["beta"] == pytest.approx(1.0, abs=0.01)
    assert result["correlations"]["SPY"] == pytest.approx(1.0, abs=0.01)
    assert result["volatility_annual"] > 0
    assert result["max_drawdown"] <= 0
    assert 0 <= result["risk_score"] <= 100
    assert AssetRiskMetrics.objects.filter(asset=asset).exists()


def test_crypto_penalty_lowers_score():
    frame = make_price_frame(seed=13)
    spy = AssetFactory(ticker="SPY")
    store_prices(spy, frame)

    stock = AssetFactory(ticker="RSK2")
    store_prices(stock, frame)
    crypto = AssetFactory(ticker="RSK2-USD", asset_type=AssetType.CRYPTO)
    store_prices(crypto, frame)

    stock_score = compute_asset_risk(stock, persist=False)["risk_score"]
    crypto_result = compute_asset_risk(crypto, persist=False)
    assert crypto_result["risk_score"] == pytest.approx(stock_score - 15.0, abs=0.2)
    assert any("sección 12" in n.lower() or "criptoactivo" in n.lower() for n in crypto_result["notes"])


def test_risk_summary_text_always_includes_something():
    asset = AssetFactory(ticker="RSK3")
    assert risk_summary_text(None, asset)  # sin métricas → incertidumbre alta
