"""Simulador de inversiones (4.6) y backtesting (4.7).

Todo determinista: escenarios cerrados (optimista/medio/pesimista) en lugar de
Monte Carlo, y métricas de backtest reproducibles — facilita los tests de
regresión de la sección 16.6.
"""
import math

import numpy as np
import pandas as pd

TRADING_DAYS = 252


# ------------------------------------------------------------------ simulador
def _future_value(initial: float, monthly: float, annual_return: float, years: float) -> float:
    """Valor futuro con capitalización mensual y aportes a fin de mes."""
    months = int(round(years * 12))
    if annual_return <= -1.0:
        return 0.0
    r_m = (1.0 + annual_return) ** (1.0 / 12.0) - 1.0
    fv = initial * (1.0 + r_m) ** months
    if monthly and months > 0:
        if abs(r_m) < 1e-12:
            fv += monthly * months
        else:
            fv += monthly * (((1.0 + r_m) ** months - 1.0) / r_m)
    return fv


def simulate_investment(
    initial_capital: float,
    monthly_contribution: float,
    years: float,
    expected_return: float,
    volatility: float,
) -> dict:
    """Escenarios medio (r), optimista (r+vol) y pesimista (r−vol) — sección 4.6."""
    total_contributed = initial_capital + monthly_contribution * int(round(years * 12))

    scenarios = {}
    for name, rate in (
        ("pesimista", expected_return - volatility),
        ("medio", expected_return),
        ("optimista", expected_return + volatility),
    ):
        fv = _future_value(initial_capital, monthly_contribution, rate, years)
        gain = fv - total_contributed
        cumulative_pct = (fv / total_contributed - 1.0) * 100 if total_contributed else 0.0
        annualized_pct = (
            ((fv / total_contributed) ** (1.0 / years) - 1.0) * 100
            if total_contributed and years > 0 and fv > 0
            else None
        )
        scenarios[name] = {
            "annual_return_used": round(rate, 4),
            "final_value": round(fv, 2),
            "gain": round(gain, 2),
            "cumulative_return_pct": round(cumulative_pct, 2),
            # Aproximación sobre el total aportado (los aportes mensuales
            # entran a lo largo del tiempo, no el día uno).
            "approx_annualized_return_pct": round(annualized_pct, 2) if annualized_pct is not None else None,
        }

    return {
        "initial_capital": initial_capital,
        "monthly_contribution": monthly_contribution,
        "years": years,
        "expected_return": expected_return,
        "volatility": volatility,
        "total_contributed": round(total_contributed, 2),
        "scenarios": scenarios,
        "disclaimer": (
            "Estimación estadística hipotética basada en supuestos de retorno "
            "y volatilidad; no constituye una garantía de rendimiento futuro."
        ),
    }


# ---------------------------------------------------------------- backtesting
def _max_drawdown(equity: pd.Series) -> float:
    """Máxima caída desde un máximo, como fracción negativa (ej. -0.35)."""
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return float(drawdown.min()) if len(drawdown) else 0.0


def _trades_from_positions(position: pd.Series, close: pd.Series) -> list[dict]:
    """Reconstruye operaciones (entrada→salida) desde la serie de posición 0/1."""
    trades = []
    entry_price = None
    entry_date = None
    prev = 0
    for date, pos in position.items():
        price = float(close.loc[date])
        if pos == 1 and prev == 0:
            entry_price, entry_date = price, date
        elif pos == 0 and prev == 1 and entry_price:
            trades.append(
                {
                    "entry_date": str(getattr(entry_date, "date", lambda: entry_date)()),
                    "exit_date": str(getattr(date, "date", lambda: date)()),
                    "return_pct": (price / entry_price - 1.0) * 100,
                }
            )
            entry_price = None
        prev = pos
    if entry_price is not None:  # posición abierta al final
        last_date = position.index[-1]
        price = float(close.iloc[-1])
        trades.append(
            {
                "entry_date": str(getattr(entry_date, "date", lambda: entry_date)()),
                "exit_date": str(getattr(last_date, "date", lambda: last_date)()),
                "return_pct": (price / entry_price - 1.0) * 100,
            }
        )
    return trades


def backtest_sma_cross(
    df: pd.DataFrame,
    fast: int = 50,
    slow: int = 200,
    initial_capital: float = 10000.0,
) -> dict:
    """Backtest de cruce de medias: long cuando SMA(fast) > SMA(slow), si no cash.

    Devuelve las 7 métricas de la tabla 4.7 + curva de equity downsampleada.
    """
    if fast >= slow:
        raise ValueError("`fast` debe ser menor que `slow`")
    close = df["close"].astype(float)
    if len(close) < slow + 10:
        raise ValueError(
            f"Histórico insuficiente: se necesitan al menos {slow + 10} barras, hay {len(close)}."
        )

    sma_fast = close.rolling(fast).mean()
    sma_slow = close.rolling(slow).mean()
    position = (sma_fast > sma_slow).astype(int)
    position = position.where(~sma_slow.isna(), 0)

    daily_returns = close.pct_change(fill_method=None).fillna(0.0)
    strategy_returns = daily_returns * position.shift(1).fillna(0)

    equity = initial_capital * (1.0 + strategy_returns).cumprod()
    final_value = float(equity.iloc[-1])
    total_return = final_value / initial_capital - 1.0

    n_days = len(strategy_returns)
    years = n_days / TRADING_DAYS
    cagr = (final_value / initial_capital) ** (1.0 / years) - 1.0 if years > 0 and final_value > 0 else 0.0
    vol = float(strategy_returns.std() * math.sqrt(TRADING_DAYS))
    mean_daily = float(strategy_returns.mean())
    std_daily = float(strategy_returns.std())
    sharpe = (mean_daily / std_daily * math.sqrt(TRADING_DAYS)) if std_daily > 0 else 0.0

    trades = _trades_from_positions(position, close)
    wins = [t for t in trades if t["return_pct"] > 0]
    losses = [t for t in trades if t["return_pct"] <= 0]
    win_rate = (len(wins) / len(trades) * 100) if trades else 0.0
    gross_gain = sum(t["return_pct"] for t in wins)
    gross_loss = abs(sum(t["return_pct"] for t in losses))
    profit_factor = (gross_gain / gross_loss) if gross_loss > 0 else (None if not wins else float("inf"))

    # Curva downsampleada (máx ~200 puntos) para el dashboard
    step = max(1, len(equity) // 200)
    curve = [
        [str(getattr(idx, "date", lambda: idx)()), round(float(val), 2)]
        for idx, val in equity.iloc[::step].items()
    ]

    return {
        "strategy": "sma_cross",
        "params": {"fast": fast, "slow": slow},
        "start_date": str(getattr(close.index[0], "date", lambda: close.index[0])()),
        "end_date": str(getattr(close.index[-1], "date", lambda: close.index[-1])()),
        "initial_capital": initial_capital,
        "final_value": round(final_value, 2),
        "total_return_pct": round(total_return * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "volatility_pct": round(vol * 100, 2),
        "max_drawdown_pct": round(_max_drawdown(equity) * 100, 2),
        "win_rate_pct": round(win_rate, 2),
        "sharpe_ratio": round(sharpe, 3),
        "profit_factor": round(profit_factor, 3) if profit_factor not in (None, float("inf")) else profit_factor,
        "num_trades": len(trades),
        "equity_curve": curve,
        "disclaimer": (
            "Resultado histórico simulado; el rendimiento pasado no garantiza "
            "resultados futuros."
        ),
    }
