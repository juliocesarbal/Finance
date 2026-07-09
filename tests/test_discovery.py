"""Tests del motor de descubrimiento (secciones 6, 13, 14) con RSS mockeado."""
import re

import pytest
import responses

from discovery.models import EmergingTopic, OpportunityType, RiskLevel
from discovery.services import (
    DEFAULT_TOPICS,
    WEIGHTS,
    build_report,
    scan_topic,
    seed_topics,
)
from tests.factories import AssetFactory

pytestmark = pytest.mark.django_db

GOOGLE_NEWS = re.compile(r"https://news\.google\.com/rss/search.*")

RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Google News</title>
  <item>
    <title>Quantum computing investment hits record: MegaCorp (NASDAQ: MEGA) raises $2 billion in funding</title>
    <link>https://news.google.com/articles/q1</link>
    <pubDate>Tue, 07 Jul 2026 10:00:00 GMT</pubDate>
    <description>Venture funding and institutional investment grow.</description>
    <source url="https://www.reuters.com">Reuters</source>
  </item>
  <item>
    <title>Breakthrough research: new patent for quantum chip technology launch</title>
    <link>https://news.google.com/articles/q2</link>
    <pubDate>Mon, 06 Jul 2026 09:00:00 GMT</pubDate>
    <description>Development and innovation continue.</description>
    <source url="https://www.cnbc.com">CNBC</source>
  </item>
</channel></rss>"""


def test_weights_match_section_13():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)
    assert WEIGHTS["sector_growth"] == 0.20
    assert WEIGHTS["risk"] == 0.05


def test_seed_topics_creates_defaults_once():
    assert seed_topics() == len(DEFAULT_TOPICS)
    assert seed_topics() == 0  # idempotente
    assert EmergingTopic.objects.count() == len(DEFAULT_TOPICS)


@responses.activate
def test_scan_topic_features_and_ticker_linking():
    AssetFactory(ticker="MEGA")
    responses.add(responses.GET, GOOGLE_NEWS, body=RSS_XML)
    topic = EmergingTopic.objects.create(
        name="Computación cuántica",
        query='"quantum computing" AND investment',
        category=OpportunityType.TECHNOLOGY,
    )

    scan = scan_topic(topic)
    assert topic.mention_count == 2
    assert "MEGA" in scan["candidate_tickers"]
    assert [a.ticker for a in scan["related_assets"]] == ["MEGA"]
    assert 0.0 <= scan["score"] <= 100.0
    for value in scan["features"].values():
        assert 0.0 <= value <= 100.0
    # Señales institucionales y tecnológicas detectadas en los titulares
    assert scan["features"]["institutional_investment"] > 0
    assert scan["features"]["tech_activity"] > 0


@responses.activate
def test_momentum_tracks_mention_changes():
    responses.add(responses.GET, GOOGLE_NEWS, body=RSS_XML)
    responses.add(responses.GET, GOOGLE_NEWS, body=RSS_XML)
    topic = EmergingTopic.objects.create(name="Momentum test", query="momentum")
    scan_topic(topic)
    assert topic.momentum == 0.0  # primera corrida: sin base previa
    scan_topic(topic)
    assert topic.previous_mention_count == 2
    assert topic.momentum == 0.0  # 2 → 2: sin cambio


@responses.activate
def test_build_report_structure_and_prudence():
    responses.add(responses.GET, GOOGLE_NEWS, body=RSS_XML)
    topic = EmergingTopic.objects.create(
        name="Reporte test", query="report query", default_horizon="5-10 años",
    )
    scan = scan_topic(topic)
    report = build_report(scan)

    # Estructura de la sección 14
    assert report.thesis and report.risks and report.conclusion
    assert report.horizon == "5-10 años"
    assert report.score == scan["score"]
    assert report.score_breakdown["weights"] == WEIGHTS
    assert report.evidence.count() == 2
    # Evidencia clasificada por el dominio del medio original
    levels = {e.reliability_level for e in report.evidence.all()}
    assert "B" in levels  # reuters/cnbc → medio financiero
    # Lenguaje prudente (sección 20)
    assert "no constituye asesoramiento" in report.conclusion
    # Sin activos relacionados vinculados → especulativo
    assert report.risk_level in {RiskLevel.VERY_HIGH, RiskLevel.EXTREME}
