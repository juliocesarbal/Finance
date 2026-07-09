"""Tests de indicadores técnicos (4.2) con valores verificables a mano."""
import numpy as np
import pandas as pd
import pytest

from market.indicators import (
    compute_indicator_frame,
    macd,
    rsi,
    support_resistance,
    technical_score,
)
from tests.helpers import make_linear_frame, make_price_frame


def test_sma_exact_values():
    close = pd.Series([1.0] * 19 + [21.0] + [1.0] * 40)
    df = pd.DataFrame({"close": close, "volume": [100] * 60})
    frame = compute_indicator_frame(df)
    # SMA20 en la posición 19: (19*1 + 21) / 20 = 2.0
    assert frame["sma_20"].iloc[19] == pytest.approx(2.0)
    # Antes de la ventana mínima no hay valor
    assert np.isnan(frame["sma_20"].iloc[18])


def test_rsi_extremes():
    rising = pd.Series(np.linspace(100, 200, 60))
    falling = pd.Series(np.linspace(200, 100, 60))
    assert rsi(rising).iloc[-1] == pytest.approx(100.0)
    assert rsi(falling).iloc[-1] == pytest.approx(0.0, abs=1e-6)


def test_macd_sign_follows_trend():
    rising = pd.Series(np.linspace(100, 200, 120))
    line, signal, hist = macd(rising)
    assert line.iloc[-1] > 0
    falling = pd.Series(np.linspace(200, 100, 120))
    line_f, _, _ = macd(falling)
    assert line_f.iloc[-1] < 0


def test_support_resistance_uses_last_window():
    df = make_linear_frame(n=100, start=100, end=200)
    support, resistance = support_resistance(df, window=20)
    assert support == pytest.approx(float(df["low"].tail(20).min()))
    assert resistance == pytest.approx(float(df["high"].tail(20).max()))


def test_technical_score_uptrend_regression():
    """Regresión (16.6): tendencia lineal alcista con volumen constante.

    Componentes verificables a mano:
      +12 precio > SMA50, +12 SMA50 > SMA200, −10 RSI=100 (sobrecompra),
      +0 volumen relativo == 1, +5 MACD positivo → 50+19 = 69.
    """
    df = make_linear_frame(n=260, start=100, end=200)
    result = technical_score(df)
    assert result["score"] == pytest.approx(69.0)


def test_technical_score_downtrend_regression():
    """Bajista lineal: −12 −12 −6 (RSI=0 sobreventa) −5 MACD → 15."""
    df = make_linear_frame(n=260, start=200, end=100)
    result = technical_score(df)
    assert result["score"] == pytest.approx(15.0)


def test_technical_score_volume_confirmation():
    """El mismo alcista con volumen final 3x promedio suma +8 → 77."""
    df = make_linear_frame(n=260, start=100, end=200)
    df.iloc[-1, df.columns.get_loc("volume")] = 6_000_000
    result = technical_score(df)
    assert result["score"] == pytest.approx(77.0)


def test_technical_score_is_deterministic():
    df = make_price_frame(seed=7)
    assert technical_score(df)["score"] == technical_score(df)["score"]
    assert 0.0 <= technical_score(df)["score"] <= 100.0
