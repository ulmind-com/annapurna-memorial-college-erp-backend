import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "Annapurna" in data["service"]


@pytest.mark.asyncio
async def test_superadmin_login(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@annapurnacollege.org", "password": "Admin@123456"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["role"] == "SUPER_ADMIN"

    # Also test admin@annapurnacollege.edu.in with Admin@Amce2024#
    resp2 = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@annapurnacollege.edu.in", "password": "Admin@Amce2024#"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert "access_token" in data2
    assert data2["user"]["role"] == "SUPER_ADMIN"


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@annapurnacollege.org", "password": "WrongPassword999"},
    )
    assert resp.status_code == 401
