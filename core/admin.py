from django.contrib import admin

from .models import EvidenceSource


@admin.register(EvidenceSource)
class EvidenceSourceAdmin(admin.ModelAdmin):
    list_display = (
        "source_name",
        "source_type",
        "reliability_level",
        "reliability_score",
        "related_asset",
        "published_at",
        "retrieved_at",
    )
    list_filter = ("source_type", "reliability_level")
    search_fields = ("source_name", "url", "author", "relevant_excerpt")
    readonly_fields = ("reliability_score", "reliability_level", "retrieved_at")
