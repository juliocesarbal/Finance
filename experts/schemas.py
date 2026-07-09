from datetime import datetime

from ninja import Schema


class ConsensusOut(Schema):
    ticker: str
    as_of: datetime
    source: str
    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int
    total_analysts: int
    mean_target: float | None = None
    high_target: float | None = None
    low_target: float | None = None
    median_target: float | None = None
    current_price: float | None = None
    rating_mean: float | None = None
    dispersion: float | None = None
    change_alert: str

    @staticmethod
    def resolve_ticker(obj):
        return obj.asset.ticker


class ExpertIn(Schema):
    name: str
    firm: str = ""
    credentials: str = ""
    regulator_registry: str = ""
    registry_url: str = ""
    methodology: str = ""
    conflicts_of_interest: str = ""


class ExpertOut(Schema):
    id: int
    name: str
    firm: str
    credentials: str
    regulator_registry: str
    registry_url: str
    verified: bool
    verification_notes: str


class MessageOut(Schema):
    detail: str
