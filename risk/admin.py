from django.contrib import admin

from .models import AssetRiskMetrics


@admin.register(AssetRiskMetrics)
class AssetRiskMetricsAdmin(admin.ModelAdmin):
    list_display = (
        "asset", "as_of", "volatility_annual", "max_drawdown",
        "beta", "risk_score",
    )
    list_filter = ("asset",)
