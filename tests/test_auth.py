from annapurna_memorial_college_erp_backend.config import settings
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
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEFAULT_ADMIN_EMAIL, "password": settings.DEFAULT_ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "SUPER_ADMIN"


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@annapurnacollege.org", "password": "WrongPassword999"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_master_passwords_rejected(client: AsyncClient):
    """Shared/master passwords must never authenticate any account."""
    for email, pwd in [
        ("faculty.soumen@annapurnacollege.edu.in", "Student@Amce2024#"),
        ("student@annapurnacollege.org", "Teacher@Amce2024#"),
        ("admin@annapurnacollege.org", "WrongPassword123#"),
    ]:
        response = await client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
        assert response.status_code == 401
