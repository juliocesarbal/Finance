"""Endpoints del motor de descubrimiento."""
from django.shortcuts import get_object_or_404
from ninja import Router

from .models import EmergingTopic, OpportunityReport
from .schemas import DiscoveryRunOut, ReportOut, TopicIn, TopicOut
from .services import run_discovery, seed_topics

router = Router()


@router.get("/topics", response=list[TopicOut])
def list_topics(request):
    seed_topics()
    return EmergingTopic.objects.all()


@router.post("/topics", response=TopicOut)
def create_topic(request, payload: TopicIn):
    topic, _ = EmergingTopic.objects.get_or_create(
        name=payload.name,
        defaults=payload.dict(exclude={"name"}),
    )
    return topic


@router.get("/opportunities", response=list[ReportOut])
def list_opportunities(request, min_score: float = 0.0):
    """Últimos reportes por tema, ordenados por score."""
    latest_ids = []
    seen = set()
    for report in OpportunityReport.objects.order_by("topic_id", "-created_at"):
        key = report.topic_id or f"standalone-{report.id}"
        if key not in seen:
            seen.add(key)
            latest_ids.append(report.id)
    qs = (
        OpportunityReport.objects.filter(id__in=latest_ids, score__gte=min_score)
        .prefetch_related("related_assets")
        .order_by("-score")
    )
    return qs


@router.get("/opportunities/{report_id}", response=ReportOut)
def opportunity_detail(request, report_id: int):
    return get_object_or_404(
        OpportunityReport.objects.prefetch_related("related_assets"), id=report_id
    )


@router.post("/scan", response=DiscoveryRunOut)
def scan_now(request):
    """Corre el escaneo completo de temas (puede tardar: descarga RSS)."""
    return run_discovery()
