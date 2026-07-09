"""Tests de la app news: RSS mockeado, categorías, sentimiento e impacto."""
import pytest
import responses

from news.models import News, NewsCategory
from news.services import (
    analyze_sentiment,
    classify_category,
    estimate_impact,
    google_news_rss_url,
    ingest_rss_for_query,
    news_score,
)
from tests.factories import AssetFactory

pytestmark = pytest.mark.django_db

RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Google News</title>
  <item>
    <title>MegaCorp beats earnings expectations with record revenue</title>
    <link>https://news.google.com/articles/abc123</link>
    <pubDate>Tue, 07 Jul 2026 10:00:00 GMT</pubDate>
    <description>Quarterly results exceeded analyst guidance.</description>
    <source url="https://www.reuters.com">Reuters</source>
  </item>
  <item>
    <title>MegaCorp faces lawsuit and regulatory investigation over fraud claims</title>
    <link>https://news.google.com/articles/def456</link>
    <pubDate>Mon, 06 Jul 2026 09:00:00 GMT</pubDate>
    <description>Regulators opened a probe into the company.</description>
    <source url="https://someblog.example.com">Some Blog</source>
  </item>
</channel></rss>"""


@responses.activate
def test_ingest_rss_creates_news_with_evidence_and_dedupes():
    asset = AssetFactory(ticker="MEGA")
    url = google_news_rss_url("MegaCorp stock", lang="en", country="US")
    responses.add(responses.GET, url, body=RSS_XML, content_type="application/rss+xml")
    responses.add(responses.GET, url, body=RSS_XML, content_type="application/rss+xml")

    created = ingest_rss_for_query("MegaCorp stock", asset=asset)
    assert created == 2

    items = News.objects.filter(asset=asset).order_by("published_at")
    assert items.count() == 2
    # Evidencia con confiabilidad calculada (regla 18)
    reuters_item = items.get(url_hash__isnull=False, title__icontains="beats earnings")
    assert reuters_item.evidence is not None
    assert reuters_item.evidence.reliability_level == "B"  # reuters.com → medio financiero

    # Segunda corrida: dedupe por hash de URL
    assert ingest_rss_for_query("MegaCorp stock", asset=asset) == 0
    assert News.objects.filter(asset=asset).count() == 2


def test_classify_category_rules():
    assert classify_category("Company beats earnings, revenue guidance up") == NewsCategory.EARNINGS
    assert classify_category("Regulator opens antitrust probe, compliance ban") == NewsCategory.REGULATION
    assert classify_category("Firm acquires rival in $2B merger deal to buy") == NewsCategory.MNA
    assert classify_category("CEO resigns; board appoints new executive") == NewsCategory.MANAGEMENT
    assert classify_category("Noticia genérica sin señales") == NewsCategory.OTHER


def test_sentiment_labels():
    positive, label_pos = analyze_sentiment("Record profits, great growth, beats expectations")
    negative, label_neg = analyze_sentiment("Fraud lawsuit, terrible losses, investigation")
    assert positive > 0 and label_pos == "positive"
    assert negative < 0 and label_neg == "negative"


def test_estimate_impact_bounds_and_ordering():
    high = estimate_impact(NewsCategory.MNA, sentiment=0.9, reliability=90.0)
    low = estimate_impact(NewsCategory.OTHER, sentiment=0.0, reliability=20.0)
    assert 0.0 <= low < high <= 100.0


@responses.activate
def test_news_score_neutral_without_news_and_moves_with_sentiment():
    asset = AssetFactory(ticker="NEWSY")
    assert news_score(asset) == (50.0, 0)

    url = google_news_rss_url("only positive", lang="en", country="US")
    positive_xml = RSS_XML.replace(
        "MegaCorp faces lawsuit and regulatory investigation over fraud claims",
        "MegaCorp wins major contract, excellent growth outlook",
    )
    responses.add(responses.GET, url, body=positive_xml)
    ingest_rss_for_query("only positive", asset=asset)
    # Independiza el test de las fechas fijas del XML
    from django.utils import timezone

    News.objects.filter(asset=asset).update(published_at=timezone.now())

    score, count = news_score(asset)
    assert count == 2
    assert score > 50.0
