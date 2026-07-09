from datetime import datetime

from ninja import Schema


class NewsOut(Schema):
    id: int
    title: str
    summary: str
    source: str
    url: str
    category: str
    sentiment: float
    sentiment_label: str
    impact_score: float
    published_at: datetime | None = None
    reliability_level: str | None = None
    reliability_score: float | None = None

    @staticmethod
    def resolve_reliability_level(obj):
        return obj.evidence.reliability_level if obj.evidence else None

    @staticmethod
    def resolve_reliability_score(obj):
        return obj.evidence.reliability_score if obj.evidence else None


class NewsDigestOut(Schema):
    ticker: str
    days: int
    news_score: float
    item_count: int
    top_items: list[NewsOut]


class IngestResultOut(Schema):
    created: int
    detail: str
