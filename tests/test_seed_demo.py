from collections import Counter

import pytest
from sqlalchemy import func, select

from app.models import FollowUp, Incident, IncidentPrediction, Role
from app.services.users import create_user
from scripts.seed_demo import MARKER, seed_demo, validate_demo_url


@pytest.mark.parametrize("url", [None, "postgresql+psycopg://localhost/ic", "sqlite:///demo.db"])
def test_demo_refuses_implicit_or_non_demo_database(url):
    with pytest.raises(ValueError):
        validate_demo_url(url)


def test_demo_is_idempotent_and_uses_real_prediction_snapshots(db_session):
    actor = create_user(
        db_session,
        email="demo@test.local",
        name="Demo",
        role=Role.admin,
        password="Demo-test-2026!",
    )
    db_session.flush()
    first = seed_demo(db_session, actor_email=actor.email)
    db_session.commit()
    second = seed_demo(db_session, actor_email=actor.email)
    assert first["created"] == 12 and first["new_predictions"] == 10
    assert second["created"] == second["new_predictions"] == 0
    assert db_session.scalar(select(func.count()).select_from(Incident)) == 12
    assert db_session.scalar(select(func.count()).select_from(FollowUp)) == 3
    predictions = list(db_session.scalars(select(IncidentPrediction)))
    assert len(predictions) == 10
    assert (
        dict(Counter(p.predicted_severity for p in predictions))
        == first["latest_prediction_distribution"]
    )
    for prediction in predictions:
        assert len(prediction.input_data) == 11
        assert prediction.model_version == "1.0"
        assert (
            prediction.prob_fatal + prediction.prob_grave + prediction.prob_leve == pytest.approx(1)
        )
    assert all(i.description == MARKER for i in db_session.scalars(select(Incident)))
    assert all(i.title.startswith("[DEMO] ") for i in db_session.scalars(select(Incident)))
    assert sum(i.latitude is None for i in db_session.scalars(select(Incident))) == 1


def test_demo_requires_authorized_existing_actor(db_session):
    with pytest.raises(ValueError):
        seed_demo(db_session, actor_email="missing@test.local")
    assert db_session.scalar(select(func.count()).select_from(Incident)) == 0


def test_demo_rename_refuses_unrecognized_record(db_session):
    from scripts.seed_demo import rename_demo_labels

    incident = Incident(
        title="[DEMO 01] Colisión urbana en cruce",
        description="Registro ajeno al generador",
        creation_state={},
    )
    db_session.add(incident)
    db_session.flush()
    with pytest.raises(ValueError, match="no reconocido"):
        rename_demo_labels(db_session)
    assert incident.title == "[DEMO 01] Colisión urbana en cruce"


def test_demo_renames_known_examples_without_touching_predictions(db_session, monkeypatch):
    from copy import deepcopy

    from scripts.seed_demo import SCENARIOS

    actor = create_user(
        db_session,
        email="rename@test.local",
        name="Demo",
        role=Role.admin,
        password="Demo-test-2026!",
    )
    first = seed_demo(db_session, actor_email=actor.email)
    db_session.commit()
    incidents = list(db_session.scalars(select(Incident).order_by(Incident.id)))
    for index, incident in enumerate(incidents):
        incident.title = f"[DEMO {index + 1:02d}] {SCENARIOS[index][0]}"
    for task in db_session.scalars(select(FollowUp)):
        task.title = "[DEMO] Revisar documentación sintética"
    predictions = list(db_session.scalars(select(IncidentPrediction)))
    saved = [
        {c.key: deepcopy(getattr(p, c.key)) for c in IncidentPrediction.__mapper__.column_attrs}
        for p in predictions
    ]
    db_session.commit()

    def never_analyze(*_args, **_kwargs):
        pytest.fail("Renombrar DEMO no debe ejecutar el modelo")

    monkeypatch.setattr("scripts.seed_demo.create_prediction", never_analyze)
    summary = seed_demo(db_session, actor_email=actor.email, rename_only=True)
    db_session.commit()
    assert summary == {"renamed_accidents": 12, "renamed_tasks": 3}
    assert seed_demo(db_session, actor_email=actor.email, rename_only=True) == {
        "renamed_accidents": 0,
        "renamed_tasks": 0,
    }
    repeated = seed_demo(db_session, actor_email=actor.email)
    assert repeated["created"] == repeated["new_predictions"] == 0
    assert repeated["incident_ids"] == first["incident_ids"]
    for p, before in zip(predictions, saved, strict=True):
        db_session.refresh(p)
        assert {
            c.key: getattr(p, c.key) for c in IncidentPrediction.__mapper__.column_attrs
        } == before
