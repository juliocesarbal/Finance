from django.contrib import admin

from .models import EmergingTopic, OpportunityReport


@admin.register(EmergingTopic)
class EmergingTopicAdmin(admin.ModelAdmin):
    list_display = (
        "name", "category", "mention_count", "momentum",
        "last_scanned_at", "is_active",
    )
    list_filter = ("category", "is_active")
    search_fields = ("name", "query")


@admin.register(OpportunityReport)
class OpportunityReportAdmin(admin.ModelAdmin):
    list_display = ("name", "opportunity_type", "score", "risk_level", "horizon", "created_at")
    list_filter = ("opportunity_type", "risk_level")
    filter_horizontal = ("related_assets", "evidence")
