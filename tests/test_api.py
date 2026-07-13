"""Smoke tests de la API (Django Ninja) con proveedor falso."""
import json

import pytest

from market.providers import set_provider
from tests.fakes import FakeProvider
from tests.factories import AssetFactory, UserFactory
from tests.helpers import make_price_frame, store_prices

pytestmark = pytest.mark.django_db


def _post(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type="application/json")


@pytest.fixture
def auth_client(client):
    """Cliente con sesión iniciada: portfolio y simulation exigen auth."""
    client.force_login(UserFactory())
    return client


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] is True
    assert "yfinance_rate_limit_errors" in body


def test_create_and_list_assets(client):
    set_provider(FakeProvider(info={"longName": "API Corp", "quoteType": "EQUITY", "currency": "USD"}))
    response = _post(client, "/api/market/assets", {"ticker": "apix"})
    assert response.status_code == 200
    assert response.json()["ticker"] == "APIX"
    assert response.json()["name"] == "API Corp"

    listed = client.get("/api/market/assets").json()
    assert any(a["ticker"] == "APIX" for a in listed)


def test_prices_and_technical_endpoints(client):
    asset = AssetFactory(ticker="APIP")
    store_prices(asset, make_price_frame(n=260, seed=3))

    prices = client.get("/api/market/assets/APIP/prices?days=4000").json()
    assert len(prices) == 260
    assert prices[0]["close"] > 0

    technical = client.get("/api/market/assets/APIP/technical")
    assert technical.status_code == 200
    assert 0 <= technical.json()["score"] <= 100


def test_simulation_endpoint(auth_client):
    response = _post(
        auth_client, "/api/simulation/run",
        {"initial_capital": 1000, "monthly_contribution": 100, "years": 2,
         "expected_return": 0.08, "volatility": 0.15, "persist": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body["scenarios"]) == {"pesimista", "medio", "optimista"}
    assert body["simulation_id"] is not None


def test_portfolio_flow(auth_client):
    set_provider(FakeProvider(info={}))
    asset = AssetFactory(ticker="APIF")
    store_prices(asset, make_price_frame(n=30, seed=5))

    portfolio_id = _post(auth_client, "/api/portfolio", {"name": "Mi cartera"}).json()["id"]
    position = _post(
        auth_client, f"/api/portfolio/{portfolio_id}/positions",
        {"ticker": "APIF", "quantity": 10, "average_price": 50},
    )
    assert position.status_code == 200
    detail = auth_client.get(f"/api/portfolio/{portfolio_id}").json()
    assert detail["total_value"] > 0
    assert len(detail["positions"]) == 1


def test_recommendation_ranking_empty_ok(client):
    response = client.get("/api/recommendation/ranking")
    assert response.status_code == 200
    assert response.json() == []


def test_openapi_schema_available(client):
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"].startswith("Sistema Inteligente")
