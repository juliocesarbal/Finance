"""Modelos de simulación (15.9) y backtesting (4.7)."""
from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class Simulation(TimeStampedModel):
    """Resultado persistido de una simulación de aportes (4.6, 15.9).

    Regla central (sección 18): las simulaciones son estimaciones estadísticas
    hipotéticas, jamás garantías de rendimiento futuro.
    """

    # null: filas anteriores a la autenticación por usuario (sin dueño conocido)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.CASCADE, related_name="simulations",
    )
    portfolio = models.ForeignKey(
        "portfolio.Portfolio", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="simulations",
    )
    asset = models.ForeignKey(
        "market.Asset", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="simulations",
    )
    scenario_name = models.CharField(max_length=100, default="escenario base")
    initial_capital = models.FloatField()
    monthly_contribution = models.FloatField(default=0.0)
    time_horizon_years = models.FloatField()
    expected_return = models.FloatField(help_text="Retorno anual esperado, ej. 0.08")
    volatility = models.FloatField(help_text="Volatilidad anual esperada, ej. 0.15")
    final_estimated_value = models.FloatField(null=True)
    optimistic_value = models.FloatField(null=True)
    pessimistic_value = models.FloatField(null=True)
    total_contributed = models.FloatField(null=True)
    results = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.scenario_name} ({self.time_horizon_years} años)"


class BacktestRun(TimeStampedModel):
    """Resultado de backtesting con las métricas de la tabla 4.7."""

    # null: filas anteriores a la autenticación por usuario (sin dueño conocido)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.CASCADE, related_name="backtests",
    )
    asset = models.ForeignKey(
        "market.Asset", on_delete=models.CASCADE, related_name="backtests"
    )
    strategy = models.CharField(max_length=50, default="sma_cross")
    params = models.JSONField(default=dict, blank=True)
    start_date = models.DateField(null=True)
    end_date = models.DateField(null=True)
    initial_capital = models.FloatField(default=10000.0)
    final_value = models.FloatField(null=True)
    total_return_pct = models.FloatField(null=True)
    cagr_pct = models.FloatField(null=True)
    volatility_pct = models.FloatField(null=True)
    max_drawdown_pct = models.FloatField(null=True)
    win_rate_pct = models.FloatField(null=True)
    sharpe_ratio = models.FloatField(null=True)
    profit_factor = models.FloatField(null=True)
    num_trades = models.IntegerField(default=0)
    equity_curve = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.asset.ticker} {self.strategy} {self.created_at:%Y-%m-%d}"
