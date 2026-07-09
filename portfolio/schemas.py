from datetime import date, datetime

from ninja import Schema


class PortfolioIn(Schema):
    name: str
    base_currency: str = "USD"


class PositionIn(Schema):
    ticker: str
    quantity: float
    average_price: float
    fees: float = 0.0
    currency: str = "USD"
    purchased_at: date | None = None
    target_weight: float | None = None


class PositionUpdateIn(Schema):
    quantity: float | None = None
    average_price: float | None = None
    fees: float | None = None
    target_weight: float | None = None


class PositionOut(Schema):
    id: int
    ticker: str
    asset_name: str
    asset_type: str
    quantity: float
    average_price: float
    fees: float
    currency: str
    purchased_at: date | None = None
    target_weight: float | None = None
    current_price: float | None = None
    current_value: float | None = None
    weight: float | None = None
    profit_loss: float | None = None
    profit_loss_pct: float | None = None

    @staticmethod
    def resolve_ticker(obj):
        return obj.asset.ticker

    @staticmethod
    def resolve_asset_name(obj):
        return obj.asset.name

    @staticmethod
    def resolve_asset_type(obj):
        return obj.asset.asset_type


class PortfolioOut(Schema):
    id: int
    name: str
    base_currency: str
    created_at: datetime


class PortfolioDetailOut(Schema):
    id: int
    name: str
    base_currency: str
    total_value: float
    total_cost: float
    total_profit_loss: float
    total_profit_loss_pct: float | None = None
    positions: list[PositionOut]


class RebalanceSuggestionOut(Schema):
    ticker: str
    current_weight: float
    target_weight: float
    delta_pct: float
    action: str
    approx_amount: float


class RebalanceOut(Schema):
    portfolio_id: int
    total_value: float
    suggestions: list[RebalanceSuggestionOut]
    warning: str | None = None


class ConcentrationOut(Schema):
    by_asset: dict
    by_sector: dict
    by_country: dict
    by_type: dict
    hhi: float | None = None
    crypto_exposure_pct: float
    tech_exposure_pct: float
    emerging_exposure_pct: float
