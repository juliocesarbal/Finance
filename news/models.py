"""Modelo de noticias (secciones 4.4 y 15.4)."""
from django.db import models

from core.models import TimeStampedModel


class NewsCategory(models.TextChoices):
    """Categorías de la sección 4.4."""

    EARNINGS = "earnings", "Resultados financieros"
    PRODUCTS = "products", "Nuevos productos"
    REGULATION = "regulation", "Regulación"
    LEGAL = "legal", "Demandas / investigaciones"
    MNA = "mna", "Fusiones y adquisiciones"
    MANAGEMENT = "management", "Cambios de directiva"
    CONTRACTS = "contracts", "Contratos importantes"
    GEOPOLITICS = "geopolitics", "Riesgo geopolítico"
    TECHNOLOGY = "technology", "Innovación tecnológica"
    OTHER = "other", "Otros"


class SentimentLabel(models.TextChoices):
    POSITIVE = "positive", "Positivo"
    NEUTRAL = "neutral", "Neutral"
    NEGATIVE = "negative", "Negativo"


class News(TimeStampedModel):
    """Noticia con sentimiento, impacto y evidencia (15.4)."""

    asset = models.ForeignKey(
        "market.Asset",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="news_items",
    )
    keyword = models.CharField(
        max_length=200, blank=True,
        help_text="Palabra clave de búsqueda para noticias macro/sectoriales sin ticker.",
    )
    title = models.CharField(max_length=500)
    summary = models.TextField(blank=True)
    source = models.CharField(max_length=200, blank=True)
    author = models.CharField(max_length=200, blank=True)
    url = models.TextField(blank=True)
    url_hash = models.CharField(max_length=64, unique=True)
    language = models.CharField(max_length=10, default="en")
    published_at = models.DateTimeField(null=True, blank=True)
    sentiment = models.FloatField(default=0.0, help_text="Compound VADER en [-1, 1].")
    sentiment_label = models.CharField(
        max_length=10, choices=SentimentLabel.choices, default=SentimentLabel.NEUTRAL
    )
    impact_score = models.FloatField(default=0.0, help_text="Impacto estimado 0-100.")
    category = models.CharField(
        max_length=20, choices=NewsCategory.choices, default=NewsCategory.OTHER
    )
    evidence = models.ForeignKey(
        "core.EvidenceSource",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="news_items",
    )

    class Meta:
        ordering = ["-published_at"]
        verbose_name_plural = "news"
        indexes = [
            models.Index(fields=["asset", "-published_at"]),
            models.Index(fields=["category"]),
        ]

    def __str__(self):
        target = self.asset.ticker if self.asset else self.keyword or "macro"
        return f"[{target}] {self.title[:60]}"
