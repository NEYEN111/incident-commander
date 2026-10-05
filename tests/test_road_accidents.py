from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.db import get_db
from app.main import create_app
from app.models import Incident, IncidentType, Role, SeverityLevel, System
from app.road_fields import ROAD_FIELDS, validate_road_data
from app.services.incidents import update_incident
from app.services.statuses import seed_status_levels
from app.services.users import create_user

ROAD_DATA = {
    "date": "2026-09-30",
    "time": "14:30",
    "latitude": "-12.0464",
    "longitude": "-77.0428",
    "road_type": "6",
    "speed_limit": "30",
    "urban_or_rural_area": "1",
    "light_conditions": "1",
    "weather_conditions": "2",
    "road_surface_conditions": "2",
    "number_of_vehicles": "2",
    "junction_detail": "13",
    "first_road_class": "3",
}


@pytest.fixture
def client(db_session, get_db_override):
    seed_status_levels(db_session)
    create_user(
        db_session,
        email="vial@test.local",
        name="Coordinador",
        role=Role.admin,
        password="password123",
    )
    db_session.add(SeverityLevel(label="SEV2", color="#F4B740", rank=2, is_default=True))
    db_session.commit()
    app = create_app()
    app.dependency_overrides[get_db] = get_db_override
    client = TestClient(app)
    client.post("/login", data={"email": "vial@test.local", "password": "password123"})
    return client


def _create(client, db_session, fields=None):
    response = client.post(
        "/incidents", data={"title": "Colisión de prueba", **(fields or {})}, follow_redirects=False
    )
    assert response.status_code == 303
    return db_session.scalar(select(Incident))


