"""Series de precios deterministas y utilidades comunes de test."""
from decimal import Decimal

import numpy as np
import pandas as pd

from market.models import MarketPrice


def _recent_index(n: int) -> pd.DatetimeIndex:
    """Días hábiles que terminan hoy: mantiene los datos dentro de las
    ventanas de lookback (ej. riesgo usa los últimos 365 días)."""
    end = pd.Timestamp.now(tz="UTC").normalize()
    return pd.bdate_range(end=end, periods=n)


def make_price_frame(
    n: int = 260,
    start: float = 100.0,
    drift: float = 0.0005,
    vol: float = 0.01,
    seed: int = 42,
) -> pd.DataFrame:
    """OHLCV determinista (random walk geométrico con semilla fija)."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, vol, n)
    close = start * np.cumprod(1.0 + returns)
    idx = _recent_index(n)
    volume = rng.integers(1_000_000, 5_000_000, n)
    return pd.DataFrame(
        {
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": volume,
        },
        index=idx,
    )


def make_linear_frame(
    n: int = 260,
    start: float = 100.0,
    end: float = 200.0,
    volume: int = 2_000_000,
) -> pd.DataFrame:
    """Serie lineal (100% determinista, componentes verificables a mano)."""
    close = np.linspace(start, end, n)
    idx = _recent_index(n)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
            "volume": np.full(n, volume),
        },
        index=idx,
    )


def store_prices(asset, df: pd.DataFrame) -> int:
    """Persiste un DataFrame OHLCV como filas de MarketPrice."""
    rows = [
        MarketPrice(
            asset=asset,
            datetime=ts.to_pydatetime(),
            open=Decimal(str(round(float(row["open"]), 6))),
            high=Decimal(str(round(float(row["high"]), 6))),
            low=Decimal(str(round(float(row["low"]), 6))),
            close=Decimal(str(round(float(row["close"]), 6))),
            volume=int(row["volume"]),
        )
        for ts, row in df.iterrows()
    ]
    MarketPrice.objects.bulk_create(rows, batch_size=500)
    return len(rows)
