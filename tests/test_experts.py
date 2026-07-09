"""Tests del consenso de analistas (sección 11): dispersión y alertas."""
import pytest

from experts.services import sync_consensus
from market.providers import set_provider
from tests.factories import AssetFactory
from tests.fakes import FakeProvider

pytestmark = pytest.mark.django_db


def _consensus_data(strong_buy=5, buy=10, hold=5, sell=1, strong_sell=0,
                    mean=120.0, high=150.0, low=90.0):
    return {
        "summary": [
            {"period": "0m", "strongBuy": strong_buy, "buy": buy, "hold": hold,
             "sell": sell, "strongSell": strong_sell},
            {"period": "-1m", "strongBuy": 1, "buy": 1, "hold": 1, "sell": 1, "strongSell": 1},
        ],
        "targets": {"current": 100.0, "mean": mean, "high": high, "low": low, "median": mean},
    }


def test_sync_consensus_math():
    asset = AssetFactory(ticker="CONS1")
    set_provider(FakeProvider(recommendations=_consensus_data()))

    consensus = sync_consensus(asset)
    assert consensus.total_analysts == 21
    # (1·5 + 2·10 + 3·5 + 4·1 + 5·0) / 21 = 44/21 ≈ 2.10
    assert consensus.rating_mean == pytest.approx(2.10, abs=0.01)
    # (150 − 90) / 120 = 0.5
    assert consensus.dispersion == pytest.approx(0.5)
    assert consensus.mean_target == 120.0
    assert consensus.change_alert == "" or "dispersión" in consensus.change_alert.lower()


def test_drastic_change_generates_alert():
    asset = AssetFactory(ticker="CONS2")
    set_provider(FakeProvider(recommendations=_consensus_data()))
    first = sync_consensus(asset)
    assert first is not None

    # Mejora drástica del rating y salto del precio objetivo
    set_provider(FakeProvider(recommendations=_consensus_data(
        strong_buy=15, buy=5, hold=1, sell=0, strong_sell=0,
        mean=150.0, high=160.0, low=140.0,
    )))
    second = sync_consensus(asset)
    assert "mejoró" in second.change_alert
    assert "objetivo" in second.change_alert.lower()


def test_high_dispersion_is_flagged_as_signal():
    """La dispersión alta se muestra, no se esconde en el promedio (sección 11)."""
    asset = AssetFactory(ticker="CONS3")
    set_provider(FakeProvider(recommendations=_consensus_data(mean=100.0, high=180.0, low=40.0)))
    consensus = sync_consensus(asset)
    assert consensus.dispersion == pytest.approx(1.4)
    assert "dispersión alta" in consensus.change_alert.lower()


def test_sync_returns_none_without_data():
    asset = AssetFactory(ticker="CONS4")
    set_provider(FakeProvider(recommendations={"summary": [], "targets": {}}))
    assert sync_consensus(asset) is None
