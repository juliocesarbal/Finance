"""Modelos transversales: evidencia y confiabilidad de fuentes (secciones 9 y 15.5)."""
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SourceType(models.TextChoices):
    OFFICIAL_FILING = "official_filing", "Reporte oficial / filing (SEC, IR)"
    REGULATOR = "regulator", "Regulador / banco central / organismo"
    INSTITUTIONAL = "institutional", "Banco de inversión / proveedor institucional"
    FINANCIAL_MEDIA = "financial_media", "Medio financiero reconocido"
    INDEPENDENT_ANALYST = "independent_analyst", "Analista independiente verificable"
    SOCIAL = "social", "Redes sociales / foros"
    PROMOTIONAL = "promotional", "Fuente anónima o promocional"


# Nivel y score base por tipo de fuente (tabla de la sección 9)
SOURCE_TYPE_BASE = {
    SourceType.OFFICIAL_FILING: ("A+", 95.0),
    SourceType.REGULATOR: ("A+", 95.0),
    SourceType.INSTITUTIONAL: ("A", 85.0),
    SourceType.FINANCIAL_MEDIA: ("B", 70.0),
    SourceType.INDEPENDENT_ANALYST: ("C", 55.0),
    SourceType.SOCIAL: ("D", 35.0),
    SourceType.PROMOTIONAL: ("E", 15.0),
}


class EvidenceSource(TimeStampedModel):
    """Evidencia que respalda noticias, recomendaciones y reportes (15.5).

    Regla central (sección 18): ninguna fuente se muestra sin su nivel de
    confiabilidad previamente calculado.
    """

    url = models.URLField(max_length=1000, blank=True)
    source_name = models.CharField(max_length=200)
    source_type = models.CharField(
        max_length=30, choices=SourceType.choices, default=SourceType.FINANCIAL_MEDIA
    )
    author = models.CharField(max_length=200, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    retrieved_at = models.DateTimeField(auto_now_add=True)
    related_asset = models.ForeignKey(
        "market.Asset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="evidence_sources",
    )
    relevant_excerpt = models.TextField(blank=True)

    # Factores del score (sección 9), cada uno 0-100. Defaults neutros;
    # se curan a mano vía admin cuando se conoce a la fuente.
    author_credentials = models.FloatField(default=50.0)
    track_record = models.FloatField(default=50.0)
    methodological_transparency = models.FloatField(default=50.0)
    independence = models.FloatField(default=50.0)

    reliability_score = models.FloatField(default=0.0)
    reliability_level = models.CharField(max_length=2, default="E")

    class Meta:
        ordering = ["-retrieved_at"]

    def __str__(self):
        return f"{self.source_name} [{self.reliability_level}]"

    def compute_reliability(self) -> float:
        """Score = 40% tipo de fuente + 20% credenciales + 15% historial
        + 15% transparencia metodológica + 10% independencia (sección 9)."""
        level, type_score = SOURCE_TYPE_BASE[SourceType(self.source_type)]
        score = (
            0.40 * type_score
            + 0.20 * self.author_credentials
            + 0.15 * self.track_record
            + 0.15 * self.methodological_transparency
            + 0.10 * self.independence
        )
        self.reliability_score = round(score, 1)
        self.reliability_level = level
        return self.reliability_score

    def save(self, *args, **kwargs):
        self.compute_reliability()
        super().save(*args, **kwargs)
