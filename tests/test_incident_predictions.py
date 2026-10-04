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
    assert "Analizar con ML" in client.get(f"/incidents/{incident.id}").text
    response = client.post(f"/incidents/{incident.id}/predict", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/incidents/{incident.id}#ml-result-title"
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
    assert "Análisis de gravedad con ML" in html
    assert f"Gravedad estimada: {prediction.predicted_severity}" in html
    assert f"{prediction.prob_grave * 100:.1f}%" in html
    assert "Probabilidades estimadas" in html and "Volver a analizar" in html
    assert "La predicción del modelo es independiente de la prioridad operativa." in html
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
    db_session.refresh(incident)
    for field, value in changes.items():
        assert getattr(incident, field) == value
    assert db_session.scalar(select(func.count()).select_from(IncidentPrediction)) == 0
    if "speed_limit" in changes:
        assert "20, 30, 40, 50, 60 o 70 mph" in html
        # A rejected attempt must preserve an existing snapshot as well as create none initially.
        snapshot = IncidentPrediction(
            incident_id=incident.id,
            created_by=incident.created_by,
            predicted_severity="Leve",
            prob_fatal=0.1,
            prob_grave=0.2,
            prob_leve=0.7,
            model_version="previous-snapshot",
            input_data={"speed_limit": 30},
        )
        db_session.add(snapshot)
        db_session.commit()
        snapshot_id = snapshot.id
        second = client.post(f"/incidents/{incident.id}/predict", follow_redirects=False)
        assert second.status_code == 303
        assert message in client.get(second.headers["location"]).text
        db_session.refresh(incident)
        db_session.refresh(snapshot)
        assert incident.speed_limit == changes["speed_limit"]
        assert snapshot.id == snapshot_id and snapshot.input_data == {"speed_limit": 30}
        assert db_session.scalars(select(IncidentPrediction)).all() == [snapshot]
        return
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
    records[0].predicted_severity = "Fatal"
    db_session.commit()
    home = client.get("/").text
    own_row = home.split(f'id="incident-{incident.id}"', 1)[1].split('class="incident"', 1)[0]
    other_row = home.split(f'id="incident-{other.id}"', 1)[1].split('class="incident"', 1)[0]
    assert "ML: Grave" in own_row and "ML: Fatal" not in own_row
    assert "ML: Fatal" in other_row and "ML: Grave" not in other_row
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
        client.post(
            f"/incidents/{incident.id}/predict", data={"speed_limit": "70"}, follow_redirects=False
        ).status_code
        == 403
    )
    html = client.get(f"/incidents/{incident.id}").text
    assert "Análisis de gravedad con ML" in html
    assert f'action="/incidents/{incident.id}/predict"' not in html
    assert db_session.scalar(select(func.count()).select_from(IncidentPrediction)) == 0
    db_session.refresh(incident)
    assert incident.speed_limit == 30


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


