import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_fees_overview_and_invoices(client: AsyncClient):
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@annapurnacollege.org", "password": "Admin@123456"},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Test fee overview stats
    ov_resp = await client.get("/api/v1/fees/overview", headers=headers)
    assert ov_resp.status_code == 200
    ov_data = ov_resp.json()
    assert ov_data["total_invoices"] >= 1
    assert "collection_rate" in ov_data

    # 2. Test list invoices
    inv_resp = await client.get("/api/v1/fees/invoices", headers=headers)
    assert inv_resp.status_code == 200
    inv_data = inv_resp.json()
    assert "items" in inv_data