def test_road_fields_round_trip_create_edit_detail_and_list(client, db_session):
    incident = _create(client, db_session, ROAD_DATA)
    db_session.refresh(incident)
    assert incident.date == date(2026, 9, 30)
    assert incident.time == time(14, 30)
    assert incident.latitude == pytest.approx(-12.0464)
    assert incident.longitude == pytest.approx(-77.0428)
    for key in ROAD_FIELDS.keys() - {"date", "time", "latitude", "longitude"}:
        assert getattr(incident, key) == int(ROAD_DATA[key])
    listing = client.get("/").text
    assert "30/09/2026" in listing and "14:30" in listing and "Urbana" in listing
    detail = client.get(f"/incidents/{incident.id}").text
    assert 'value="2026-09-30"' in detail and 'value="14:30"' in detail
    assert "Mojada/húmeda" in detail and "Lluvia sin viento fuerte" in detail
    assert 'value="2"' in detail.split('id="ml-number_of_vehicles"', 1)[1].split(">", 1)[0]
    assert (
        'value="13" selected'
        in detail.split('name="junction_detail"', 1)[1].split("</select>", 1)[0]
    )
    assert (
        'value="3" selected'
        in detail.split('name="first_road_class"', 1)[1].split("</select>", 1)[0]
    )
    response = client.post(
        f"/incidents/{incident.id}/edit",
        data={
            "title": "Título editado",
            "severity_level_id": incident.severity_level_id,
            **ROAD_DATA,
            "road_type": "1",
            "speed_limit": "20",
            "weather_conditions": "",
            "number_of_vehicles": "17",
            "junction_detail": "16",
            "first_road_class": "6",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(incident)
    assert incident.road_type == 1 and incident.speed_limit == 20
    assert incident.weather_conditions is None
    assert incident.number_of_vehicles == 17
    assert incident.junction_detail == 16 and incident.first_road_class == 6
    assert "Rotonda" in client.get(f"/incidents/{incident.id}").text
    detail = client.get(f"/incidents/{incident.id}").text
    assert 'value="17"' in detail.split('id="ml-number_of_vehicles"', 1)[1].split(">", 1)[0]
    assert (
        'value="16" selected'
        in detail.split('name="junction_detail"', 1)[1].split("</select>", 1)[0]
    )
    assert (
        'value="6" selected'
        in detail.split('name="first_road_class"', 1)[1].split("</select>", 1)[0]
    )


def test_edit_omitted_fields_preserves_road_and_hidden_legacy_data(client, db_session):
    incident = _create(client, db_session, ROAD_DATA)
    system = System(name="Sistema anterior")
    kind = IncidentType(label="Tipo anterior", rank=1)
    db_session.add_all([system, kind])
    db_session.flush()
    incident.system_id = system.id
    incident.incident_type_id = kind.id
    db_session.commit()
    response = client.post(
        f"/incidents/{incident.id}/edit",
        data={
            "title": "Cambio de título",
            "severity_level_id": incident.severity_level_id,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(incident)
    assert incident.system_id == system.id and incident.incident_type_id == kind.id
    assert incident.road_type == 6 and incident.date == date(2026, 9, 30)
    assert incident.number_of_vehicles == 2
    assert incident.junction_detail == 13 and incident.first_road_class == 3


def test_unknown_and_absent_data_are_not_guessed(client, db_session):
    incident = _create(client, db_session, {"road_type": "9", "weather_conditions": "9"})
    db_session.refresh(incident)
    assert incident.road_type == 9 and incident.weather_conditions == 9
    assert incident.date is None and incident.speed_limit is None
    assert "Desconocido" in client.get(f"/incidents/{incident.id}").text
    for key in ("number_of_vehicles", "junction_detail", "first_road_class"):
        assert getattr(incident, key) is None
        html = client.get(f"/incidents/{incident.id}").text
        if key == "number_of_vehicles":
            assert 'value=""' in html.split(f'id="ml-{key}"', 1)[1].split(">", 1)[0]
        else:
            options = html.split(f'name="{key}"', 1)[1].split("</select>", 1)[0]
            assert '<option value="">Sin datos</option>' in options and " selected" not in options
    response = client.post(
        f"/incidents/{incident.id}/edit",
        data={"title": "Registro antiguo editado", "severity_level_id": incident.severity_level_id},
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(incident)
    assert incident.title == "Registro antiguo editado"
    assert incident.number_of_vehicles is None
    assert incident.junction_detail is None and incident.first_road_class is None


@pytest.mark.parametrize(
    "key,value",
    [
        ("latitude", "91"),
        ("latitude", "nan"),
        ("longitude", "-181"),
        ("road_type", "5"),
        ("urban_or_rural_area", "0"),
        ("light_conditions", "2"),
        ("weather_conditions", "10"),
        ("road_surface_conditions", "6"),
        ("speed_limit", "-1"),
        ("speed_limit", "30.5"),
        ("speed_limit", "201"),
        ("date", "2026-02-31"),
        ("time", "25:30"),
        ("number_of_vehicles", "0"),
        ("number_of_vehicles", "18"),
        ("number_of_vehicles", "1.5"),
        ("junction_detail", "1"),
        ("first_road_class", "7"),
    ],
)
def test_invalid_road_form_does_not_create_incident(client, db_session, key, value):
    response = client.post("/incidents", data={"title": "Inválido", **ROAD_DATA, key: value})
    assert response.status_code == 422
    assert "Datos viales no válidos" in response.json()["detail"]
    assert db_session.scalar(select(func.count()).select_from(Incident)) == 0


def test_invalid_service_edit_is_rejected_before_mutating_incident(client, db_session):
    incident = _create(client, db_session, ROAD_DATA)
    with pytest.raises(ValueError):
        update_incident(db_session, incident, title="No guardar", road_data={"speed_limit": -1})
    assert incident.title == "Colisión de prueba" and incident.speed_limit == 30


@pytest.mark.parametrize(
    "key,value",
    [
        ("road_type", "99"),
        ("number_of_vehicles", "18"),
        ("junction_detail", "1"),
        ("first_road_class", "7"),
    ],
)
def test_invalid_edit_keeps_existing_data(client, db_session, key, value):
    incident = _create(client, db_session, ROAD_DATA)
    response = client.post(
        f"/incidents/{incident.id}/edit",
        data={
            "title": "No guardar",
            "severity_level_id": incident.severity_level_id,
            key: value,
        },
    )
    assert response.status_code == 422
    db_session.refresh(incident)
    assert incident.title == "Colisión de prueba" and incident.road_type == 6
    assert incident.number_of_vehicles == 2
    assert incident.junction_detail == 13 and incident.first_road_class == 3


def test_readonly_cannot_write_road_fields(client, db_session):
    incident = _create(client, db_session, ROAD_DATA)
    create_user(
        db_session,
        email="reader@test.local",
        name="Consulta",
        role=Role.read_only,
        password="password123",
    )
    db_session.commit()
    client.get("/logout")
    client.post("/login", data={"email": "reader@test.local", "password": "password123"})
    assert client.post("/incidents", data={"title": "No guardar", **ROAD_DATA}).status_code == 403
    assert (
        client.post(
            f"/incidents/{incident.id}/edit",
            data={
                "title": "No guardar",
                "severity_level_id": incident.severity_level_id,
                **ROAD_DATA,
            },
        ).status_code
        == 403
    )
    assert 'id="edit-date"' not in client.get(f"/incidents/{incident.id}").text


def test_main_interface_is_spanish_and_technical_modules_hidden(client):
    for path in ("/", "/users", "/groups", "/settings", "/follow-ups", "/account/password"):
        assert client.get(path).status_code == 200
    login = client.get("/login").text
    assert "Iniciar sesión" in login and "Sistema de Gestión de Accidentes Viales" in login
    home = client.get("/").text
    assert "Registrar accidente" in home and 'lang="es"' in home
    assert "Prioridad de atención" in home and "Nivel 2 (SEV2)" in home
    assert "No es el resultado del Machine Learning" in home
    assert "Ubicación del accidente (opcional)" in home and "GPS" in home
    for field in ["date", "time", "latitude", "longitude"]:
        assert f'name="{field}"' in home
    for field in ROAD_FIELDS.keys() - {"date", "time", "latitude", "longitude"}:
        assert f'name="{field}"' not in home
    for field in ["system_id", "component_ids", "slack_connection_id", "video", "incident_type_id"]:
        assert f'name="{field}"' not in home
    assert 'href="/maps"' in home
    for path in ["/systems", "/components", "/alerts", "/automations", "/postmortems"]:
        assert f'href="{path}"' not in home
    settings = client.get("/settings").text
    assert "Configuración" in settings and "Roles de responsables" in settings
    assert "<h2>Slack</h2>" not in settings and "<h2>Google</h2>" not in settings


def test_database_checks_reject_invalid_categories(client, db_session):
    incident = _create(client, db_session, ROAD_DATA)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(
            text("UPDATE incidents SET road_type = 99 WHERE id = :id"), {"id": incident.id}
        )


def test_blank_inputs_clear_values_but_omitted_inputs_are_preserved():
    assert validate_road_data({"date": "", "speed_limit": ""}) == {
        "date": None,
        "speed_limit": None,
    }
    assert validate_road_data({}) == {}
    assert validate_road_data(
        {"number_of_vehicles": "", "junction_detail": "", "first_road_class": ""}
    ) == {
        "number_of_vehicles": None,
        "junction_detail": None,
        "first_road_class": None,
    }
    assert validate_road_data({"junction_detail": "-1", "first_road_class": "-1"}) == {
        "junction_detail": -1,
        "first_road_class": -1,
    }
