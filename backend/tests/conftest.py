from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings
from app.db.base import Base
from app.keitaro import KeitaroClient
from app.main import create_app
from tests.fake_keitaro import API_KEY, BASE_URL, FakeKeitaro


@pytest.fixture
def fake() -> FakeKeitaro:
    return FakeKeitaro()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        keitaro_api_url=BASE_URL,  # type: ignore[arg-type]
        keitaro_api_key=API_KEY,  # type: ignore[arg-type]
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        keitaro_retry_backoff_seconds=0,
        frontend_dist=tmp_path / "no-dist",
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def kt_client(fake: FakeKeitaro) -> KeitaroClient:
    return KeitaroClient(BASE_URL, API_KEY, backoff=0, transport=fake.transport())


@pytest.fixture
async def api(settings: Settings, kt_client: KeitaroClient) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, keitaro_client=kt_client)
    async with app.router.lifespan_context(app):
        async with app.state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://wrapper") as client:
            yield client
