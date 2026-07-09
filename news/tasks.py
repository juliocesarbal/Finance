"""Tareas Celery de ingesta de noticias (Celery Beat cada hora)."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)

# Consultas macro/sectoriales fijas (ampliables desde discovery)
MACRO_QUERIES = [
    ("stock market outlook", "en", "US"),
    ("federal reserve interest rates", "en", "US"),
    ("mercados financieros latinoamérica", "es", "AR"),
]


@shared_task
def ingest_news_task() -> dict:
    from market.models import Asset

    from .services import ingest_asset_news, ingest_rss_for_query

    results = {"assets": 0, "created": 0, "errors": 0}
    for asset in Asset.objects.filter(is_active=True):
        try:
            created = ingest_asset_news(asset)
            query = f'"{asset.name}" stock' if asset.name else f"{asset.ticker} stock"
            created += ingest_rss_for_query(query, asset=asset)
            results["assets"] += 1
            results["created"] += created
        except Exception:
            logger.exception("Error ingiriendo noticias de %s", asset.ticker)
            results["errors"] += 1

    for query, lang, country in MACRO_QUERIES:
        try:
            results["created"] += ingest_rss_for_query(query, lang=lang, country=country)
        except Exception:
            logger.exception("Error en query macro %r", query)
            results["errors"] += 1
    return results
