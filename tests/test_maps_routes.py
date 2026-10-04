from datetime import UTC, date, datetime, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.db import get_db
from app.main import create_app
from app.models import (
    Incident,
    IncidentPrediction,
    Role,
    SeverityLevel,
    StatusCategory,
    StatusLevel,
)
from app.services.users import create_user


@pytest.fixture
def client(db_session, get_db_override):
    app = create_app()
    app.dependency_overrides[get_db] = get_db_override
    client = TestClient(app)
    yield client
    client.close()


@pytest.fixture
def authenticated(client, db_session):
    user = create_user(
        db_session,
        email="map@test.local",
        name="Consulta",
        role=Role.read_only,
        password="password123",
    )
    db_session.commit()
    client.post("/login", data={"email": user.email, "password": "password123"})
    return client, user


def accident(db, **values):
    defaults = dict(
        title="Accidente",
        latitude=-12.04,
        longitude=-77.04,
        date=date(2026, 10, 4),
        time=time(14, 30),
        urban_or_rural_area=1,
        creation_state={},
    )
    incident = Incident(**{**defaults, **values})
    db.add(incident)
    db.flush()
    return incident


def prediction(db, incident, user, severity, when):
    probs = {"Fatal": (1, 0, 0), "Grave": (0, 1, 0), "Leve": (0, 0, 1)}[severity]
    record = IncidentPrediction(
        incident_id=incident.id,
        created_by=user.id,
        predicted_severity=severity,
        prob_fatal=probs[0],
        prob_grave=probs[1],
        prob_leve=probs[2],
        model_version="map-test",
        input_data={},
        created_at=when,
    )
    db.add(record)
    db.flush()
    return record


def test_map_and_data_require_login(client):
    for path in ("/maps", "/maps/incidents.json"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


def test_maps_page_uses_leaflet_clustering_and_navigation(authenticated):
    client, _ = authenticated
    response = client.get("/maps")
    assert response.status_code == 200
    assert "Mapa de accidentes" in response.text
    assert (
        "Explora la ubicación de los accidentes y su última predicción de gravedad."
        in response.text
    )
    assert 'class="map-surface"' in response.text
    for name in ("date_from", "date_to", "prediction", "zone"):
        assert f'name="{name}"' in response.text
    assert "Aplicar filtros" in response.text and "Limpiar" in response.text
    for path in (
        "/static/vendor/leaflet/leaflet.js",
        "/static/vendor/leaflet.markercluster/leaflet.markercluster.js",
        "/static/accident-map.js",
        "/static/accident-map.css",
    ):
        assert path in response.text
        assert client.get(path).status_code == 200
    assert "3d-force-graph" not in response.text and "graph.json" not in response.text
    assert 'href="/maps"' in client.get("/").text
    assert client.get("/maps/graph.json").status_code == 404


def test_coordinates_required_and_zero_and_boundaries_are_valid(authenticated, db_session):
    client, _ = authenticated
    good = [
        accident(
            db_session, latitude=0, longitude=0, date=None, time=None, urban_or_rural_area=None
        ),
        accident(db_session, latitude=90, longitude=180),
        accident(db_session, latitude=-90, longitude=-180),
    ]
    for lat, lon in [(None, None), (None, 0), (0, None)]:
        accident(db_session, latitude=lat, longitude=lon)
    db_session.commit()
    data = client.get("/maps/incidents.json").json()
    assert data["count"] == 3
    assert {item["id"] for item in data["incidents"]} == {i.id for i in good}
    zero = next(item for item in data["incidents"] if item["id"] == good[0].id)
    assert zero["latitude"] == 0 and zero["longitude"] == 0
    assert zero["date"] is None and zero["time"] is None
    assert zero["latest_prediction"] is None and zero["urban_or_rural_area"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("latitude", 91),
        ("longitude", -181),
        ("latitude", float("nan")),
        ("longitude", float("inf")),
    ],
)
def test_invalid_coordinates_cannot_enter_map_data(authenticated, db_session, field, value):
    client, _ = authenticated
    good = accident(db_session)
    db_session.commit()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        accident(db_session, **{field: value})
    data = client.get("/maps/incidents.json").json()
    assert data["count"] == 1 and data["incidents"][0]["id"] == good.id


