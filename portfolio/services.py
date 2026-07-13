"""Valorización, rebalanceo y concentración de carteras (4.5, 4.9)."""
import logging
from decimal import Decimal

from django.utils import timezone

from market.models import Asset, AssetType, MarketPrice

logger = logging.getLogger(__name__)

# Sectores considerados "tecnología" y países emergentes para exposición (4.8)
TECH_SECTORS = {"technology", "communication services"}
EMERGING_COUNTRIES = {
    "argentina", "brazil", "bolivia", "chile", "colombia", "mexico", "peru",
    "india", "indonesia", "vietnam", "china", "south africa", "turkey", "nigeria",
}


def current_price_for(asset: Asset) -> Decimal | None:
    """Último cierre persistido. La frescura la garantiza la ingesta periódica."""
    row = (
        MarketPrice.objects.filter(asset=asset)
        .order_by("-datetime")
        .values_list("close", flat=True)
        .first()
    )
    return row


def revalue_portfolio(portfolio) -> dict:
    """Actualiza el snapshot de valorización de cada posición y devuelve el resumen."""
    positions = list(portfolio.positions.select_related("asset"))
    now = timezone.now()

    total_value = Decimal("0")
    total_cost = Decimal("0")
    valued = []
    for pos in positions:
        price = current_price_for(pos.asset)
        if price is None:
            logger.info("Sin precio para %s; posición sin valorizar", pos.asset.ticker)
            continue
        value = pos.quantity * price
        cost = pos.cost_basis
        pos.current_price = price
        pos.current_value = value
        pos.profit_loss = value - cost
        pos.profit_loss_pct = float((value - cost) / cost * 100) if cost else None
        pos.last_valued_at = now
        total_value += value
        total_cost += cost
        valued.append(pos)

    for pos in valued:
        pos.weight = float(pos.current_value / total_value * 100) if total_value else 0.0

    if valued:
        fields = [
            "current_price", "current_value", "weight",
            "profit_loss", "profit_loss_pct", "last_valued_at", "updated_at",
        ]
        type(valued[0]).objects.bulk_update(valued, fields)

    total_pl = total_value - total_cost
    return {
        "portfolio_id": portfolio.id,
        "name": portfolio.name,
        "base_currency": portfolio.base_currency,
        "position_count": len(positions),
        "valued_count": len(valued),
        "total_value": float(total_value),
        "total_cost": float(total_cost),
        "total_profit_loss": float(total_pl),
        "total_profit_loss_pct": float(total_pl / total_cost * 100) if total_cost else None,
        "valued_at": now,
    }


def rebalance_suggestions(portfolio, threshold_pct: float = 1.0) -> dict:
    """Compara pesos actuales vs objetivo y sugiere acciones (4.9).

    Versión simple: no simula impacto fiscal ni comisiones (roadmap V7).
    """
    summary = revalue_portfolio(portfolio)
    total_value = Decimal(str(summary["total_value"]))
    suggestions = []
    targets_sum = 0.0

    for pos in portfolio.positions.select_related("asset"):
        if pos.target_weight is None or pos.weight is None:
            continue
        targets_sum += pos.target_weight
        delta = pos.target_weight - pos.weight
        if abs(delta) < threshold_pct:
            continue
        amount = float(total_value) * delta / 100.0
        suggestions.append(
            {
                "ticker": pos.asset.ticker,
                "current_weight": round(pos.weight, 2),
                "target_weight": pos.target_weight,
                "delta_pct": round(delta, 2),
                "action": "aumentar exposición" if delta > 0 else "reducir exposición",
                "approx_amount": round(amount, 2),
            }
        )

    warning = None
    if suggestions and abs(targets_sum - 100.0) > 0.5:
        warning = f"Los pesos objetivo suman {targets_sum:.1f}%, no 100%."
    return {
        "portfolio_id": portfolio.id,
        "total_value": summary["total_value"],
        "suggestions": sorted(suggestions, key=lambda s: -abs(s["delta_pct"])),
        "warning": warning,
    }


def concentration(portfolio) -> dict:
    """Concentración por activo/sector/país y exposiciones (sección 4.8)."""
    positions = [
        p for p in portfolio.positions.select_related("asset") if p.current_value
    ]
    total = sum(Decimal(p.current_value) for p in positions) if positions else Decimal("0")
    if not total:
        return {
            "by_asset": {}, "by_sector": {}, "by_country": {}, "by_type": {},
            "hhi": None, "crypto_exposure_pct": 0.0, "tech_exposure_pct": 0.0,
            "emerging_exposure_pct": 0.0,
        }

    def add(bucket, key, value):
        key = key or "desconocido"
        bucket[key] = bucket.get(key, 0.0) + value

    by_asset, by_sector, by_country, by_type = {}, {}, {}, {}
    crypto = tech = emerging = 0.0
    for p in positions:
        pct = float(Decimal(p.current_value) / total * 100)
        add(by_asset, p.asset.ticker, pct)
        add(by_sector, p.asset.sector.lower() if p.asset.sector else "", pct)
        add(by_country, p.asset.country.lower() if p.asset.country else "", pct)
        add(by_type, p.asset.asset_type, pct)
        if p.asset.asset_type == AssetType.CRYPTO:
            crypto += pct
        if (p.asset.sector or "").lower() in TECH_SECTORS:
            tech += pct
        if (p.asset.country or "").lower() in EMERGING_COUNTRIES:
            emerging += pct

    hhi = sum((w / 100.0) ** 2 for w in by_asset.values())  # 0-1; >0.25 = concentrada
    return {
        "by_asset": {k: round(v, 2) for k, v in by_asset.items()},
        "by_sector": {k: round(v, 2) for k, v in by_sector.items()},
        "by_country": {k: round(v, 2) for k, v in by_country.items()},
        "by_type": {k: round(v, 2) for k, v in by_type.items()},
        "hhi": round(hhi, 4),
        "crypto_exposure_pct": round(crypto, 2),
        "tech_exposure_pct": round(tech, 2),
        "emerging_exposure_pct": round(emerging, 2),
    }
