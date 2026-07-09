"""Métricas de riesgo por activo (sección 4.8)."""
from django.db import models

from core.models import TimeStampedModel


class AssetRiskMetrics(TimeStampedModel):
    """Snapshot de riesgo de un activo. `risk_score` en 0-100 donde
    100 = riesgo bajo (así suma positivo en la fórmula 5.1)."""

    asset = models.ForeignKey(
        "market.Asset", on_delete=models.CASCADE, related_name="risk_metrics"
    )
    as_of = models.DateTimeField()
    lookback_days = models.IntegerField(default=365)
    volatility_annual = models.FloatField(null=True, help_text="Fracción, ej. 0.25")
    max_drawdown = models.FloatField(null=True, help_text="Fracción negativa, ej. -0.35")
    beta = models.FloatField(null=True, help_text="Beta vs benchmark (SPY)")
    benchmark = models.CharField(max_length=20, default="SPY")
    correlations = models.JSONField(default=dict, blank=True)
    risk_score = models.FloatField(null=True)
    notes = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-as_of"]
        verbose_name_plural = "asset risk metrics"

    def __str__(self):
        return f"{self.asset.ticker} riesgo @ {self.as_of:%Y-%m-%d}"
