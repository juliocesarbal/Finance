"""Modelos del motor de descubrimiento (secciones 6, 13 y 14)."""
from django.db import models

from core.models import TimeStampedModel


class RiskLevel(models.TextChoices):
    LOW = "low", "Bajo"
    MEDIUM = "medium", "Medio"
    HIGH = "high", "Alto"
    VERY_HIGH = "very_high", "Muy alto"
    EXTREME = "extreme", "Extremo / especulativo"


class OpportunityType(models.TextChoices):
    SECTOR = "sector", "Sector emergente"
    COMPANY = "company", "Empresa en crecimiento"
    CRYPTO = "crypto", "Criptoactivo / protocolo"
    COUNTRY = "country", "País / macro"
    COMMODITY = "commodity", "Commodity"
    ETF = "etf", "ETF nuevo"
    TECHNOLOGY = "technology", "Tecnología"
    REGULATION = "regulation", "Cambio regulatorio"


class EmergingTopic(TimeStampedModel):
    """Tema/nicho monitoreado vía búsquedas avanzadas en Google News RSS."""

    name = models.CharField(max_length=150, unique=True)
    query = models.CharField(
        max_length=300,
        help_text='Búsqueda avanzada, ej. "quantum computing" AND investment',
    )
    category = models.CharField(
        max_length=20, choices=OpportunityType.choices, default=OpportunityType.SECTOR
    )
    default_horizon = models.CharField(max_length=50, default="3-5 años")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    mention_count = models.IntegerField(default=0)
    previous_mention_count = models.IntegerField(default=0)
    momentum = models.FloatField(default=0.0, help_text="Variación relativa de menciones")
    last_scanned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class OpportunityReport(TimeStampedModel):
    """Reporte de oportunidad emergente (estructura de la sección 14)."""

    topic = models.ForeignKey(
        EmergingTopic, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="reports",
    )
    name = models.CharField(max_length=200)
    opportunity_type = models.CharField(
        max_length=20, choices=OpportunityType.choices, default=OpportunityType.SECTOR
    )
    related_assets = models.ManyToManyField(
        "market.Asset", blank=True, related_name="opportunity_reports"
    )
    thesis = models.TextField()
    evidence = models.ManyToManyField(
        "core.EvidenceSource", blank=True, related_name="opportunity_reports"
    )
    risks = models.TextField()
    horizon = models.CharField(max_length=50)
    risk_level = models.CharField(
        max_length=20, choices=RiskLevel.choices, default=RiskLevel.HIGH
    )
    score = models.FloatField(help_text="Emerging Market Score 0-100 (sección 13)")
    score_breakdown = models.JSONField(default=dict, blank=True)
    conclusion = models.TextField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.score})"
