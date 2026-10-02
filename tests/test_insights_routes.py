from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import create_app
from app.models import Incident, Role
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
    assert "Análisis vial" in response.text
    for text in (
        "Total de accidentes",
        "Accidentes sin predicción ML",
        "Última predicción ML por accidente",
        "Calidad y completitud de datos",
        "Accidentes por día de la semana",
        "Accidentes por hora del día",
        "Evolución de accidentes",
        "Sin datos",
        "1 accidentes sin fecha",
    ):
        assert text in response.text
    for text in ("Por prioridad operativa", "Por estado", "MTTR", "Tareas pendientes", "SEV1"):
        assert text not in response.text
    assert "/static/road-analytics.css" in response.text
    assert client.get("/static/road-analytics.css").status_code == 200
    assert "cdn" not in response.text.lower()
    assert client.get("/insights?days=90").status_code == 200
    all_time = client.get("/insights?days=0")
    assert all_time.status_code == 200 and "incluidos en el total" in all_time.text
    assert client.get("/insights?days=31").status_code == 422
