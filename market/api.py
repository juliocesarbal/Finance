"""Endpoints del monitor de mercado."""
import logging

from django.shortcuts import get_object_or_404
from ninja import Router

from . import services
from .models import Asset, MarketPrice, TechnicalIndicator
from .schemas import (
    AssetIn,
    AssetOut,
    IndicatorRowOut,
    MessageOut,
    PricePointOut,
    TechnicalSnapshotOut,
)

logger = logging.getLogger(__name__)
router = Router()


@router.get("/assets", response=list[AssetOut])
def list_assets(request, asset_type: str | None = None, active: bool = True):
    qs = Asset.objects.all()
    if active:
        qs = qs.filter(is_active=True)
    if asset_type:
        qs = qs.filter(asset_type=asset_type)
    return qs


@router.post("/assets", response=AssetOut)
def create_asset(request, payload: AssetIn):
    asset, _created = Asset.objects.get_or_create(
        ticker=payload.ticker.upper(),
        defaults=payload.dict(exclude={"ticker"}),
    )
    try:
        services.sync_asset_metadata(asset)
    except Exception:
        logger.warning("Metadatos no sincronizados para %s", asset.ticker, exc_info=True)
    return asset


@router.get("/assets/{ticker}", response=AssetOut)
def get_asset(request, ticker: str):
    return get_object_or_404(Asset, ticker__iexact=ticker)


@router.get("/assets/{ticker}/prices", response=list[PricePointOut])
def get_prices(request, ticker: str, days: int = 365, refresh: bool = False):
    asset = get_object_or_404(Asset, ticker__iexact=ticker)
    if refresh or not MarketPrice.objects.filter(asset=asset).exists():
        try:
            services.ingest_prices(asset)
        except Exception:
            logger.warning("Ingesta en caliente falló para %s", ticker, exc_info=True)
    df = services.load_price_frame(asset, days=days)
    return [
        PricePointOut(
            datetime=ts,
            open=row.get("open"),
            high=row.get("high"),
            low=row.get("low"),
            close=row.get("close"),
            volume=int(row["volume"]) if row.get("volume") == row.get("volume") and row.get("volume") is not None else None,
        )
        for ts, row in df.iterrows()
    ]


@router.get("/assets/{ticker}/indicators", response=list[IndicatorRowOut])
def get_indicators(request, ticker: str, days: int = 180):
    asset = get_object_or_404(Asset, ticker__iexact=ticker)
    if not TechnicalIndicator.objects.filter(asset=asset).exists():
        services.compute_and_store_indicators(asset)
    qs = TechnicalIndicator.objects.filter(asset=asset).order_by("datetime")
    rows = list(qs)
    return rows[-days:] if days else rows


@router.get(
    "/assets/{ticker}/technical",
    response={200: TechnicalSnapshotOut, 404: MessageOut},
)
def get_technical_snapshot(request, ticker: str):
    asset = get_object_or_404(Asset, ticker__iexact=ticker)
    snapshot = services.latest_technical_snapshot(asset)
    if snapshot is None:
        return 404, {"detail": "Histórico insuficiente: ingesta precios primero (mínimo 20 barras)."}
    return 200, snapshot
