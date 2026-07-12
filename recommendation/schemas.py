from datetime import datetime

from ninja import Schema


class EvidenceOut(Schema):
    id: int
    source_name: str
    source_type: str
    url: str
    reliability_level: str
    reliability_score: float
    published_at: datetime | None = None
    retrieved_at: datetime


class RecommendationOut(Schema):
    id: int
    ticker: str
    signal: str
    score: float
    technical_score: float | None = None
    news_score: float | None = None
    fundamental_score: float | None = None
    risk_score: float | None = None
    explanation: str
    risks: str
    created_at: datetime
    evidence_sources: list[EvidenceOut]

    @staticmethod
    def resolve_ticker(obj):
        return obj.asset.ticker


class AgentReviewOut(Schema):
    id: int
    ticker: str
    mechanical_score: float
    agent_score: float
    divergence: float
    confidence: float
    signal: str
    justification: str
    contradictions_detected: list
    model_used: str
    created_at: datetime
    evidence_sources: list[EvidenceOut]

    @staticmethod
    def resolve_ticker(obj):
        return obj.asset.ticker


class RankingItemOut(Schema):
    ticker: str
    name: str
    asset_type: str
    mechanical_score: float
    mechanical_signal: str
    agent_score: float | None = None
    agent_signal: str | None = None
    agent_confidence: float | None = None
    divergence: float | None = None
    contradictions: list | None = None
    scored_at: datetime


class ScoringRunOut(Schema):
    scored: int
    errors: int
    escalated: list[str]
    note: str | None = None
    ranking: list[dict]


class MessageOut(Schema):
    detail: str
