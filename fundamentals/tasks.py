"""Tarea Celery de sincronización de fundamentales (diaria)."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def sync_fundamentals_task() -> dict:
    from market.models import Asset, AssetType

    from .services import sync_fundamentals

    results = {"ok": 0, "skipped": 0, "errors": 0}
    for asset in Asset.objects.filter(is_active=True):
        if asset.asset_type == AssetType.CRYPTO:
            results["skipped"] += 1
            continue
        try:
            sync_fundamentals(asset)
            results["ok"] += 1
        except Exception:
            logger.exception("Error en fundamentales de %s", asset.ticker)
            results["errors"] += 1
    return results
