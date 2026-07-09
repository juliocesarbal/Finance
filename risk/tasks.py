"""Tarea Celery de recálculo de riesgo (diaria, tras la ingesta de precios)."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def compute_risk_task() -> dict:
    from market.models import Asset

    from .services import compute_asset_risk

    results = {"ok": 0, "errors": 0}
    for asset in Asset.objects.filter(is_active=True):
        try:
            compute_asset_risk(asset)
            results["ok"] += 1
        except Exception:
            logger.exception("Error calculando riesgo de %s", asset.ticker)
            results["errors"] += 1
    return results
