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
    assert sum(i.latitude is None for i in db_session.scalars(select(Incident))) == 1


def test_demo_requires_authorized_existing_actor(db_session):
    with pytest.raises(ValueError):
        seed_demo(db_session, actor_email="missing@test.local")
    assert db_session.scalar(select(func.count()).select_from(Incident)) == 0
