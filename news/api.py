"""Endpoints de noticias y sentimiento."""
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router

from market.models import Asset

from . import services
from .models import News
from .schemas import IngestResultOut, NewsDigestOut, NewsOut

router = Router()


@router.get("", response=list[NewsOut])
def list_news(
    request,
    ticker: str | None = None,
    category: str | None = None,
    days: int = 30,
    limit: int = 50,
):
    qs = News.objects.select_related("evidence").all()
    if ticker:
        qs = qs.filter(asset__ticker__iexact=ticker)
    if category:
        qs = qs.filter(category=category)
    if days:
        qs = qs.filter(published_at__gte=timezone.now() - timezone.timedelta(days=days))
    return qs[: min(limit, 200)]


@router.get("/digest/{ticker}", response=NewsDigestOut)
def news_digest(request, ticker: str, days: int = 14, top: int = 5):
    asset = get_object_or_404(Asset, ticker__iexact=ticker)
    score, count = services.news_score(asset, days=days)
    since = timezone.now() - timezone.timedelta(days=days)
    top_items = (
        News.objects.filter(asset=asset, published_at__gte=since)
        .select_related("evidence")
        .order_by("-impact_score")[:top]
    )
    return {
        "ticker": asset.ticker,
        "days": days,
        "news_score": score,
        "item_count": count,
        "top_items": list(top_items),
    }


@router.post("/ingest/{ticker}", response=IngestResultOut)
def ingest_for_ticker(request, ticker: str, include_rss: bool = True):
    asset = get_object_or_404(Asset, ticker__iexact=ticker)
    created = services.ingest_asset_news(asset)
    if include_rss:
        query = f'"{asset.name}" stock' if asset.name else f"{asset.ticker} stock"
        created += services.ingest_rss_for_query(query, asset=asset)
    return {"created": created, "detail": f"Noticias nuevas para {asset.ticker}: {created}"}
