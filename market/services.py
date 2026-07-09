"""Servicios del monitor de mercado: sincronización de metadatos,
ingesta de precios e indicadores (secciones 4.1 y 4.2)."""
import logging
import math
from decimal import Decimal

import pandas as pd
from django.utils import timezone

from .indicators import compute_indicator_frame, technical_score
from .models import Asset, AssetType, MarketPrice, TechnicalIndicator
from .providers import get_provider

logger = logging.getLogger(__name__)

# quoteType de Yahoo → AssetType propio
QUOTE_TYPE_MAP = {
    "EQUITY": AssetType.STOCK,
    "ETF": AssetType.ETF,
    "MUTUALFUND": AssetType.ETF,
    "INDEX": AssetType.INDEX,
    "CRYPTOCURRENCY": AssetType.CRYPTO,
    "FUTURE": AssetType.COMMODITY,
    "BOND": AssetType.BOND,
}


def sync_asset_metadata(asset: Asset) -> Asset:
    """Completa nombre, tipo, sector, país, etc. desde el provider (best effort)."""
    try:
        info = get_provider().get_info(asset.ticker) or {}
    except Exception:
        logger.warning("No se pudo sincronizar metadatos de %s", asset.ticker, exc_info=True)
        return asset

    asset.name = asset.name or info.get("longName") or info.get("shortName") or ""
    quote_type = (info.get("quoteType") or "").upper()
    if quote_type in QUOTE_TYPE_MAP:
        asset.asset_type = QUOTE_TYPE_MAP[quote_type]
    asset.sector = asset.sector or info.get("sector") or ""
    asset.country = asset.country or info.get("country") or ""
    asset.currency = info.get("currency") or asset.currency
    asset.exchange = asset.exchange or info.get("exchange") or ""
    if not asset.description:
        asset.description = (info.get("longBusinessSummary") or "")[:2000]
    asset.save()
    return asset


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return Decimal(str(round(f, 6)))


def _utc_index(df: pd.DataFrame) -> pd.DataFrame:
    idx = df.index
    if getattr(idx, "tz", None) is not None:
        df = df.tz_convert("UTC")
    else:
        df = df.tz_localize("UTC")
    return df


def ingest_prices(asset: Asset, period: str = "1y", interval: str = "1d") -> int:
    """Descarga histórico diario vía provider y hace upsert en MarketPrice."""
    df = get_provider().get_history(asset.ticker, period=period, interval=interval)
    if df is None or df.empty:
        logger.warning("Sin datos de precios para %s", asset.ticker)
        return 0

    df = _utc_index(df)
    rows = []
    for ts, row in df.iterrows():
        close = _to_decimal(row.get("close"))
        if close is None:
            continue
        volume = row.get("volume")
        volume = int(volume) if volume is not None and not math.isnan(float(volume)) else None
        rows.append(
            MarketPrice(
                asset=asset,
                datetime=ts.to_pydatetime(),
                open=_to_decimal(row.get("open")),
                high=_to_decimal(row.get("high")),
                low=_to_decimal(row.get("low")),
                close=close,
                volume=volume,
            )
        )
    if not rows:
        return 0
    MarketPrice.objects.bulk_create(
        rows,
        update_conflicts=True,
        unique_fields=["asset", "datetime"],
        update_fields=["open", "high", "low", "close", "volume"],
        batch_size=500,
    )
    return len(rows)


def load_price_frame(asset: Asset, days: int | None = None) -> pd.DataFrame:
    """Arma un DataFrame OHLCV desde la base (fuente para pandas)."""
    qs = MarketPrice.objects.filter(asset=asset).order_by("datetime")
    if days:
        qs = qs.filter(datetime__gte=timezone.now() - timezone.timedelta(days=days))
    values = list(qs.values("datetime", "open", "high", "low", "close", "volume"))
    if not values:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(values)
    df = df.set_index("datetime")
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def compute_and_store_indicators(asset: Asset) -> int:
    """Calcula la matriz de indicadores y hace upsert en TechnicalIndicator."""
    df = load_price_frame(asset)
    if len(df) < 20:
        logger.info("Histórico insuficiente para indicadores de %s (%s filas)", asset.ticker, len(df))
        return 0

    frame = compute_indicator_frame(df)
    fields = [
        "sma_20", "sma_50", "sma_200", "rsi", "macd", "macd_signal", "macd_hist",
        "bb_upper", "bb_middle", "bb_lower", "volatility", "relative_volume",
    ]

    def clean(v):
        if v is None:
            return None
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f

    rows = []
    for ts, row in frame.iterrows():
        if clean(row.get("sma_20")) is None:  # aún sin ventana mínima
            continue
        rows.append(
            TechnicalIndicator(
                asset=asset,
                datetime=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                **{f: clean(row.get(f)) for f in fields},
            )
        )
    if not rows:
        return 0
    TechnicalIndicator.objects.bulk_create(
        rows,
        update_conflicts=True,
        unique_fields=["asset", "datetime"],
        update_fields=fields,
        batch_size=500,
    )
    return len(rows)


def latest_technical_snapshot(asset: Asset) -> dict | None:
    """Snapshot técnico actual (score 0-100, señales, soportes) desde la base."""
    df = load_price_frame(asset)
    if len(df) < 20:
        return None
    return technical_score(df)
