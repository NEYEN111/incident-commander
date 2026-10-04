import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import create_app
from app.models import Incident, IncidentPrediction, Role
from app.services.users import create_user


@pytest.fixture
def client(db_session, get_db_override):
    app = create_app()
    app.dependency_overrides[get_db] = get_db_override
    with_client = TestClient(app)
    yield with_client
    with_client.close()


def test_insights_requires_login(client):
    response = client.get("/insights", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_readonly_can_view_road_analysis_and_date_filter(client, db_session):
    user = create_user(
        db_session, email="ro@x.io", name="Consulta", role=Role.read_only, password="password123"
    )
    today = datetime.now(UTC).date()
    db_session.add(
        Incident(
            title="Actual",
            date=today,
            time=None,
            creation_state={},
            created_at=datetime.now(UTC) - timedelta(days=400),
        )
    )
    db_session.add(Incident(title="Antiguo", date=today - timedelta(days=100), creation_state={}))
    db_session.add(Incident(title="Sin fecha", date=None, creation_state={}))
    db_session.commit()
    client.post("/login", data={"email": user.email, "password": "password123"})
    response = client.get("/insights")
    assert response.status_code == 200
    assert "<h1>Estadísticas</h1>" in response.text
    for text in (
        "Total de accidentes",
        "Pendientes de análisis",
        "Distribución de gravedad estimada",
        "Calidad y completitud de datos",
        "Accidentes por día de la semana",
        "Accidentes por hora del día",
        "Evolución de accidentes",
        "1 accidentes sin fecha",
        "Aún no hay suficientes predicciones para mostrar la distribución.",
        "Modelo de Machine Learning",
        "Random Forest",
    ):
        assert text in response.text
    for text in ("Por prioridad operativa", "Por estado", "MTTR", "Tareas pendientes"):
        assert text not in response.text
    assert "/static/road-analytics.css" in response.text
    assert client.get("/static/road-analytics.css").status_code == 200
    assert "cdn" not in response.text.lower()
    assert client.get("/insights?days=90").status_code == 200
    all_time = client.get("/insights?days=0")
    assert all_time.status_code == 200 and "incluidos en el total" in all_time.text
    assert client.get("/insights?days=31").status_code == 422


def test_insights_empty_state_and_model_metadata_fallback(client, db_session, monkeypatch):
    user = create_user(
        db_session,
        email="empty@x.io",
        name="Consulta",
        role=Role.read_only,
        password="password123",
    )
    db_session.commit()
    client.post("/login", data={"email": user.email, "password": "password123"})
    response = client.get("/insights?days=0")
    assert response.status_code == 200
    assert "Todavía no hay accidentes registrados." in response.text
    assert re.findall(r'data-metric="[^"]+">(\d+)</dd>', response.text) == ["0"] * 4
    assert "analytics-ml-track" not in response.text
    assert "<svg" not in response.text
    assert "Variables utilizadas</dt><dd>11" in response.text
    assert "Árboles</dt><dd>150" in response.text
    assert "Evaluación del modelo entrenado" in response.text
    assert "STATS19" in response.text and "20305 para test" in response.text
    for value in ("0,5577", "0,3663", "0,4618", "0,6259"):
        assert f"<dd>{value}</dd>" in response.text
    assert "no son las estadísticas de los accidentes registrados" in response.text
    monkeypatch.setattr("app.routers.insights.load_model_metadata", lambda: None)
    response = client.get("/insights")
    assert response.status_code == 200
    assert "Los metadatos del modelo no están disponibles." in response.text
    monkeypatch.setattr("app.routers.insights.load_model_evaluation", lambda: None)
    assert "No está disponible la evaluación documentada" in client.get("/insights").text


def test_insights_summary_distribution_and_series_use_latest_real_records(client, db_session):
    user = create_user(
        db_session,
        email="results@x.io",
        name="Consulta",
        role=Role.read_only,
        password="password123",
    )
    today = datetime.now(UTC).date()
    incidents = [
        Incident(title="Actual analizado", date=today, latitude=0, longitude=0, creation_state={}),
        Incident(title="Actual pendiente", date=today, creation_state={}),
        Incident(title="Anterior analizado", date=today - timedelta(days=40), creation_state={}),
        Incident(title="Analizado sin fecha", date=None, creation_state={}),
    ]
    db_session.add_all(incidents)
    db_session.flush()
    now = datetime.now(UTC)
    for incident, label, when in [
        (incidents[0], "Fatal", now - timedelta(hours=1)),
        (incidents[0], "Leve", now),
        (incidents[2], "Grave", now),
        (incidents[3], "Fatal", now),
    ]:
        db_session.add(
            IncidentPrediction(
                incident_id=incident.id,
                created_by=user.id,
                predicted_severity=label,
                prob_fatal=int(label == "Fatal"),
                prob_grave=int(label == "Grave"),
                prob_leve=int(label == "Leve"),
                model_version="insights-test",
                input_data={},
                created_at=when,
            )
        )
    db_session.commit()
    client.post("/login", data={"email": user.email, "password": "password123"})
    for days, expected in [(30, [2, 1, 1, 1]), (90, [3, 2, 1, 1]), (0, [4, 3, 1, 1])]:
        response = client.get(f"/insights?days={days}")
        assert response.status_code == 200
        assert [
            int(n) for n in re.findall(r'data-metric="[^"]+">(\d+)</dd>', response.text)
        ] == expected
        assert f'href="/insights?days={days}" class="active" aria-current="page"' in response.text
        if days == 90:
            distribution = response.text.split('<ul class="analytics-ml-bars">', 1)[1].split(
                "</ul>", 1
            )[0]
            for label in ("Grave", "Leve"):
                row = distribution.split(f'data-ml-class="{label}"', 1)[1].split("</li>", 1)[0]
                assert "width: 50.0%" in row and "50,0 %" in row
    html = client.get("/insights?days=30").text
    distribution = html.split('<ul class="analytics-ml-bars">', 1)[1].split("</ul>", 1)[0]
    for label, percentage in [("Fatal", "0.0"), ("Grave", "0.0"), ("Leve", "100.0")]:
        row = distribution.split(f'data-ml-class="{label}"', 1)[1].split("</li>", 1)[0]
        assert f"width: {percentage}%" in row
        assert f"{percentage.replace('.', ',')} %" in row
    assert "Total de accidentes: 2" in html and "Con predicción ML: 1" in html
    assert "<td>2</td><td>1</td>" in html
    assert "Sin datos" in html
    assert "independiente de la prioridad operativa" in html
    assert "SEV1 / SEV2 / SEV3 expresan prioridad operativa" in html
