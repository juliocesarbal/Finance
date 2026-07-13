"""Endpoints de cartera (CRUD + valorización + rebalanceo).

El router se monta con ``auth=django_auth`` (config/api.py): siempre hay un
``request.user`` autenticado y cada consulta se acota a sus carteras.
"""
from decimal import Decimal

from django.shortcuts import get_object_or_404
from ninja import Router

from market.models import Asset
from market.services import sync_asset_metadata

from . import services
from .models import Portfolio, PortfolioPosition
from .schemas import (
    ConcentrationOut,
    PortfolioDetailOut,
    PortfolioIn,
    PortfolioOut,
    PositionIn,
    PositionOut,
    PositionUpdateIn,
    RebalanceOut,
)

router = Router()


@router.get("", response=list[PortfolioOut])
def list_portfolios(request):
    return Portfolio.objects.filter(user=request.user)


@router.post("", response=PortfolioOut)
def create_portfolio(request, payload: PortfolioIn):
    portfolio, _ = Portfolio.objects.get_or_create(
        user=request.user,
        name=payload.name,
        defaults={"base_currency": payload.base_currency},
    )
    return portfolio


@router.get("/{portfolio_id}", response=PortfolioDetailOut)
def portfolio_detail(request, portfolio_id: int):
    portfolio = get_object_or_404(
        Portfolio, id=portfolio_id, user=request.user
    )
    summary = services.revalue_portfolio(portfolio)
    return {
        "id": portfolio.id,
        "name": portfolio.name,
        "base_currency": portfolio.base_currency,
        "total_value": summary["total_value"],
        "total_cost": summary["total_cost"],
        "total_profit_loss": summary["total_profit_loss"],
        "total_profit_loss_pct": summary["total_profit_loss_pct"],
        "positions": list(portfolio.positions.select_related("asset")),
    }


@router.delete("/{portfolio_id}", response={204: None})
def delete_portfolio(request, portfolio_id: int):
    portfolio = get_object_or_404(
        Portfolio, id=portfolio_id, user=request.user
    )
    portfolio.delete()
    return 204, None


@router.post("/{portfolio_id}/positions", response=PositionOut)
def add_position(request, portfolio_id: int, payload: PositionIn):
    portfolio = get_object_or_404(
        Portfolio, id=portfolio_id, user=request.user
    )
    asset, created = Asset.objects.get_or_create(ticker=payload.ticker.upper())
    if created:
        sync_asset_metadata(asset)
    position, _ = PortfolioPosition.objects.update_or_create(
        portfolio=portfolio,
        asset=asset,
        defaults={
            "quantity": Decimal(str(payload.quantity)),
            "average_price": Decimal(str(payload.average_price)),
            "fees": Decimal(str(payload.fees)),
            "currency": payload.currency,
            "purchased_at": payload.purchased_at,
            "target_weight": payload.target_weight,
        },
    )
    services.revalue_portfolio(portfolio)
    position.refresh_from_db()
    return position


@router.patch("/positions/{position_id}", response=PositionOut)
def update_position(request, position_id: int, payload: PositionUpdateIn):
    position = get_object_or_404(
        PortfolioPosition,
        id=position_id,
        portfolio__user=request.user,
    )
    data = payload.dict(exclude_unset=True)
    for field in ("quantity", "average_price", "fees"):
        if field in data and data[field] is not None:
            setattr(position, field, Decimal(str(data[field])))
    if "target_weight" in data:
        position.target_weight = data["target_weight"]
    position.save()
    services.revalue_portfolio(position.portfolio)
    position.refresh_from_db()
    return position


@router.delete("/positions/{position_id}", response={204: None})
def delete_position(request, position_id: int):
    position = get_object_or_404(
        PortfolioPosition,
        id=position_id,
        portfolio__user=request.user,
    )
    portfolio = position.portfolio
    position.delete()
    services.revalue_portfolio(portfolio)
    return 204, None


@router.get("/{portfolio_id}/rebalance", response=RebalanceOut)
def rebalance(request, portfolio_id: int, threshold: float = 1.0):
    portfolio = get_object_or_404(
        Portfolio, id=portfolio_id, user=request.user
    )
    return services.rebalance_suggestions(portfolio, threshold_pct=threshold)


@router.get("/{portfolio_id}/concentration", response=ConcentrationOut)
def portfolio_concentration(request, portfolio_id: int):
    portfolio = get_object_or_404(
        Portfolio, id=portfolio_id, user=request.user
    )
    services.revalue_portfolio(portfolio)
    return services.concentration(portfolio)
