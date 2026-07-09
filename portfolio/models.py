"""Modelos de cartera (secciones 4.5, 15.7 y 15.8)."""
from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class Portfolio(TimeStampedModel):
    """Cartera del usuario (15.7)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="portfolios"
    )
    name = models.CharField(max_length=100)
    base_currency = models.CharField(max_length=10, default="USD")

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["user", "name"], name="uniq_portfolio_user_name"),
        ]

    def __str__(self):
        return self.name


class PortfolioPosition(TimeStampedModel):
    """Posición dentro de una cartera (15.8). Los campos de valorización son
    snapshots que actualiza el servicio de revalorización."""

    portfolio = models.ForeignKey(
        Portfolio, on_delete=models.CASCADE, related_name="positions"
    )
    asset = models.ForeignKey(
        "market.Asset", on_delete=models.PROTECT, related_name="positions"
    )
    quantity = models.DecimalField(max_digits=24, decimal_places=8)
    average_price = models.DecimalField(max_digits=20, decimal_places=6)
    fees = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    currency = models.CharField(max_length=10, default="USD")
    purchased_at = models.DateField(null=True, blank=True)
    target_weight = models.FloatField(
        null=True, blank=True,
        help_text="Peso objetivo %% para rebalanceo (sección 4.9).",
    )

    # Snapshot de valorización
    current_price = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    current_value = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    weight = models.FloatField(null=True, blank=True)
    profit_loss = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    profit_loss_pct = models.FloatField(null=True, blank=True)
    last_valued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["asset__ticker"]
        constraints = [
            models.UniqueConstraint(
                fields=["portfolio", "asset"], name="uniq_position_portfolio_asset"
            ),
        ]

    def __str__(self):
        return f"{self.portfolio.name}: {self.quantity} {self.asset.ticker}"

    @property
    def cost_basis(self):
        return self.quantity * self.average_price + self.fees
