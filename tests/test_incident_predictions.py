from copy import deepcopy
from datetime import UTC, date, datetime, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import get_db
from app.main import create_app
from app.models import Incident, IncidentPrediction, Role, SeverityLevel
from app.road_fields import ROAD_FIELDS
from app.services.incident_predictions import (
    PredictionDataError,
    prediction_request_from_incident,
)
from app.services.users import create_user

ACCIDENT_DATA = {
    "date": date(2026, 10, 4),
    "time": time(14, 37),
    "road_type": 6,
    "speed_limit": 30,
    "urban_or_rural_area": 1,
    "light_conditions": 1,
    "weather_conditions": 1,
    "road_surface_conditions": 1,
    "number_of_vehicles": 2,
    "junction_detail": 13,
    "first_road_class": 3,
}


@pytest.mark.parametrize("day", range(1, 8))
def test_stats19_day_and_hour_from_incident(day):
    hour = (0, 14, 23)[day % 3]
    incident = Incident(
        **{**ACCIDENT_DATA, "date": date(2026, 10, day + 3), "time": time(hour, 59)}
    )
    inputs = prediction_request_from_incident(incident)
    assert inputs.day_of_week == day  # 4 October 2026 is Sunday.
    assert inputs.hour == hour  # Minutes are discarded, without altering the saved time.
    assert incident.time.minute == 59
    assert len(inputs.model_dump()) == 11
    for name in type(inputs).model_fields.keys() - {"day_of_week", "hour"}:
        assert getattr(inputs, name) == ACCIDENT_DATA[name]


@pytest.mark.parametrize("field", list(ACCIDENT_DATA))
def test_missing_input_is_named_without_filling_defaults(field):
    incident = Incident(**{**ACCIDENT_DATA, field: None})
    with pytest.raises(PredictionDataError) as error:
        prediction_request_from_incident(incident)
    assert ROAD_FIELDS[field]["label"] in str(error.value)


@pytest.fixture
def registered_accident(db_session, get_db_override):
    user = create_user(
        db_session,
        email="ml-incident@test.local",
        name="Coordinador",
        role=Role.incident_commander,
        password="password123",
    )
    severity = SeverityLevel(label="SEV2", color="#F4B740", rank=2, is_default=True)
    db_session.add(severity)
    db_session.flush()
    incident = Incident(
        title="Accidente ML",
        description="Descripción original",
        severity_level_id=severity.id,
        created_by=user.id,
        creation_state={},
        **ACCIDENT_DATA,
    )
    db_session.add(incident)
    db_session.commit()
    app = create_app()
    app.dependency_overrides[get_db] = get_db_override
    client = TestClient(app)
    client.post("/login", data={"email": user.email, "password": "password123"})
    try:
        yield client, incident, user
    finally:
        client.close()


def test_predict_saves_snapshot_and_renders_result_without_changing_accident(
    registered_accident, db_session
):
    client, incident, user = registered_accident
    before = {
        column.key: deepcopy(getattr(incident, column.key))
        for column in Incident.__mapper__.column_attrs
    }
    assert "Calcular predicción" in client.get(f"/incidents/{incident.id}").text
    response = client.post(f"/incidents/{incident.id}/predict", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/incidents/{incident.id}"
    prediction = db_session.scalar(select(IncidentPrediction))
    assert prediction.incident_id == incident.id and prediction.created_by == user.id
    assert prediction.predicted_severity in {"Fatal", "Grave", "Leve"}
    assert prediction.model_version == "1.0" and prediction.created_at is not None
    assert prediction.input_data == prediction_request_from_incident(incident).model_dump()
    assert prediction.prob_fatal + prediction.prob_grave + prediction.prob_leve == pytest.approx(1)
    db_session.refresh(incident)
    assert {
        column.key: getattr(incident, column.key) for column in Incident.__mapper__.column_attrs
    } == before
    assert incident.severity_level_id == before["severity_level_id"]
    html = client.get(f"/incidents/{incident.id}").text
    assert "Predicción de gravedad por ML" in html
    assert f"Gravedad estimada: {prediction.predicted_severity}" in html
    assert f"{prediction.prob_grave * 100:.1f}%" in html
    assert "Probabilidades estimadas" in html and "Volver a calcular" in html
    assert (
        "La predicción es una estimación del modelo y no reemplaza la gravedad registrada del accidente."
        in html
    )
    incident.speed_limit = 70
    db_session.commit()
    db_session.refresh(prediction)
    assert prediction.input_data["speed_limit"] == 30


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"date": None, "time": None, "number_of_vehicles": None}, "Faltan datos necesarios"),
        ({"speed_limit": 173}, "Datos incompatibles con el modelo"),
    ],
)
def test_web_action_reports_invalid_accident_without_saving(
    registered_accident, db_session, monkeypatch, changes, message
):
    client, incident, _ = registered_accident
    for name, value in changes.items():
        setattr(incident, name, value)
    db_session.commit()

    def should_not_load():
        pytest.fail("No debe ejecutarse ML con datos inválidos")

    monkeypatch.setattr("app.services.incident_predictions.get_predictor", should_not_load)
    response = client.post(f"/incidents/{incident.id}/predict", follow_redirects=False)
    assert response.status_code == 303
    html = client.get(response.headers["location"]).text
    assert message in html
    for field in changes:
        assert ROAD_FIELDS[field]["label"] in html
    assert db_session.scalar(select(func.count()).select_from(IncidentPrediction)) == 0


