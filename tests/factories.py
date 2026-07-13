"""Factories de datos de prueba (sección 16.6: sin depender de la red)."""
import factory
from django.contrib.auth import get_user_model

from core.models import EvidenceSource, SourceType
from market.models import Asset, AssetType


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"user{n}@example.com")
    email = factory.LazyAttribute(lambda o: o.username)


class AssetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Asset
        django_get_or_create = ("ticker",)

    ticker = factory.Sequence(lambda n: f"TST{n}")
    name = factory.LazyAttribute(lambda o: f"Test Asset {o.ticker}")
    asset_type = AssetType.STOCK
    sector = "Technology"
    country = "United States"
    currency = "USD"


class EvidenceSourceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EvidenceSource

    url = factory.Sequence(lambda n: f"https://example.com/nota-{n}")
    source_name = "Medio de prueba"
    source_type = SourceType.FINANCIAL_MEDIA
