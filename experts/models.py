"""Expertos verificables (sección 10) y consenso de analistas (sección 11)."""
from django.db import models

from core.models import TimeStampedModel


class Expert(TimeStampedModel):
    """Analista o institución. Regla central (18): nadie se considera
    certificado sin verificación regulatoria formal — la verificación se
    cura a mano vía Django Admin contra FINRA BrokerCheck / SEC IAPD."""

    name = models.CharField(max_length=200)
    firm = models.CharField(max_length=200, blank=True)
    credentials = models.TextField(blank=True, help_text="CFA, CPA, etc.")
    regulator_registry = models.CharField(
        max_length=100, blank=True, help_text="Ej. FINRA CRD# o registro SEC IAPD."
    )
    registry_url = models.URLField(max_length=500, blank=True)
    verified = models.BooleanField(
        default=False, help_text="Solo True tras verificar el registro regulatorio."
    )
    verification_notes = models.TextField(blank=True)
    disciplinary_history = models.TextField(blank=True)
    methodology = models.TextField(blank=True)
    conflicts_of_interest = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        status = "✓" if self.verified else "sin verificar"
        return f"{self.name} ({self.firm or 'independiente'}) [{status}]"


class AnalystConsensus(TimeStampedModel):
    """Snapshot del consenso de Wall Street (sección 11).

    La dispersión alta es una señal en sí misma: el agente (5.2) debe
    mencionarla en vez de esconderla en un promedio."""

    asset = models.ForeignKey(
        "market.Asset", on_delete=models.CASCADE, related_name="consensus_snapshots"
    )
    as_of = models.DateTimeField()
    source = models.CharField(max_length=50, default="yfinance")

    strong_buy = models.IntegerField(default=0)
    buy = models.IntegerField(default=0)
    hold = models.IntegerField(default=0)
    sell = models.IntegerField(default=0)
    strong_sell = models.IntegerField(default=0)
    total_analysts = models.IntegerField(default=0)

    mean_target = models.FloatField(null=True)
    high_target = models.FloatField(null=True)
    low_target = models.FloatField(null=True)
    median_target = models.FloatField(null=True)
    current_price = models.FloatField(null=True)

    rating_mean = models.FloatField(
        null=True, help_text="1=compra fuerte … 5=venta fuerte."
    )
    dispersion = models.FloatField(
        null=True, help_text="(objetivo máx − mín) / promedio; >0.5 = opiniones muy dispersas."
    )
    change_alert = models.CharField(max_length=300, blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-as_of"]
        verbose_name_plural = "analyst consensus"

    def __str__(self):
        return f"{self.asset.ticker} consenso @ {self.as_of:%Y-%m-%d}"
