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


@pytest.mark.asyncio
async def test_teacher_and_student_logins(client: AsyncClient):
    # Test faculty login with master password
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "faculty.soumen@annapurnacollege.edu.in", "password": "Teacher@Amce2024#"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["role"] in ["FACULTY", "TEACHER"]

    # Test student login with master password
    resp2 = await client.post(
        "/api/v1/auth/login",
        json={"email": "student@annapurnacollege.org", "password": "Student@Amce2024#"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["user"]["role"] == "STUDENT"
