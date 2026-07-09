"""Endpoints de consenso de analistas y expertos."""
from django.shortcuts import get_object_or_404
from ninja import Router

from market.models import Asset

from .models import Expert
from .schemas import ConsensusOut, ExpertIn, ExpertOut, MessageOut
from .services import latest_consensus, sync_consensus

router = Router()


@router.get("/consensus/{ticker}", response={200: ConsensusOut, 404: MessageOut})
def get_consensus(request, ticker: str, refresh: bool = False):
    asset = get_object_or_404(Asset, ticker__iexact=ticker)
    consensus = None if refresh else latest_consensus(asset)
    if consensus is None:
        consensus = sync_consensus(asset)
    if consensus is None:
        return 404, {"detail": f"Sin consenso de analistas disponible para {asset.ticker}."}
    return 200, consensus


@router.get("/analysts", response=list[ExpertOut])
def list_experts(request, verified: bool | None = None):
    qs = Expert.objects.all()
    if verified is not None:
        qs = qs.filter(verified=verified)
    return qs


@router.post("/analysts", response=ExpertOut)
def create_expert(request, payload: ExpertIn):
    # La verificación (campo `verified`) solo se activa desde el admin
    # tras chequear el registro regulatorio (regla sección 18).
    return Expert.objects.create(**payload.dict())