def test_latest_prediction_is_scoped_and_operational_labels_are_separate(authenticated, db_session):
    client, user = authenticated
    level = SeverityLevel(
        label="Prioridad operativa urgente", rank=1, color="#000000", is_default=True
    )
    db_session.add(level)
    state = StatusLevel(label="En atención", category=StatusCategory.active, rank=1)
    db_session.add(state)
    db_session.flush()
    first = accident(
        db_session,
        severity_level_id=level.id,
        status_id=state.id,
        description="Información ajena al mapa",
    )
    second = accident(db_session)
    neutral = accident(db_session)
    timestamp = datetime(2026, 10, 4, tzinfo=UTC)
    prediction(db_session, first, user, "Fatal", datetime(2026, 10, 3, tzinfo=UTC))
    prediction(db_session, first, user, "Leve", timestamp)
    prediction(db_session, first, user, "Grave", timestamp)  # Tie: highest id is latest.
    prediction(db_session, second, user, "Fatal", timestamp)
    db_session.commit()
    data = client.get("/maps/incidents.json").json()
    items = {item["id"]: item for item in data["incidents"]}
    assert items[first.id]["latest_prediction"] == {
        "prediction": "Grave",
        "probabilities": {"Fatal": 0, "Grave": 1, "Leve": 0},
    }
    assert items[second.id]["latest_prediction"]["prediction"] == "Fatal"
    assert items[neutral.id]["latest_prediction"] is None
    expected = {
        "id",
        "title",
        "latitude",
        "longitude",
        "date",
        "time",
        "urban_or_rural_area",
        "operational_priority",
        "status",
        "latest_prediction",
    }
    assert all(set(item) == expected for item in items.values())
    assert items[first.id]["operational_priority"] == "Prioridad operativa urgente"
    assert items[first.id]["status"] == "En atención"
    assert items[neutral.id]["operational_priority"] is None and items[neutral.id]["status"] is None
    assert "severity_level" not in str(data) and "color" not in str(data)
    assert "Información ajena al mapa" not in str(data)
    assert items[first.id]["date"] == "2026-10-04" and items[first.id]["time"] == "14:30"
    fatal = client.get("/maps/incidents.json", params={"prediction": "Fatal"}).json()
    assert [item["id"] for item in fatal["incidents"]] == [second.id]


def test_date_range_prediction_and_zone_filters_combine(authenticated, db_session):
    client, user = authenticated
    matching = accident(db_session, date=date(2026, 10, 4), urban_or_rural_area=2)
    others = [
        accident(db_session, date=date(2026, 10, 3), urban_or_rural_area=2),
        accident(db_session, date=date(2026, 10, 5), urban_or_rural_area=2),
        accident(db_session, urban_or_rural_area=1),
        accident(db_session, urban_or_rural_area=3),
        accident(db_session, date=None, urban_or_rural_area=None),
    ]
    for incident in [matching, *others]:
        prediction(db_session, incident, user, "Leve", datetime(2026, 10, 6, tzinfo=UTC))
    db_session.commit()
    data = client.get(
        "/maps/incidents.json",
        params={
            "date_from": "2026-10-04",
            "date_to": "2026-10-04",
            "prediction": "Leve",
            "zone": 2,
        },
    ).json()
    assert data["count"] == 1 and data["incidents"][0]["id"] == matching.id
    for zone, count in [(1, 1), (2, 3), (3, 1)]:
        assert client.get("/maps/incidents.json", params={"zone": zone}).json()["count"] == count
    assert client.get("/maps/incidents.json", params={"prediction": "Grave"}).json()["count"] == 0


def test_no_prediction_filter_keeps_neutral_accidents(authenticated, db_session):
    client, user = authenticated
    neutral = accident(db_session)
    predicted = accident(db_session)
    prediction(db_session, predicted, user, "Fatal", datetime(2026, 10, 4, tzinfo=UTC))
    db_session.commit()
    data = client.get("/maps/incidents.json", params={"prediction": "none"}).json()
    assert data["count"] == 1 and data["incidents"][0]["id"] == neutral.id


def test_empty_map_returns_no_artificial_points(authenticated):
    client, _ = authenticated
    assert client.get("/maps/incidents.json").json() == {"incidents": [], "count": 0}


@pytest.mark.parametrize(
    "params",
    [
        {"zone": 0},
        {"zone": 4},
        {"prediction": "SEV1"},
        {"date_from": "invalid"},
        {"date_from": "2026-10-05", "date_to": "2026-10-04"},
    ],
)
def test_invalid_filters_return_422(authenticated, params):
    client, _ = authenticated
    assert client.get("/maps/incidents.json", params=params).status_code == 422
