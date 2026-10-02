from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.road_fields import ROAD_FIELDS


def test_upgrade_and_downgrade_preserve_existing_incidents(pg_engine, monkeypatch):
    name = "road_migration_" + uuid4().hex
    with pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    url = pg_engine.url.set(database=name).render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    engine = create_engine(url)
    try:
        command.upgrade(config, "0017_meet_service_account")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO incidents (title, is_private, creation_state) VALUES ('Anterior', false, '{}')"
                )
            )
        command.upgrade(config, "0018_road_accident_fields")
        with engine.begin() as connection:
            connection.execute(text("UPDATE incidents SET speed_limit = 30, road_type = 6"))
            before = dict(connection.execute(text("SELECT * FROM incidents")).mappings().one())
        command.upgrade(config, "head")
        columns = {c["name"]: c for c in inspect(engine).get_columns("incidents")}
        assert all(columns[key]["nullable"] for key in ROAD_FIELDS)
        with engine.connect() as connection:
            row = connection.execute(text("SELECT * FROM incidents")).mappings().one()
            assert row["title"] == "Anterior"
            assert all(row[key] == value for key, value in before.items())
            assert all(
                row[key] is None
                for key in ("number_of_vehicles", "junction_detail", "first_road_class")
            )
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text("UPDATE incidents SET speed_limit = -1"))
        for key, value in (
            ("number_of_vehicles", 18),
            ("junction_detail", 1),
            ("first_road_class", 7),
        ):
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(text(f"UPDATE incidents SET {key} = :value"), {"value": value})
        command.downgrade(config, "0018_road_accident_fields")
        columns = {c["name"] for c in inspect(engine).get_columns("incidents")}
        assert not {"number_of_vehicles", "junction_detail", "first_road_class"} & columns
        with engine.connect() as connection:
            assert (
                dict(connection.execute(text("SELECT * FROM incidents")).mappings().one()) == before
            )
        command.downgrade(config, "0017_meet_service_account")
        assert not ROAD_FIELDS.keys() & {
            c["name"] for c in inspect(engine).get_columns("incidents")
        }
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT title FROM incidents")).scalar_one() == "Anterior"
            )
        command.upgrade(config, "head")
    finally:
        engine.dispose()
        with pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