def test_quick_registration_then_manual_analysis_keeps_operational_data_and_history(
    registered_accident, db_session
):
    client, _, user = registered_accident
    quick = {
        "title": "Registro rápido para análisis",
        "description": "Datos operativos",
        "date": "2026-10-04",
        "time": "14:37",
        "latitude": "-12.0464",
        "longitude": "-77.0428",
        "is_private": "true",
    }
    response = client.post("/incidents", data=quick, follow_redirects=False)
    assert response.status_code == 303
    incident = db_session.scalar(select(Incident).where(Incident.title == quick["title"]))
    assert incident.severity_level_id is not None and incident.is_private
    manual = {
        name: str(value) for name, value in ACCIDENT_DATA.items() if name not in {"date", "time"}
    }
    assert all(getattr(incident, name) is None for name in manual)
    home = client.get("/").text
    assert all(f'name="{name}"' not in home for name in manual)
    html = client.get(f"/incidents/{incident.id}").text
    assert all(html.count(f'name="{name}"') == 1 for name in manual)
    assert 'name="day_of_week"' not in html and 'name="hour"' not in html
    priority = incident.severity_level_id
    response = client.post(
        f"/incidents/{incident.id}/predict",
        data={**manual, "severity_level_id": "9999", "date": "2026-10-06", "latitude": "0"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(incident)
    assert incident.severity_level_id == priority
    assert incident.date == date(2026, 10, 4) and incident.time == time(14, 37)
    assert incident.latitude == pytest.approx(-12.0464)
    assert incident.description == quick["description"] and incident.is_private
    first = db_session.scalar(
        select(IncidentPrediction).where(IncidentPrediction.incident_id == incident.id)
    )
    assert first.created_by == user.id
    assert first.input_data == prediction_request_from_incident(incident).model_dump()
    assert len(first.input_data) == 11 and first.input_data["day_of_week"] == 1
    assert first.input_data["hour"] == 14
    assert first.prob_fatal + first.prob_grave + first.prob_leve == pytest.approx(1)
    html = client.get(f"/incidents/{incident.id}").text
    assert f"Gravedad estimada: {first.predicted_severity}" in html
    assert "La predicción del modelo es independiente de la prioridad operativa" in html
    snapshot = deepcopy(first.input_data)
    client.post(
        f"/incidents/{incident.id}/edit",
        data={
            "title": quick["title"],
            "severity_level_id": priority,
            "description": quick["description"],
            "date": "2026-10-05",
            "time": "15:37",
        },
    )
    db_session.refresh(incident)
    assert incident.road_type == ACCIDENT_DATA["road_type"]
    client.post(f"/incidents/{incident.id}/predict")
    predictions = list(
        db_session.scalars(
            select(IncidentPrediction)
            .where(IncidentPrediction.incident_id == incident.id)
            .order_by(IncidentPrediction.id)
        )
    )
    assert len(predictions) == 2 and predictions[0].input_data == snapshot
    assert predictions[1].input_data["day_of_week"] == 2 and predictions[1].input_data["hour"] == 15
    assert incident.severity_level_id == priority


def test_analysis_saves_inputs_when_operational_date_is_missing(registered_accident, db_session):
    client, incident, _ = registered_accident
    incident.date = None
    db_session.commit()
    response = client.post(f"/incidents/{incident.id}/predict", data={"speed_limit": "70"})
    assert "Datos de análisis guardados" in response.text and "Fecha del accidente" in response.text
    db_session.refresh(incident)
    assert incident.speed_limit == 70 and incident.date is None
    assert db_session.scalar(select(func.count()).select_from(IncidentPrediction)) == 0


def test_invalid_manual_input_does_not_mutate_accident(registered_accident, db_session):
    client, incident, _ = registered_accident
    response = client.post(
        f"/incidents/{incident.id}/predict", data={"number_of_vehicles": "18", "speed_limit": "70"}
    )
    assert response.status_code == 422
    db_session.refresh(incident)
    assert incident.number_of_vehicles == 2 and incident.speed_limit == 30
    assert db_session.scalar(select(func.count()).select_from(IncidentPrediction)) == 0


def test_ml_speed_selector_only_offers_model_categories(registered_accident, db_session):
    import re

    client, incident, _ = registered_accident
    html = client.get(f"/incidents/{incident.id}").text
    select_html = html.split('<select id="ml-speed_limit"', 1)[1].split("</select>", 1)[0]
    assert 'name="speed_limit" required' in select_html
    assert re.findall(r'<option value="([^"]*)"', select_html) == [
        "",
        "20",
        "30",
        "40",
        "50",
        "60",
        "70",
    ]
    assert 'value="30" selected' in select_html and ">30 mph</option>" in select_html
    assert '<input id="ml-speed_limit"' not in html
    incident.speed_limit = 173
    db_session.commit()
    html = client.get(f"/incidents/{incident.id}").text
    select_html = html.split('<select id="ml-speed_limit"', 1)[1].split("</select>", 1)[0]
    assert 'value="" selected' in select_html and 'value="173"' not in select_html
    assert "El valor registrado (173 mph) no es compatible" in html
    db_session.refresh(incident)
    assert incident.speed_limit == 173


@pytest.mark.parametrize("missing", [("date",), ("time",), ("date", "time")])
def test_missing_date_or_time_disables_ml_until_operational_data_is_completed(
    registered_accident, db_session, missing
):
    client, incident, _ = registered_accident
    for name in missing:
        setattr(incident, name, None)
    db_session.commit()
    html = client.get(f"/incidents/{incident.id}").text
    form = html.split('<form class="ml-analysis-form', 1)[1].split("</form>", 1)[0]
    button = form.split("<button", 1)[1].split("</button>", 1)[0]
    assert 'disabled aria-describedby="ml-date-warning"' in button
    assert "Completa la fecha y la hora del accidente antes de analizar." in html
    assert 'name="day_of_week"' not in form and 'name="hour"' not in form
    assert db_session.scalar(select(func.count()).select_from(IncidentPrediction)) == 0
    client.post(
        f"/incidents/{incident.id}/edit",
        data={
            "title": incident.title,
            "severity_level_id": incident.severity_level_id,
            "date": "2026-10-04",
            "time": "14:37",
        },
    )
    html = client.get(f"/incidents/{incident.id}").text
    form = html.split('<form class="ml-analysis-form', 1)[1].split("</form>", 1)[0]
    assert " disabled" not in form
    assert 'id="ml-date-warning"' not in html


def test_ml_result_has_semantic_outcome_and_real_probability_bars(registered_accident, db_session):
    client, incident, _ = registered_accident
    client.post(f"/incidents/{incident.id}/predict")
    prediction = db_session.scalar(select(IncidentPrediction))
    html = client.get(f"/incidents/{incident.id}").text
    result = html.split('<div class="ml-result"', 1)[1].split("</dl>", 1)[0]
    assert f'ml-{prediction.predicted_severity.lower()}"' in result
    assert f">{prediction.predicted_severity.upper()}</p>" in result
    assert (
        result.index("<dt>Leve</dt>")
        < result.index("<dt>Grave</dt>")
        < result.index("<dt>Fatal</dt>")
    )
    for probability in [prediction.prob_leve, prediction.prob_grave, prediction.prob_fatal]:
        assert f"width: {probability * 100}%" in html
        assert f"{probability * 100:.1f}%" in html
    assert html.index("Volver a analizar</button>") < html.index('<div class="ml-result"')
    assert incident.severity_level_id is not None
