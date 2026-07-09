from django.contrib import admin

from .models import News


@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_display = (
        "title", "asset", "keyword", "category", "sentiment_label",
        "impact_score", "source", "published_at",
    )
    list_filter = ("category", "sentiment_label", "language", "asset")
    search_fields = ("title", "summary", "source", "keyword")
    date_hierarchy = "published_at"
    raw_id_fields = ("asset", "evidence")
