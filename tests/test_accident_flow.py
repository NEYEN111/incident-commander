"""One real-model flow through HTTP, persisted snapshots, rendered statistics and map."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import create_app
from app.models import Incident, IncidentPrediction, Role, SeverityLevel
from app.services.statuses import seed_status_levels
from app.services.users import create_user


def test_accident_ml_persistence_rendered_statistics_and_map(db_session, get_db_override):
    user = create_user(
        db_session,
        email="flow@test.local",
        name="Coordinador",
        role=Role.incident_commander,
        password="password123",
    )
    priority = SeverityLevel(label="SEV1", color="#E5484D", rank=1, is_default=True)
    db_session.add(priority)
    seed_status_levels(db_session)
    db_session.commit()
    app = create_app()
    app.dependency_overrides[get_db] = get_db_override
    # Match the existing HTTP fixtures: the startup bootstrap uses the application's
    # DATABASE_URL directly, while these routes use the isolated get_db override.
    client = TestClient(app)
    try:
        login = client.post(
            "/login",
            data={"email": user.email, "password": "password123"},
            follow_redirects=False,
        )
        assert login.status_code == 303
        created = client.post(
            "/incidents",
            data={
                "title": "Colisión sintética de flujo",
                "severity_level_id": priority.id,
                "date": "2026-10-03",
                "time": "18:45",
                "latitude": "53.81",
                "longitude": "-1.56",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        incident = db_session.scalars(select(Incident)).one()
        home = client.get("/").text
        assert "ML: Pendiente" in home
        registration = re.search(r'<details class="accident-registration"([^>]*)>', home)
        assert registration and "open" not in registration.group(1)
        assert "<summary>Registrar accidente</summary>" in home
        before = client.get("/maps/incidents.json")
        assert before.status_code == 200
        assert before.json()["incidents"][0]["latest_prediction"] is None
        # Submit the same inputs the compact ML form sends; date/hour remain automatic.
        inputs = {
            "road_type": "6",
            "speed_limit": "30",
            "urban_or_rural_area": "1",
            "light_conditions": "1",
            "weather_conditions": "1",
            "road_surface_conditions": "1",
            "number_of_vehicles": "2",
            "junction_detail": "13",
            "first_road_class": "3",
        }
        for _ in range(2):
            analysed = client.post(
                f"/incidents/{incident.id}/predict",
                data=inputs,
                follow_redirects=False,
            )
            assert analysed.status_code == 303
            assert analysed.headers["location"] == f"/incidents/{incident.id}#ml-result-title"
        predictions = db_session.scalars(
            select(IncidentPrediction).order_by(IncidentPrediction.id)
        ).all()
        assert len(predictions) == 2
        latest = predictions[-1]
        assert latest.incident_id == incident.id and latest.created_by == user.id
        assert latest.predicted_severity in {"Fatal", "Grave", "Leve"}
        assert len(latest.input_data) == 11
        assert latest.input_data["day_of_week"] == 7 and latest.input_data["hour"] == 18
        probabilities = {
            "Fatal": latest.prob_fatal,
            "Grave": latest.prob_grave,
            "Leve": latest.prob_leve,
        }
        assert sum(probabilities.values()) == pytest.approx(1)
        assert all(0 <= p <= 1 for p in probabilities.values())
        assert latest.model_version and latest.created_at
        detail = client.get(f"/incidents/{incident.id}")
        assert detail.status_code == 200
        assert f"Gravedad estimada: {latest.predicted_severity}" in detail.text
        assert f'data-prediction-id="{predictions[0].id}"' in detail.text
        assert "La predicción del modelo es independiente de la prioridad operativa" in detail.text
        pending = client.post("/incidents", data={"title": "Pendiente sin ubicación"})
        assert pending.status_code == 200
        home = client.get("/").text
        assert f"ML: {latest.predicted_severity}" in home and "ML: Pendiente" in home
        assert "Prioridad operativa: SEV1" in home
        stats = client.get("/insights?days=0")
        assert stats.status_code == 200
        assert 'href="/insights?days=0" class="active" aria-current="page"' in stats.text
        metrics = re.findall(r'data-metric="([^"]+)">(\d+)</dd>', stats.text)
        assert dict(metrics) == {"total": "2", "analyzed": "1", "pending": "1", "located": "1"}
        for label in ("Fatal", "Grave", "Leve"):
            row = stats.text.split(f'data-ml-class="{label}"', 1)[1].split("</li>", 1)[0]
            count = int(label == latest.predicted_severity)
            assert f'class="analytics-ml-count">{count} ' in row
            assert f"{count * 100},0 %" in row
        mapped = client.get("/maps/incidents.json")
        assert mapped.status_code == 200 and mapped.json()["count"] == 1
        point = mapped.json()["incidents"][0]
        assert point["id"] == incident.id
        assert point["operational_priority"] == "SEV1"
        assert point["latest_prediction"]["prediction"] == latest.predicted_severity
        assert point["latest_prediction"]["probabilities"] == pytest.approx(probabilities)
        assert point["operational_priority"] != point["latest_prediction"]["prediction"]
        filtered = client.get(f"/maps/incidents.json?prediction={latest.predicted_severity}")
        assert filtered.status_code == 200 and filtered.json()["count"] == 1
        assert client.get("/maps/incidents.json?prediction=none").json()["count"] == 0
        db_session.refresh(incident)
        assert incident.severity_level_id == priority.id
        closed = client.post(f"/incidents/{incident.id}/close", headers={"HX-Request": "true"})
        assert closed.status_code == 200
        assert f"ML: {latest.predicted_severity}" in closed.text
        assert "ML: Pendiente" not in closed.text
        assert "Prioridad operativa: SEV1" in closed.text
    finally:
        client.close()
