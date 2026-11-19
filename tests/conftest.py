import pytest
from httpx import AsyncClient, ASGITransport
from annapurna_memorial_college_erp_backend.main import app
from annapurna_memorial_college_erp_backend.database import DatabaseManager


@pytest.fixture(autouse=True)
async def initialize_db():
    await DatabaseManager.connect_to_mongo()
    yield


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
