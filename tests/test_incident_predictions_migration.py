from uuid import uuid4

from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.models import Incident, IncidentPrediction, Role
from app.services.users import create_user


def test_prediction_history_migration_preserves_accident_and_stores_json(
    pg_engine, monkeypatch, migration_config
):
    name = "prediction_migration_" + uuid4().hex
    with pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    url = pg_engine.url.set(database=name).render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", url)
    config = migration_config
    engine = create_engine(url)
    try:
        command.upgrade(config, "0019_incident_ml_fields")
        with Session(engine) as db:
            user = create_user(
                db,
                email="migration@test.local",
                name="Usuario",
                role=Role.admin,
                password="password123",
            )
            incident = Incident(title="Anterior", speed_limit=30, creation_state={})
            db.add(incident)
            db.commit()
            incident_id, user_id = incident.id, user.id
            before = dict(db.execute(text("SELECT * FROM incidents")).mappings().one())
        command.upgrade(config, "head")
        inspector = inspect(engine)
        assert "incident_predictions" in inspector.get_table_names()
        assert {i["name"] for i in inspector.get_indexes("incident_predictions")} == {
            "ix_incident_predictions_history"
        }
        with Session(engine) as db:
            assert dict(db.execute(text("SELECT * FROM incidents")).mappings().one()) == before
            record = IncidentPrediction(
                incident_id=incident_id,
                created_by=user_id,
                predicted_severity="Grave",
                prob_fatal=0.123,
                prob_grave=0.558,
                prob_leve=0.319,
                model_version="migration-test",
                input_data={"day_of_week": 1, "hour": 14},
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            assert record.input_data == {"day_of_week": 1, "hour": 14}
            assert record.created_at is not None
        command.downgrade(config, "0019_incident_ml_fields")
        assert "incident_predictions" not in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert (
                dict(connection.execute(text("SELECT * FROM incidents")).mappings().one()) == before
            )
    finally:
        engine.dispose()
        with pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
