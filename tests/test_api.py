"""API tests: auth, endpoints, usage caps, rate limits (in-memory tmp db)."""

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setenv("ROI_DB_PATH", str(db))
    # Import after env is set so startup uses the test db.
    from app import auth
    from app.main import app

    auth.init_db(str(db))
    with TestClient(app) as c:
        c.api_key = auth.create_key("free", "test", db_path=str(db))
        c.db_path = str(db)
        yield c


def _auth(client):
    return {"X-API-Key": client.api_key}


def test_health_no_auth(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_missing_key_401(client):
    assert client.get("/v1/me").status_code == 401


def test_invalid_key_401(client):
    r = client.get("/v1/me", headers={"X-API-Key": "roi_bogus"})
    assert r.status_code == 401


def test_bearer_auth_works(client):
    r = client.get("/v1/me", headers={"Authorization": f"Bearer {client.api_key}"})
    assert r.status_code == 200
    assert r.json()["plan"] == "free"


def test_roi_endpoint(client):
    r = client.post(
        "/v1/roi",
        json={"buy_price": 100, "sell_price": 150},
        headers=_auth(client),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["net_profit"] == 50
    assert body["verdict"] == "strong"


def test_scan_endpoint(client):
    r = client.post(
        "/v1/scan",
        json={"asking_price": 100, "expected_resale_price": 130},
        headers=_auth(client),
    )
    assert r.status_code == 200
    assert r.json()["market_verdict"] == "undervalued"


def test_validation_rejects_negative_price(client):
    r = client.post(
        "/v1/roi",
        json={"buy_price": -5, "sell_price": 100},
        headers=_auth(client),
    )
    assert r.status_code == 422


def test_rate_limit_429(client):
    codes = []
    for _ in range(12):  # free plan = 10/min
        codes.append(
            client.post(
                "/v1/roi",
                json={"buy_price": 1, "sell_price": 2},
                headers=_auth(client),
            ).status_code
        )
    assert codes.count(200) == 10
    assert 429 in codes
    last = client.post(
        "/v1/roi", json={"buy_price": 1, "sell_price": 2}, headers=_auth(client)
    )
    assert last.status_code == 429
    assert "Retry-After" in last.headers


def test_me_reports_usage(client):
    client.post("/v1/roi", json={"buy_price": 1, "sell_price": 2}, headers=_auth(client))
    r = client.get("/v1/me", headers=_auth(client))
    body = r.json()
    assert body["used_today"] == 1
    assert body["daily_cap"] == 100
