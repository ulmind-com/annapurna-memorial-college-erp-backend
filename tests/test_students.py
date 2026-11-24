from annapurna_memorial_college_erp_backend.config import settings
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_students(client: AsyncClient):
    # First login as admin
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEFAULT_ADMIN_EMAIL, "password": settings.DEFAULT_ADMIN_PASSWORD},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/students", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] >= 1
