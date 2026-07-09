from datetime import datetime

from ninja import Schema


class TopicOut(Schema):
    id: int
    name: str
    query: str
    category: str
    mention_count: int
    momentum: float
    last_scanned_at: datetime | None = None
    is_active: bool


class TopicIn(Schema):
    name: str
    query: str
    category: str = "sector"
    default_horizon: str = "3-5 años"
    description: str = ""


class ReportOut(Schema):
    id: int
    name: str
    opportunity_type: str
    score: float
    score_breakdown: dict
    risk_level: str
    horizon: str
    thesis: str
    risks: str
    conclusion: str
    related_tickers: list[str]
    created_at: datetime

    @staticmethod
    def resolve_related_tickers(obj):
        return [a.ticker for a in obj.related_assets.all()]


class DiscoveryRunOut(Schema):
    scanned: int
    errors: int
    reports: list[dict]
