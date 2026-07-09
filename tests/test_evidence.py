"""Tests del sistema de confiabilidad de fuentes (sección 9)."""
import pytest

from core.models import SourceType
from core.sources import classify_domain
from tests.factories import EvidenceSourceFactory

pytestmark = pytest.mark.django_db


def test_reliability_formula_financial_media():
    """40%·70 + 20%·50 + 15%·50 + 15%·50 + 10%·50 = 58.0, nivel B."""
    evidence = EvidenceSourceFactory(source_type=SourceType.FINANCIAL_MEDIA)
    assert evidence.reliability_score == pytest.approx(58.0)
    assert evidence.reliability_level == "B"


def test_reliability_formula_official_filing():
    """40%·95 + resto neutral = 68.0, nivel A+."""
    evidence = EvidenceSourceFactory(source_type=SourceType.OFFICIAL_FILING)
    assert evidence.reliability_score == pytest.approx(68.0)
    assert evidence.reliability_level == "A+"


def test_reliability_social_is_low():
    evidence = EvidenceSourceFactory(source_type=SourceType.SOCIAL)
    assert evidence.reliability_level == "D"
    assert evidence.reliability_score < 50


def test_author_credentials_move_score():
    base = EvidenceSourceFactory(source_type=SourceType.FINANCIAL_MEDIA)
    better = EvidenceSourceFactory(
        source_type=SourceType.FINANCIAL_MEDIA, author_credentials=100.0
    )
    assert better.reliability_score == pytest.approx(base.reliability_score + 10.0)


def test_classify_domain_known_and_unknown():
    assert classify_domain("https://www.reuters.com/markets/nota") == SourceType.FINANCIAL_MEDIA
    assert classify_domain("https://sec.gov/filing") == SourceType.OFFICIAL_FILING
    assert classify_domain("https://x.com/post") == SourceType.SOCIAL
    assert classify_domain("https://blog-desconocido.io/a") == SourceType.INDEPENDENT_ANALYST
    assert classify_domain("") == SourceType.PROMOTIONAL
