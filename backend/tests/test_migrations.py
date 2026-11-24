from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command

BACKEND = Path(__file__).resolve().parents[1]


def test_upgrade_and_downgrade(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.attributes["database_url"] = f"sqlite+aiosqlite:///{db}"
    command.upgrade(cfg, "head")
    tables = set(inspect(create_engine(f"sqlite:///{db}")).get_table_names())
    assert {"campaigns", "streams", "stream_offers", "alembic_version"} <= tables
    command.downgrade(cfg, "base")
    assert set(inspect(create_engine(f"sqlite:///{db}")).get_table_names()) == {"alembic_version"}
