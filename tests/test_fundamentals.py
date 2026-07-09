"""Tests del tablero fundamental (4.3): ratios exactos, DCF y score de regresión."""
import pandas as pd
import pytest

from fundamentals.services import (
    compute_dcf,
    compute_ratios,
    fundamental_score,
    sync_fundamentals,
)
from market.models import AssetType
from market.providers import set_provider
from tests.factories import AssetFactory
from tests.fakes import FakeProvider

pytestmark = pytest.mark.django_db


def _statements():
    """Estados con etiquetas reales de yfinance y números redondos."""
    period = pd.Timestamp("2025-12-31")
    income = pd.DataFrame(
        {
            period: {
                "Total Revenue": 100.0,
                "Gross Profit": 60.0,
                "EBIT": 30.0,
                "EBITDA": 40.0,
                "Net Income": 20.0,
                "Pretax Income": 25.0,
                "Tax Provision": 5.0,
                "Interest Expense": 5.0,
            }
        }
    )
    balance = pd.DataFrame(
        {
            period: {
                "Total Assets": 200.0,
                "Current Assets": 80.0,
                "Current Liabilities": 40.0,
                "Inventory": 20.0,
                "Stockholders Equity": 100.0,
                "Total Debt": 50.0,
                "Cash And Cash Equivalents": 30.0,
            }
        }
    )
    cashflow = pd.DataFrame(
        {
            period: {
                "Free Cash Flow": 25.0,
                "Operating Cash Flow": 35.0,
                "Capital Expenditure": -10.0,
            }
        }
    )
    return {"income": income, "balance": balance, "cashflow": cashflow}


def _info():
    # Sin ratios precalculados de .info → fuerza el camino de cálculo propio
    return {
        "currentPrice": 10.0,
        "marketCap": 1000.0,
        "totalDebt": 50.0,
        "totalCash": 30.0,
        "sharesOutstanding": 100.0,
        "beta": 1.0,
        "earningsGrowth": 0.10,
        "freeCashflow": 25.0,
    }


def test_compute_ratios_exact_values():
    asset = AssetFactory(ticker="FUND")
    ratios = compute_ratios(asset, _info(), _statements())

    # Bloque 2: EV = 1000 + 50 − 30 = 1020
    assert ratios["enterprise_value"] == pytest.approx(1020.0)
    assert ratios["ev_ebitda"] == pytest.approx(1020.0 / 40.0)
    assert ratios["ev_ebit"] == pytest.approx(1020.0 / 30.0)
    assert ratios["ev_fcf"] == pytest.approx(1020.0 / 25.0)
    assert ratios["ev_sales"] == pytest.approx(10.2)

    # Bloque 3 (desde estados): ROE 20/100, ROA 20/200, márgenes 60/30/20%
    assert ratios["roe"] == pytest.approx(0.20)
    assert ratios["roa"] == pytest.approx(0.10)
    assert ratios["gross_margin"] == pytest.approx(0.60)
    assert ratios["operating_margin"] == pytest.approx(0.30)
    assert ratios["net_margin"] == pytest.approx(0.20)
    # ROIC = NOPAT / (equity + deuda) = 30·(1−0.2) / 150 = 0.16
    assert ratios["roic"] == pytest.approx(0.16)

    # Bloque 4
    assert ratios["current_ratio"] == pytest.approx(2.0)
    assert ratios["quick_ratio"] == pytest.approx(1.5)
    assert ratios["net_debt_to_ebitda"] == pytest.approx((50.0 - 30.0) / 40.0)
    assert ratios["interest_coverage"] == pytest.approx(6.0)

    # Bloque 1
    assert ratios["fcf_yield"] == pytest.approx(25.0 / 1000.0)


def test_dcf_produces_fair_value_and_persists_assumptions():
    dcf = compute_dcf(_info(), _statements(), price=10.0)
    assert dcf["fair_value"] is not None and dcf["fair_value"] > 0
    # WACC = (1000/1050)·(4.2%+1.0·5%) + (50/1050)·(5%·0.79) ≈ 8.95%
    assert dcf["wacc"] == pytest.approx(0.0895, abs=2e-3)
    assumptions = dcf["assumptions"]
    assert assumptions["growth_used"] == pytest.approx(0.10)
    assert assumptions["fcf_base"] == pytest.approx(25.0)
    assert "terminal_growth" in assumptions  # auditabilidad (sección 18)


def test_dcf_handles_missing_fcf():
    info = {k: v for k, v in _info().items() if k != "freeCashflow"}
    financials = _statements()
    financials["cashflow"] = pd.DataFrame()
    dcf = compute_dcf(info, financials, price=10.0)
    assert dcf["fair_value"] is None
    assert dcf["upside"] is None


def test_fundamental_score_regression_strong_company():
    """Regresión (16.6): empresa sólida → todos los umbrales positivos → 100."""
    ratios = {
        "roe": 0.20, "net_margin": 0.20, "current_ratio": 1.5,
        "net_debt_to_ebitda": 1.0, "interest_coverage": 6.0,
        "per": 12.0, "peg": 0.8, "fcf_yield": 0.06, "dcf_upside": 0.30,
    }
    assert fundamental_score(ratios) == 100.0


def test_fundamental_score_regression_weak_company():
    """Empresa débil: todas las penalizaciones → clamp en 0."""
    ratios = {
        "roe": -0.10, "net_margin": -0.05, "current_ratio": 0.8,
        "net_debt_to_ebitda": 5.0, "interest_coverage": 1.0,
        "per": None, "peg": None, "fcf_yield": -0.01, "dcf_upside": -0.50,
    }
    assert fundamental_score(ratios) == 0.0


def test_fundamental_score_neutral_without_data():
    assert fundamental_score({}) == pytest.approx(46.0)  # solo penaliza PER ausente


def test_sync_fundamentals_persists_and_skips_crypto():
    set_provider(FakeProvider(info=_info(), financials=_statements()))

    stock = AssetFactory(ticker="SYNCF")
    ratios = sync_fundamentals(stock)
    assert ratios is not None
    assert ratios.fundamental_score is not None
    assert stock.statements.count() == 3  # income + balance + cashflow

    crypto = AssetFactory(ticker="CRY-USD", asset_type=AssetType.CRYPTO)
    assert sync_fundamentals(crypto) is None  # sección 12
