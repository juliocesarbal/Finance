"""Endpoints del motor de recomendaciones y ranking (secciones 5.1-5.3)."""
from django.shortcuts import get_object_or_404
from ninja import Router

from market.models import Asset

from .models import AgentReview, Recommendation
from .pipeline import run_universe_scoring
from .schemas import (
    AgentReviewOut,
    MessageOut,
    RankingItemOut,
    RecommendationOut,
    ScoringRunOut,
)

router = Router()


def _latest_per_asset(model, assets=None):
    qs = model.objects.select_related("asset").order_by("asset_id", "-created_at")
    if assets is not None:
        qs = qs.filter(asset__in=assets)
    seen, latest = set(), []
    for row in qs:
        if row.asset_id not in seen:
            seen.add(row.asset_id)
            latest.append(row)
    return latest


@router.get("", response=list[RecommendationOut])
def list_recommendations(request, signal: str | None = None):
    latest = _latest_per_asset(Recommendation)
    if signal:
        latest = [r for r in latest if r.signal == signal]
    return sorted(latest, key=lambda r: -r.score)


@router.get("/ranking", response=list[RankingItemOut])
def ranking(request):
    """Ranking de oportunidades: score mecánico vs ajustado por el agente,
    con su divergencia visible (secciones 5.2 punto 5 y 5.3)."""
    recommendations = _latest_per_asset(Recommendation)
    reviews = {r.asset_id: r for r in _latest_per_asset(AgentReview)}

    items = []
    for rec in recommendations:
        review = reviews.get(rec.asset_id)
        items.append(
            {
                "ticker": rec.asset.ticker,
                "name": rec.asset.name,
                "asset_type": rec.asset.asset_type,
                "mechanical_score": rec.score,
                "mechanical_signal": rec.signal,
                "agent_score": review.agent_score if review else None,
                "agent_signal": review.signal if review else None,
                "agent_confidence": review.confidence if review else None,
                "divergence": review.divergence if review else None,
                "contradictions": review.contradictions_detected if review else None,
                "scored_at": rec.created_at,
            }
        )
    return sorted(items, key=lambda i: -(i["agent_score"] or i["mechanical_score"]))


# Nota: /run debe declararse ANTES que /{ticker} — Django resuelve en orden
# de declaración y "run" matchearía el patrón dinámico (solo GET → 405).
@router.post("/run", response=ScoringRunOut)
def run_scoring(request, escalate: bool = False):
    """Corre la etapa 1 (mecánica) sobre el universo. `escalate=true` encola
    además la etapa 2 (agente) para el top N vía Celery."""
    return run_universe_scoring(escalate=escalate, sync_agent=False)


@router.get("/{ticker}", response={200: RecommendationOut, 404: MessageOut})
def recommendation_detail(request, ticker: str):
    asset = get_object_or_404(Asset, ticker__iexact=ticker)
    rec = asset.recommendations.prefetch_related("evidence_sources").first()
    if rec is None:
        return 404, {"detail": f"Sin recomendación para {asset.ticker}: corré el scoring primero."}
    return 200, rec


@router.get("/{ticker}/agent", response={200: AgentReviewOut, 404: MessageOut})
def agent_review_detail(request, ticker: str):
    asset = get_object_or_404(Asset, ticker__iexact=ticker)
    review = asset.agent_reviews.prefetch_related("evidence_sources").first()
    if review is None:
        return 404, {"detail": f"Sin revisión del agente para {asset.ticker}."}
    return 200, review
