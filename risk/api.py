"""Endpoints de riesgo."""
from django.shortcuts import get_object_or_404
from ninja import Router

from market.models import Asset

from .services import compute_asset_risk, latest_risk
from .schemas import AssetRiskOut

router = Router()


@router.get("/{ticker}", response=AssetRiskOut)
def asset_risk(request, ticker: str, refresh: bool = False, days: int = 365):
    asset = get_object_or_404(Asset, ticker__iexact=ticker)
    if not refresh:
        metrics = latest_risk(asset)
        if metrics is not None:
            return {
                "ticker": asset.ticker,
                "volatility_annual": metrics.volatility_annual,
                "max_drawdown": metrics.max_drawdown,
                "beta": metrics.beta,
                "correlations": metrics.correlations,
                "risk_score": metrics.risk_score,
                "notes": metrics.notes,
            }
    return compute_asset_risk(asset, days=days)
