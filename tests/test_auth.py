"""Tests del flujo de autenticación por sesión (app accounts) y del
aislamiento de datos por usuario en portfolio y simulation."""
import json

import pytest

from portfolio.models import Portfolio
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

PASSWORD = "clave-segura-99"


def _post(client, url, payload=None):
    return client.post(
        url,
        data=json.dumps(payload) if payload is not None else None,
        content_type="application/json",
    )


def _user(email: str):
    user = UserFactory(username=email, email=email)
    user.set_password(PASSWORD)
    user.save()
    return user


# ---------------------------------------------------------------- registro
def test_register_creates_user_logs_in_and_normalizes_email(client):
    resp = _post(client, "/api/auth/register", {"email": "Ana@Example.com", "password": PASSWORD})
    assert resp.status_code == 200
    assert resp.json()["email"] == "ana@example.com"

    me = client.get("/api/auth/me").json()
    assert me["authenticated"] is True
    assert me["user"]["email"] == "ana@example.com"


def test_register_rejects_duplicate_email_case_insensitive(client):
    _post(client, "/api/auth/register", {"email": "dup@example.com", "password": PASSWORD})
    resp = _post(client, "/api/auth/register", {"email": "DUP@example.com", "password": "otra-clave-77"})
    assert resp.status_code == 400
    assert "correo" in resp.json()["detail"].lower()


def test_register_rejects_invalid_email(client):
    resp = _post(client, "/api/auth/register", {"email": "no-es-un-email", "password": PASSWORD})
    assert resp.status_code == 400


def test_register_rejects_weak_password(client):
    resp = _post(client, "/api/auth/register", {"email": "ok@example.com", "password": "123"})
    assert resp.status_code == 400


# ---------------------------------------------------------------- login/logout
def test_login_logout_flow(client):
    _user("u@example.com")

    bad = _post(client, "/api/auth/login", {"email": "u@example.com", "password": "incorrecta"})
    assert bad.status_code == 401

    ok = _post(client, "/api/auth/login", {"email": "U@Example.com", "password": PASSWORD})
    assert ok.status_code == 200
    assert client.get("/api/auth/me").json()["authenticated"] is True

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_me_is_public_and_anonymous_by_default(client):
    body = client.get("/api/auth/me").json()
    assert body == {"authenticated": False, "user": None}


# ---------------------------------------------------------------- protección
def test_portfolio_requires_session(client):
    assert client.get("/api/portfolio").status_code == 401


def test_simulation_requires_session(client):
    resp = _post(client, "/api/simulation/run", {"initial_capital": 1000, "years": 1})
    assert resp.status_code == 401


# ---------------------------------------------------------------- aislamiento
def test_portfolios_are_isolated_per_user(client):
    ana = _user("ana@example.com")
    client.force_login(ana)
    pid = _post(client, "/api/portfolio", {"name": "De Ana"}).json()["id"]

    client.force_login(_user("beto@example.com"))
    assert client.get("/api/portfolio").json() == []
    assert client.get(f"/api/portfolio/{pid}").status_code == 404
    assert client.delete(f"/api/portfolio/{pid}").status_code == 404


def test_simulation_cannot_persist_into_foreign_portfolio(client):
    ajena = Portfolio.objects.create(user=_user("ana2@example.com"), name="De Ana")
    client.force_login(_user("beto2@example.com"))

    resp = _post(
        client, "/api/simulation/run",
        {"initial_capital": 1000, "years": 1, "portfolio_id": ajena.id, "persist": True},
    )
    assert resp.status_code == 404


def test_simulation_persists_with_owner(client):
    user = _user("dueno@example.com")
    client.force_login(user)
    resp = _post(client, "/api/simulation/run", {"initial_capital": 1000, "years": 1})
    assert resp.status_code == 200

    from simulation.models import Simulation

    sim = Simulation.objects.get(id=resp.json()["simulation_id"])
    assert sim.user == user
