"""Tests del simulador (4.6) y backtesting (4.7) con matemática verificable."""
import pytest

from simulation.services import backtest_sma_cross, simulate_investment
from tests.helpers import make_linear_frame

# ------------------------------------------------------------------ simulador

def test_future_value_without_contributions():
    """1000 al 12% anual efectivo por 1 año = 1120 exacto (capitalización mensual
    de la tasa efectiva anual)."""
    result = simulate_investment(1000.0, 0.0, 1.0, 0.12, 0.0)
    assert result["scenarios"]["medio"]["final_value"] == pytest.approx(1120.0)
    assert result["total_contributed"] == pytest.approx(1000.0)


def test_future_value_zero_rate_accumulates_contributions():
    result = simulate_investment(1000.0, 100.0, 1.0, 0.0, 0.0)
    assert result["scenarios"]["medio"]["final_value"] == pytest.approx(2200.0)
    assert result["scenarios"]["medio"]["gain"] == pytest.approx(0.0)


def test_scenarios_are_ordered():
    result = simulate_investment(1000.0, 100.0, 5.0, 0.08, 0.15)
    s = result["scenarios"]
    assert s["pesimista"]["final_value"] < s["medio"]["final_value"] < s["optimista"]["final_value"]


def test_zero_volatility_collapses_scenarios():
    result = simulate_investment(1000.0, 0.0, 3.0, 0.05, 0.0)
    s = result["scenarios"]
    assert s["pesimista"]["final_value"] == s["medio"]["final_value"] == s["optimista"]["final_value"]


def test_simulation_includes_disclaimer():
    """Regla 18: las simulaciones son estimaciones hipotéticas, no garantías."""
    result = simulate_investment(1000.0, 0.0, 1.0, 0.08, 0.1)
    assert "no constituye una garantía" in result["disclaimer"]


# ---------------------------------------------------------------- backtesting

def test_backtest_uptrend_stays_invested_and_profits():
    df = make_linear_frame(n=300, start=100, end=200)
    result = backtest_sma_cross(df, fast=20, slow=50, initial_capital=10_000)
    assert result["final_value"] > 10_000
    assert result["num_trades"] >= 1
    assert result["win_rate_pct"] > 0
    assert result["max_drawdown_pct"] <= 0
    assert result["sharpe_ratio"] > 0
    assert len(result["equity_curve"]) > 10
    assert "no garantiza" in result["disclaimer"]


def test_backtest_requires_enough_history():
    df = make_linear_frame(n=100)
    with pytest.raises(ValueError, match="insuficiente"):
        backtest_sma_cross(df, fast=50, slow=200)


def test_backtest_validates_windows():
    df = make_linear_frame(n=300)
    with pytest.raises(ValueError, match="menor"):
        backtest_sma_cross(df, fast=200, slow=50)


def test_backtest_is_deterministic():
    df = make_linear_frame(n=300, start=100, end=180)
    a = backtest_sma_cross(df, fast=20, slow=50)
    b = backtest_sma_cross(df, fast=20, slow=50)
    assert a["total_return_pct"] == b["total_return_pct"]
    assert a["sharpe_ratio"] == b["sharpe_ratio"]
