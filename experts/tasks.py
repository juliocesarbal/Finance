"""Tarea Celery de sincronización de consenso (diaria)."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def sync_consensus_task() -> dict:
    from market.models import Asset, AssetType

    from .services import sync_consensus

    results = {"ok": 0, "skipped": 0, "errors": 0}
    for asset in Asset.objects.filter(is_active=True):
        if asset.asset_type == AssetType.CRYPTO:
            results["skipped"] += 1  # sin cobertura de analistas tradicional
            continue
        try:
            sync_consensus(asset)
            results["ok"] += 1
        except Exception:
            logger.exception("Error sincronizando consenso de %s", asset.ticker)
            results["errors"] += 1
    return results
