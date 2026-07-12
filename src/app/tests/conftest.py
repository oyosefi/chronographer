import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/chronographer_test"
)
os.environ.setdefault("API_KEY", "test-api-key")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import SessionLocal, engine
from app.main import app
from app.models import SINGLE_USER_ID, Base, User


@pytest_asyncio.fixture
async def api_client():
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        async with SessionLocal.begin() as session:
            session.add(
                User(
                    id=SINGLE_USER_ID,
                    display_name="Test User",
                    timezone="America/Los_Angeles",
                )
            )
    except OSError as exc:
        import pytest

        pytest.skip(f"PostgreSQL integration database is unavailable: {exc}")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
def auth_headers():
    return {"Authorization": "Bearer test-api-key"}