def test_latest_and_five_previous_predictions_are_scoped_and_ordered(
    registered_accident, db_session
):
    client, incident, user = registered_accident
    records = []
    for index in range(7):
        record = IncidentPrediction(
            incident_id=incident.id,
            created_by=user.id,
            predicted_severity="Grave",
            prob_fatal=0.123,
            prob_grave=0.558,
            prob_leve=0.319,
            model_version=f"test-{index}",
            input_data=prediction_request_from_incident(incident).model_dump(),
            created_at=datetime(2026, 10, 4, 15, tzinfo=UTC),
        )
        db_session.add(record)
        db_session.flush()
        records.append(record)
    other = Incident(title="Otro accidente", creation_state={})
    db_session.add(other)
    db_session.flush()
    db_session.add(
        IncidentPrediction(
            incident_id=other.id,
            created_by=user.id,
            predicted_severity="Fatal",
            prob_fatal=1,
            prob_grave=0,
            prob_leve=0,
            model_version="otro-modelo",
            input_data={},
            created_at=datetime(2026, 10, 5, tzinfo=UTC),
        )
    )
    db_session.commit()
    html = client.get(f"/incidents/{incident.id}").text
    assert "Gravedad estimada: Grave" in html
    assert "12.3%" in html and "55.8%" in html and "31.9%" in html
    assert "test-6" in html and "test-0" not in html and "otro-modelo" not in html
    assert html.count('data-prediction-id="') == 5
    positions = [
        html.index(f'data-prediction-id="{record.id}"') for record in reversed(records[1:6])
    ]
    assert positions == sorted(positions)


def test_readonly_can_view_but_cannot_generate_prediction(registered_accident, db_session):
    client, incident, _ = registered_accident
    create_user(
        db_session,
        email="ml-reader@test.local",
        name="Consulta",
        role=Role.read_only,
        password="password123",
    )
    db_session.commit()
    client.get("/logout")
    client.post("/login", data={"email": "ml-reader@test.local", "password": "password123"})
    assert (
        client.post(f"/incidents/{incident.id}/predict", follow_redirects=False).status_code == 403
    )
    html = client.get(f"/incidents/{incident.id}").text
    assert "Predicción de gravedad por ML" in html
    assert f'action="/incidents/{incident.id}/predict"' not in html
    assert db_session.scalar(select(func.count()).select_from(IncidentPrediction)) == 0


def test_prediction_of_unknown_incident_returns_404(registered_accident):
    client, _, _ = registered_accident
    assert client.post("/incidents/999999/predict", follow_redirects=False).status_code == 404


def test_model_failure_returns_to_detail_with_message(registered_accident, db_session, monkeypatch):
    client, incident, _ = registered_accident

    def unavailable():
        raise FileNotFoundError("modelo_final.joblib")

    monkeypatch.setattr("app.services.incident_predictions.get_predictor", unavailable)
    response = client.post(f"/incidents/{incident.id}/predict", follow_redirects=False)
    assert response.status_code == 303
    assert "No se pudo ejecutar el modelo ML" in client.get(response.headers["location"]).text
    assert db_session.scalar(select(func.count()).select_from(IncidentPrediction)) == 0
