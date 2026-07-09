"""Tareas Celery de ingesta de mercado (disparadas por Celery Beat)."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def ingest_prices_task(period: str = "1y") -> dict:
    from .models import Asset
    from .services import ingest_prices

    results = {"ok": 0, "errors": 0}
    for asset in Asset.objects.filter(is_active=True):
        try:
            ingest_prices(asset, period=period)
            results["ok"] += 1
        except Exception:
            logger.exception("Error ingiriendo precios de %s", asset.ticker)
            results["errors"] += 1
    return results


@shared_task
def compute_indicators_task() -> dict:
    from .models import Asset
    from .services import compute_and_store_indicators

    results = {"ok": 0, "errors": 0}
    for asset in Asset.objects.filter(is_active=True):
        try:
            compute_and_store_indicators(asset)
            results["ok"] += 1
        except Exception:
            logger.exception("Error calculando indicadores de %s", asset.ticker)
            results["errors"] += 1
    return results
