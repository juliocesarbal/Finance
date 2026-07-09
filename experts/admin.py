from django.contrib import admin

from .models import AnalystConsensus, Expert


@admin.register(Expert)
class ExpertAdmin(admin.ModelAdmin):
    list_display = ("name", "firm", "regulator_registry", "verified")
    list_filter = ("verified", "firm")
    search_fields = ("name", "firm", "regulator_registry")


@admin.register(AnalystConsensus)
class AnalystConsensusAdmin(admin.ModelAdmin):
    list_display = (
        "asset", "as_of", "total_analysts", "rating_mean",
        "mean_target", "dispersion", "change_alert",
    )
    list_filter = ("asset",)
