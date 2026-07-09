"""Endpoints de análisis fundamental."""
from django.shortcuts import get_object_or_404
from ninja import Router

from market.models import Asset

from .models import FinancialStatement
from .schemas import MessageOut, RatiosOut, StatementOut
from .services import latest_ratios, sync_fundamentals

router = Router()


@router.get("/{ticker}", response={200: RatiosOut, 404: MessageOut})
def get_ratios(request, ticker: str, refresh: bool = False):
    asset = get_object_or_404(Asset, ticker__iexact=ticker)
    ratios = None if refresh else latest_ratios(asset)
    if ratios is None:
        ratios = sync_fundamentals(asset)
    if ratios is None:
        return 404, {
            "detail": (
                "Sin fundamentales disponibles (los criptoactivos no tienen "
                "estados contables; ver sección 12 del documento)."
            )
        }
    return 200, ratios


@router.get("/{ticker}/statements", response=list[StatementOut])
def get_statements(request, ticker: str, statement_type: str | None = None):
    asset = get_object_or_404(Asset, ticker__iexact=ticker)
    qs = FinancialStatement.objects.filter(asset=asset)
    if statement_type:
        qs = qs.filter(statement_type=statement_type)
    return qs
