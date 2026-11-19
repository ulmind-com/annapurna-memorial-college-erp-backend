import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_examination_list_and_workflow(client: AsyncClient):
    # Login as admin
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@annapurnacollege.org", "password": "Admin@123456"},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Get examinations
    resp = await client.get("/api/v1/examinations", headers=headers)
    assert resp.status_code == 200
    exams = resp.json()
    assert len(exams) >= 1
    exam_id = exams[0]["id"]

    # 2. Get marksheets for this exam
    ms_resp = await client.get(f"/api/v1/examinations/{exam_id}/marksheets", headers=headers)
    assert ms_resp.status_code == 200
    marksheets = ms_resp.json()
    assert len(marksheets) >= 1

    # 3. Test PDF generation endpoint
    first_ms = marksheets[0]
    pdf_resp = await client.get(f"/api/v1/examinations/marksheets/{first_ms['id']}/pdf", headers=headers)
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert len(pdf_resp.content) > 1000  # valid binary PDF

    # 4. Test Public QR Verification endpoint
    qr_hash = first_ms["qr_code_hash"]
    v_resp = await client.get(f"/api/v1/examinations/verify/{qr_hash}")
    assert v_resp.status_code == 200
    v_data = v_resp.json()
    assert v_data["is_verified"] is True
    assert v_data["student_name"] == first_ms["student_name"]


@pytest.mark.asyncio
async def test_marksheet_rejection_requires_remarks(client: AsyncClient):
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@annapurnacollege.org", "password": "Admin@123456"},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    exams = (await client.get("/api/v1/examinations", headers=headers)).json()
    marksheets = (await client.get(f"/api/v1/examinations/{exams[0]['id']}/marksheets", headers=headers)).json()
    target_ms = marksheets[0]

    # Attempt rejection without remarks -> should fail with 400
    fail_resp = await client.post(
        f"/api/v1/examinations/marksheets/{target_ms['id']}/action",
        json={"action": "REJECT", "remarks": ""},
        headers=headers,
    )
    assert fail_resp.status_code == 400
    assert "remarks" in fail_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_attendance_and_analytics(client: AsyncClient):
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@annapurnacollege.org", "password": "Admin@123456"},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Query attendance analytics
    an_resp = await client.get("/api/v1/attendance/analytics?course_code=BED&semester=1", headers=headers)
    assert an_resp.status_code == 200
    data = an_resp.json()
    assert isinstance(data, list)
    if len(data) > 0:
        assert "percentage" in data[0]
        assert "is_short_attendance" in data[0]
