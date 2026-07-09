from django.contrib import admin

from .models import AgentReview, Recommendation


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = (
        "asset", "signal", "score", "technical_score", "news_score",
        "fundamental_score", "risk_score", "created_at",
    )
    list_filter = ("signal", "asset")
    filter_horizontal = ("evidence_sources",)


@admin.register(AgentReview)
class AgentReviewAdmin(admin.ModelAdmin):
    list_display = (
        "asset", "signal", "mechanical_score", "agent_score",
        "divergence", "confidence", "model_used", "created_at",
    )
    list_filter = ("signal", "model_used")
    filter_horizontal = ("evidence_sources",)
