"""Tests de valorización, rebalanceo y concentración de cartera (4.5, 4.9)."""
from decimal import Decimal

import pytest
from django.utils import timezone

from market.models import AssetType, MarketPrice
from portfolio.models import Portfolio, PortfolioPosition
from portfolio.services import (
    concentration,
    rebalance_suggestions,
    revalue_portfolio,
)
from tests.factories import AssetFactory, UserFactory

pytestmark = pytest.mark.django_db


def _price(asset, close: str, days_ago: int = 0):
    return MarketPrice.objects.create(
        asset=asset,
        datetime=timezone.now() - timezone.timedelta(days=days_ago),
        close=Decimal(close),
        open=Decimal(close), high=Decimal(close), low=Decimal(close),
        volume=1000,
    )


def _portfolio():
    return Portfolio.objects.create(user=UserFactory(), name="Test", base_currency="USD")


def test_revalue_computes_pl_and_weights():
    portfolio = _portfolio()
    asset = AssetFactory(ticker="VAL1")
    _price(asset, "100")
    PortfolioPosition.objects.create(
        portfolio=portfolio, asset=asset,
        quantity=Decimal("10"), average_price=Decimal("50"), fees=Decimal("10"),
    )

    summary = revalue_portfolio(portfolio)
    assert summary["total_value"] == pytest.approx(1000.0)
    assert summary["total_cost"] == pytest.approx(510.0)
    assert summary["total_profit_loss"] == pytest.approx(490.0)

    position = portfolio.positions.get()
    assert float(position.current_price) == pytest.approx(100.0)
    assert position.weight == pytest.approx(100.0)
    assert float(position.profit_loss) == pytest.approx(490.0)
    assert position.profit_loss_pct == pytest.approx(490.0 / 510.0 * 100)


def test_revalue_skips_assets_without_prices():
    portfolio = _portfolio()
    asset = AssetFactory(ticker="NOPX")
    PortfolioPosition.objects.create(
        portfolio=portfolio, asset=asset,
        quantity=Decimal("1"), average_price=Decimal("10"),
    )
    summary = revalue_portfolio(portfolio)
    assert summary["valued_count"] == 0
    assert summary["total_value"] == 0.0


def test_rebalance_suggestions_directions_and_amounts():
    portfolio = _portfolio()
    a = AssetFactory(ticker="RB1")
    b = AssetFactory(ticker="RB2")
    _price(a, "100")
    _price(b, "100")
    # 75% / 25% actual; objetivo 50/50
    PortfolioPosition.objects.create(
        portfolio=portfolio, asset=a, quantity=Decimal("7.5"),
        average_price=Decimal("100"), target_weight=50.0,
    )
    PortfolioPosition.objects.create(
        portfolio=portfolio, asset=b, quantity=Decimal("2.5"),
        average_price=Decimal("100"), target_weight=50.0,
    )

    result = rebalance_suggestions(portfolio)
    by_ticker = {s["ticker"]: s for s in result["suggestions"]}
    assert by_ticker["RB1"]["action"] == "reducir exposición"
    assert by_ticker["RB1"]["delta_pct"] == pytest.approx(-25.0)
    assert by_ticker["RB1"]["approx_amount"] == pytest.approx(-250.0)
    assert by_ticker["RB2"]["action"] == "aumentar exposición"
    assert result["warning"] is None


def test_rebalance_warns_when_targets_do_not_sum_100():
    portfolio = _portfolio()
    a = AssetFactory(ticker="RB3")
    _price(a, "100")
    PortfolioPosition.objects.create(
        portfolio=portfolio, asset=a, quantity=Decimal("10"),
        average_price=Decimal("100"), target_weight=60.0,
    )
    result = rebalance_suggestions(portfolio)
    assert result["warning"] is not None


def test_concentration_sums_and_exposures():
    portfolio = _portfolio()
    stock = AssetFactory(ticker="CON1", sector="Technology", country="United States")
    crypto = AssetFactory(ticker="CON2-USD", asset_type=AssetType.CRYPTO, sector="", country="")
    _price(stock, "100")
    _price(crypto, "100")
    PortfolioPosition.objects.create(
        portfolio=portfolio, asset=stock, quantity=Decimal("6"), average_price=Decimal("50"),
    )
    PortfolioPosition.objects.create(
        portfolio=portfolio, asset=crypto, quantity=Decimal("4"), average_price=Decimal("50"),
    )
    revalue_portfolio(portfolio)

    result = concentration(portfolio)
    assert sum(result["by_asset"].values()) == pytest.approx(100.0)
    assert result["crypto_exposure_pct"] == pytest.approx(40.0)
    assert result["tech_exposure_pct"] == pytest.approx(60.0)
    assert result["hhi"] == pytest.approx(0.6**2 + 0.4**2, rel=1e-3)
