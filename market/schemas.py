from datetime import datetime

from ninja import Schema


class AssetIn(Schema):
    ticker: str
    name: str = ""
    asset_type: str = "stock"
    sector: str = ""
    country: str = ""
    currency: str = "USD"
    exchange: str = ""
    description: str = ""


class AssetOut(Schema):
    id: int
    ticker: str
    name: str
    asset_type: str
    sector: str
    country: str
    currency: str
    exchange: str
    is_active: bool


class PricePointOut(Schema):
    datetime: datetime
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int | None = None


class IndicatorRowOut(Schema):
    datetime: datetime
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    volatility: float | None = None
    relative_volume: float | None = None


class TechnicalSnapshotOut(Schema):
    score: float
    price: float
    signals: list[str]
    support: float | None = None
    resistance: float | None = None
    indicators: dict


class MessageOut(Schema):
    detail: str
