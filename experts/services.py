"""Sincronización del consenso de analistas desde yfinance (sección 11)."""
import logging

from django.utils import timezone

from market.models import Asset
from market.providers import get_provider

from .models import AnalystConsensus

logger = logging.getLogger(__name__)

DISPERSION_HIGH = 0.5
RATING_SHIFT_ALERT = 0.4
TARGET_SHIFT_ALERT = 0.10


def _current_period_row(summary_rows: list[dict]) -> dict | None:
    """La fila del mes corriente ('0m') del recommendations_summary."""
    if not summary_rows:
        return None
    for row in summary_rows:
        if str(row.get("period", "")).strip() in ("0m", "0"):
            return row
    return summary_rows[0]


def sync_consensus(asset: Asset) -> AnalystConsensus | None:
    """Persiste un snapshot del consenso y detecta cambios drásticos."""
    try:
        data = get_provider().get_recommendations(asset.ticker) or {}
    except Exception:
        logger.warning("Consenso no disponible para %s", asset.ticker, exc_info=True)
        return None

    row = _current_period_row(data.get("summary") or [])
    targets = data.get("targets") or {}
    if row is None and not targets:
        logger.info("Sin datos de consenso para %s", asset.ticker)
        return None

    def as_int(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    sb = as_int(row.get("strongBuy")) if row else 0
    b = as_int(row.get("buy")) if row else 0
    h = as_int(row.get("hold")) if row else 0
    s = as_int(row.get("sell")) if row else 0
    ss = as_int(row.get("strongSell")) if row else 0
    total = sb + b + h + s + ss

    rating_mean = None
    if total:
        rating_mean = round((1 * sb + 2 * b + 3 * h + 4 * s + 5 * ss) / total, 2)

    def as_float(value):
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    mean_t = as_float(targets.get("mean"))
    high_t = as_float(targets.get("high"))
    low_t = as_float(targets.get("low"))
    dispersion = None
    if mean_t and high_t is not None and low_t is not None:
        dispersion = round((high_t - low_t) / mean_t, 3)

    # Cambios drásticos vs snapshot anterior (alerta de la sección 19 V5)
    previous = asset.consensus_snapshots.order_by("-as_of").first()
    alerts = []
    if previous:
        if (
            rating_mean is not None
            and previous.rating_mean is not None
            and abs(rating_mean - previous.rating_mean) >= RATING_SHIFT_ALERT
        ):
            direction = "mejoró" if rating_mean < previous.rating_mean else "empeoró"
            alerts.append(
                f"El rating promedio {direction}: {previous.rating_mean} → {rating_mean}."
            )
        if (
            mean_t and previous.mean_target
            and abs(mean_t / previous.mean_target - 1.0) >= TARGET_SHIFT_ALERT
        ):
            alerts.append(
                f"Precio objetivo promedio cambió {mean_t / previous.mean_target - 1.0:+.0%}."
            )
    if dispersion is not None and dispersion > DISPERSION_HIGH:
        alerts.append(
            f"Dispersión alta entre analistas ({dispersion:.0%} del precio objetivo promedio)."
        )

    return AnalystConsensus.objects.create(
        asset=asset,
        as_of=timezone.now(),
        strong_buy=sb, buy=b, hold=h, sell=s, strong_sell=ss,
        total_analysts=total,
        mean_target=mean_t,
        high_target=high_t,
        low_target=low_t,
        median_target=as_float(targets.get("median")),
        current_price=as_float(targets.get("current")),
        rating_mean=rating_mean,
        dispersion=dispersion,
        change_alert=" ".join(alerts)[:300],
        raw={"summary_row": row or {}, "targets": targets},
    )


def latest_consensus(asset: Asset) -> AnalystConsensus | None:
    return asset.consensus_snapshots.order_by("-as_of").first()
