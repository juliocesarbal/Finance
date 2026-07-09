"""Modelos de análisis fundamental (sección 4.3).

La sección 15 del documento no definía modelos para fundamentales;
se diseñan aquí: estados financieros crudos + ratios calculados.
"""
from django.db import models

from core.models import TimeStampedModel


class StatementType(models.TextChoices):
    INCOME = "income", "Cuenta de resultados"
    BALANCE = "balance", "Balance"
    CASHFLOW = "cashflow", "Flujo de caja"


class FinancialStatement(TimeStampedModel):
    """Estado financiero anual crudo extraído vía provider (pipeline 4.3)."""

    asset = models.ForeignKey(
        "market.Asset", on_delete=models.CASCADE, related_name="statements"
    )
    statement_type = models.CharField(max_length=10, choices=StatementType.choices)
    period_ending = models.DateField()
    data = models.JSONField(default=dict)

    class Meta:
        ordering = ["-period_ending"]
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "statement_type", "period_ending"],
                name="uniq_statement_asset_type_period",
            ),
        ]

    def __str__(self):
        return f"{self.asset.ticker} {self.statement_type} {self.period_ending}"


class FundamentalRatios(TimeStampedModel):
    """Tablero de 5 bloques (sección 4.3) + score fundamental para la capa 5.1."""

    asset = models.ForeignKey(
        "market.Asset", on_delete=models.CASCADE, related_name="fundamental_ratios"
    )
    as_of = models.DateTimeField()
    price_used = models.FloatField(null=True)

    # Bloque 1 — múltiplos de precio
    per = models.FloatField(null=True)
    forward_per = models.FloatField(null=True)
    peg = models.FloatField(null=True)
    price_to_book = models.FloatField(null=True)
    price_to_sales = models.FloatField(null=True)
    dividend_yield = models.FloatField(null=True, help_text="Fracción, ej. 0.005 = 0.5%")
    fcf_yield = models.FloatField(null=True)

    # Bloque 2 — múltiplos de enterprise value
    enterprise_value = models.FloatField(null=True)
    ev_ebitda = models.FloatField(null=True)
    ev_ebit = models.FloatField(null=True)
    ev_fcf = models.FloatField(null=True)
    ev_sales = models.FloatField(null=True)

    # Bloque 3 — rentabilidad
    roe = models.FloatField(null=True)
    roa = models.FloatField(null=True)
    roic = models.FloatField(null=True)
    gross_margin = models.FloatField(null=True)
    operating_margin = models.FloatField(null=True)
    net_margin = models.FloatField(null=True)

    # Bloque 4 — liquidez y solvencia
    current_ratio = models.FloatField(null=True)
    quick_ratio = models.FloatField(null=True)
    net_debt_to_ebitda = models.FloatField(null=True)
    interest_coverage = models.FloatField(null=True)
    debt_to_equity = models.FloatField(null=True, help_text="Ratio, ej. 1.5")

    # Bloque 5 — valoración intrínseca (DCF/WACC)
    wacc = models.FloatField(null=True)
    dcf_fair_value = models.FloatField(null=True)
    dcf_upside = models.FloatField(null=True, help_text="Fracción vs precio actual")
    dcf_assumptions = models.JSONField(
        default=dict, blank=True,
        help_text="Supuestos explícitos del DCF (auditabilidad, sección 18).",
    )

    fundamental_score = models.FloatField(
        null=True, help_text="Score 0-100 para la capa mecánica (5.1)."
    )

    class Meta:
        ordering = ["-as_of"]
        verbose_name_plural = "fundamental ratios"

    def __str__(self):
        return f"{self.asset.ticker} @ {self.as_of:%Y-%m-%d}"
