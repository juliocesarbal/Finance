from ninja import Schema


class AssetRiskOut(Schema):
    ticker: str
    volatility_annual: float | None = None
    max_drawdown: float | None = None
    beta: float | None = None
    correlations: dict
    risk_score: float | None = None
    notes: list[str]


class MessageOut(Schema):
    detail: str
