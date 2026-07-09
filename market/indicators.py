"""Indicadores técnicos sobre cierres históricos (sección 4.2).

Todo es determinista: mismas entradas → mismos valores, cubierto por
tests de regresión (sección 16.6).
"""
import math

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """RSI de Wilder (media móvil exponencial con alpha=1/window)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / window, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, min_periods=window).mean()
    rs = avg_gain / avg_loss
    out = 100.0 - 100.0 / (1.0 + rs)
    # Sin pérdidas en la ventana → RSI 100
    out = out.where(avg_loss != 0, 100.0)
    out[avg_gain.isna() | avg_loss.isna()] = np.nan
    return out


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Devuelve (línea MACD, señal, histograma)."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    line = ema_fast - ema_slow
    sig = line.ewm(span=signal, adjust=False).mean()
    return line, sig, line - sig


def compute_indicator_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula todos los indicadores de la tabla 4.2 sobre un OHLCV.

    `df` requiere columnas close y volume (open/high/low opcionales).
    """
    close = df["close"].astype(float)
    volume = df["volume"].astype(float) if "volume" in df.columns else pd.Series(np.nan, index=df.index)

    out = pd.DataFrame(index=df.index)
    out["sma_20"] = close.rolling(20).mean()
    out["sma_50"] = close.rolling(50).mean()
    out["sma_200"] = close.rolling(200).mean()
    out["rsi"] = rsi(close)
    line, sig, hist = macd(close)
    out["macd"], out["macd_signal"], out["macd_hist"] = line, sig, hist
    std20 = close.rolling(20).std()
    out["bb_middle"] = out["sma_20"]
    out["bb_upper"] = out["sma_20"] + 2.0 * std20
    out["bb_lower"] = out["sma_20"] - 2.0 * std20
    returns = close.pct_change(fill_method=None)
    out["volatility"] = returns.rolling(20).std() * math.sqrt(TRADING_DAYS)
    out["relative_volume"] = volume / volume.rolling(20).mean()
    return out


def support_resistance(df: pd.DataFrame, window: int = 20) -> tuple[float | None, float | None]:
    """Zonas de reacción simples: mínimo/máximo de las últimas `window` barras."""
    if len(df) < window:
        return None, None
    low_col = df["low"] if "low" in df.columns else df["close"]
    high_col = df["high"] if "high" in df.columns else df["close"]
    support = float(low_col.tail(window).min())
    resistance = float(high_col.tail(window).max())
    return support, resistance


def _last_valid(series: pd.Series) -> float | None:
    if series is None or series.dropna().empty:
        return None
    return float(series.dropna().iloc[-1])


def technical_score(df: pd.DataFrame, indicators: pd.DataFrame | None = None) -> dict:
    """Score técnico 0-100 según la regla de señal positiva de la sección 4.2.

    Base 50 (neutro) ajustada por:
    - precio vs SMA50 (±12), SMA50 vs SMA200 (±12)
    - RSI saludable 45-70 (+8), sobrecompra >75 (−10), sobreventa <30 (−6)
    - volumen relativo > 1 (+8)
    - histograma MACD positivo/negativo (±5)
    """
    if indicators is None:
        indicators = compute_indicator_frame(df)

    price = float(df["close"].astype(float).iloc[-1])
    sma_50 = _last_valid(indicators["sma_50"])
    sma_200 = _last_valid(indicators["sma_200"])
    rsi_val = _last_valid(indicators["rsi"])
    rel_vol = _last_valid(indicators["relative_volume"])
    macd_hist = _last_valid(indicators["macd_hist"])

    score = 50.0
    signals: list[str] = []

    if sma_50 is not None:
        if price > sma_50:
            score += 12
            signals.append("Precio por encima de la SMA50 (tendencia de medio plazo positiva)")
        else:
            score -= 12
            signals.append("Precio por debajo de la SMA50 (tendencia de medio plazo débil)")

    if sma_50 is not None and sma_200 is not None:
        if sma_50 > sma_200:
            score += 12
            signals.append("SMA50 sobre SMA200 (estructura alcista de largo plazo)")
        else:
            score -= 12
            signals.append("SMA50 bajo SMA200 (estructura bajista de largo plazo)")
    elif sma_200 is None:
        signals.append("Histórico insuficiente para SMA200 (menos de 200 barras)")

    if rsi_val is not None:
        if 45 <= rsi_val <= 70:
            score += 8
            signals.append(f"RSI saludable ({rsi_val:.0f})")
        elif rsi_val > 75:
            score -= 10
            signals.append(f"RSI en sobrecompra ({rsi_val:.0f})")
        elif rsi_val < 30:
            score -= 6
            signals.append(f"RSI en sobreventa ({rsi_val:.0f})")

    if rel_vol is not None and rel_vol > 1.0:
        score += 8
        signals.append("Volumen actual por encima del promedio de 20 días")

    if macd_hist is not None:
        if macd_hist > 0:
            score += 5
            signals.append("Momentum MACD positivo")
        else:
            score -= 5
            signals.append("Momentum MACD negativo")

    support, resistance = support_resistance(df)
    score = max(0.0, min(100.0, score))

    return {
        "score": round(score, 1),
        "price": price,
        "signals": signals,
        "support": support,
        "resistance": resistance,
        "indicators": {
            "sma_20": _last_valid(indicators["sma_20"]),
            "sma_50": sma_50,
            "sma_200": sma_200,
            "rsi": rsi_val,
            "macd": _last_valid(indicators["macd"]),
            "macd_hist": macd_hist,
            "bb_upper": _last_valid(indicators["bb_upper"]),
            "bb_lower": _last_valid(indicators["bb_lower"]),
            "volatility": _last_valid(indicators["volatility"]),
            "relative_volume": rel_vol,
        },
    }
