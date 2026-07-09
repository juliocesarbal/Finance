"""Modelos del motor de recomendaciones (secciones 5, 15.6 y 15.10)."""
from django.db import models

from core.models import TimeStampedModel


class Signal(models.TextChoices):
    """Tabla de señales de la sección 5.1."""

    STRONG_BUY = "strong_buy", "Compra fuerte"
    MODERATE_BUY = "moderate_buy", "Compra moderada"
    HOLD = "hold", "Mantener / observar"
    HIGH_RISK = "high_risk", "Riesgo alto"
    AVOID = "avoid", "Evitar / venta"


def signal_for_score(score: float) -> str:
    """80-100 compra fuerte / 65-79 moderada / 50-64 mantener /
    35-49 riesgo alto / 0-34 evitar (sección 5.1)."""
    if score >= 80:
        return Signal.STRONG_BUY
    if score >= 65:
        return Signal.MODERATE_BUY
    if score >= 50:
        return Signal.HOLD
    if score >= 35:
        return Signal.HIGH_RISK
    return Signal.AVOID


class Recommendation(TimeStampedModel):
    """Recomendación de la capa mecánica (15.6) con desglose auditable."""

    asset = models.ForeignKey(
        "market.Asset", on_delete=models.CASCADE, related_name="recommendations"
    )
    signal = models.CharField(max_length=20, choices=Signal.choices)
    score = models.FloatField()

    # Desglose por componente (auditabilidad, sección 18)
    technical_score = models.FloatField(null=True)
    news_score = models.FloatField(null=True)
    fundamental_score = models.FloatField(null=True)
    risk_score = models.FloatField(null=True)

    explanation = models.TextField()
    risks = models.TextField()
    evidence_sources = models.ManyToManyField(
        "core.EvidenceSource", blank=True, related_name="recommendations"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.asset.ticker}: {self.get_signal_display()} ({self.score})"


class AgentReview(TimeStampedModel):
    """Veredicto del agente de verificación (5.2, 15.10).

    El score del agente NO reemplaza al mecánico: ambos conviven y su
    divergencia es en sí misma una señal que se muestra al usuario.
    """

    asset = models.ForeignKey(
        "market.Asset", on_delete=models.CASCADE, related_name="agent_reviews"
    )
    mechanical_score = models.FloatField()
    agent_score = models.FloatField()
    confidence = models.FloatField(help_text="0-100")
    signal = models.CharField(max_length=20, choices=Signal.choices)
    justification = models.TextField()
    contradictions_detected = models.JSONField(default=list, blank=True)
    evidence_sources = models.ManyToManyField(
        "core.EvidenceSource", blank=True, related_name="agent_reviews"
    )
    model_used = models.CharField(max_length=100)
    raw_output = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.asset.ticker}: agente {self.agent_score} vs mecánico {self.mechanical_score}"

    @property
    def divergence(self) -> float:
        return round(self.agent_score - self.mechanical_score, 1)
