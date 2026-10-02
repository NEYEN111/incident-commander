from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.pipeline import Pipeline

from app.auth import require_user
from app.main import create_app
from app.models import Role, User
from app.schemas.prediction import PredictionRequest
from app.services import ml_prediction
from app.services.ml_prediction import MLPredictor, get_predictor
from app.services.users import create_user

INPUTS = {
    "day_of_week": 2,
    "hour": 14,
    "road_type": 6,
    "speed_limit": 30,
    "urban_or_rural_area": 1,
    "light_conditions": 1,
    "weather_conditions": 1,
    "road_surface_conditions": 1,
    "number_of_vehicles": 2,
    "junction_detail": 0,
    "first_road_class": 3,
}


@pytest.fixture
def client():
    app = create_app()
    # Test the API without PostgreSQL; authentication itself has existing coverage.
    app.dependency_overrides[require_user] = lambda: User(id=1)
    client = TestClient(app, raise_server_exceptions=True)
    try:
        yield client
    finally:
        client.close()


def test_real_pipeline_loads_once_even_with_concurrent_requests(monkeypatch):
    ml_prediction._load_predictor.cache_clear()
    original_load = ml_prediction.joblib.load
    calls = []

    def counted_load(path):
        calls.append(path)
        return original_load(path)

    monkeypatch.setattr(ml_prediction.joblib, "load", counted_load)
    with ThreadPoolExecutor(max_workers=4) as executor:
        predictors = list(executor.map(lambda _: get_predictor(), range(8)))
    assert len(calls) == 1
    assert all(predictor is predictors[0] for predictor in predictors)
    assert isinstance(predictors[0].pipeline, Pipeline)
    assert set(predictors[0].features) == set(INPUTS)


def test_missing_model_fails_clearly(tmp_path):
    with pytest.raises(FileNotFoundError, match="modelo_final.joblib"):
        MLPredictor(tmp_path)


def test_prediction_matches_real_pipeline():
    predictor = get_predictor()
    result = predictor.predict(PredictionRequest(**INPUTS))
    frame = pd.DataFrame([INPUTS], columns=predictor.features)
    assert result.prediction == predictor.pipeline.predict(frame)[0]
    assert result.model_version == "1.0"
    probabilities = result.probabilities.model_dump()
    assert set(probabilities) == {"Fatal", "Grave", "Leve"}
    expected = dict(zip(predictor.classes, predictor.pipeline.predict_proba(frame)[0], strict=True))
    assert probabilities == pytest.approx(expected)
    assert sum(probabilities.values()) == pytest.approx(1.0)
    assert all(0 <= probability <= 1 for probability in probabilities.values())


def test_endpoint_prediction(client):
    response = client.post("/api/predict", json=INPUTS)
    assert response.status_code == 200
    result = response.json()
    expected = get_predictor().predict(PredictionRequest(**INPUTS)).model_dump()
    assert result["prediction"] == expected["prediction"]
    assert result["model_version"] == expected["model_version"]
    assert result["probabilities"] == pytest.approx(expected["probabilities"])
    assert set(result["probabilities"]) == {"Fatal", "Grave", "Leve"}
    assert sum(result["probabilities"].values()) == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("day_of_week", 0),
        ("day_of_week", 8),
        ("hour", -1),
        ("hour", 24),
        ("road_type", 4),
        ("road_type", True),
        ("speed_limit", 0),
        ("speed_limit", 201),
        ("speed_limit", 173),
        ("speed_limit", 35),
        ("speed_limit", "30"),
        ("urban_or_rural_area", 4),
        ("light_conditions", 2),
        ("weather_conditions", 0),
        ("weather_conditions", 10),
        ("road_surface_conditions", 6),
        ("number_of_vehicles", 0),
        ("number_of_vehicles", 100),
        ("number_of_vehicles", 18),
        ("number_of_vehicles", 2.5),
        ("junction_detail", 1),
        ("first_road_class", 7),
        ("hour", None),
    ],
)
def test_endpoint_rejects_invalid_inputs(client, field, value):
    response = client.post("/api/predict", json={**INPUTS, field: value})
    assert response.status_code == 422
    assert any(error["loc"] == ["body", field] for error in response.json()["detail"])


@pytest.mark.parametrize(
    ("field", "value"),
    [("speed_limit", speed) for speed in (20, 30, 40, 50, 60, 70)]
    + [("number_of_vehicles", 1), ("number_of_vehicles", 17)],
)
def test_endpoint_accepts_observed_training_domain(client, field, value):
    response = client.post("/api/predict", json={**INPUTS, field: value})
    assert response.status_code == 200
    assert sum(response.json()["probabilities"].values()) == pytest.approx(1.0)


def test_endpoint_requires_all_fields_and_rejects_extra_fields(client):
    for field in INPUTS:
        response = client.post("/api/predict", json={k: v for k, v in INPUTS.items() if k != field})
        assert response.status_code == 422
    assert client.post("/api/predict", json={**INPUTS, "gravedad": "Leve"}).status_code == 422


@pytest.mark.parametrize("junction_detail", [-1, 0, 13, 16, 17, 18, 19, 99])
def test_endpoint_preserves_2025_junction_codes(client, junction_detail):
    response = client.post("/api/predict", json={**INPUTS, "junction_detail": junction_detail})
    assert response.status_code == 200


def test_endpoint_preserves_model_missing_and_unknown_categories(client):
    response = client.post(
        "/api/predict",
        json={
            **INPUTS,
            "light_conditions": -1,
            "road_surface_conditions": 9,
            "first_road_class": -1,
        },
    )
    assert response.status_code == 200


def test_endpoint_unavailable_model_returns_503(client, monkeypatch):
    def missing_model():
        raise FileNotFoundError("modelo_final.joblib")

    monkeypatch.setattr("app.routers.prediction.get_predictor", missing_model)
    response = client.post("/api/predict", json=INPUTS)
    assert response.status_code == 503
    assert response.json() == {"detail": "Modelo ML no disponible"}


def test_endpoint_requires_login(get_db_override):
    from app.db import get_db

    app = create_app()
    app.dependency_overrides[get_db] = get_db_override
    response = TestClient(app).post("/api/predict", json=INPUTS, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


@pytest.mark.parametrize("role", [Role.admin, Role.incident_commander, Role.read_only])
def test_endpoint_with_real_authenticated_session(db_session, get_db_override, role):
    from app.db import get_db

    create_user(
        db_session, email="ml@test.local", name="Usuario ML", role=role, password="password123"
    )
    app = create_app()
    app.dependency_overrides[get_db] = get_db_override
    client = TestClient(app)
    try:
        client.post("/login", data={"email": "ml@test.local", "password": "password123"})
        response = client.post("/api/predict", json=INPUTS)
        assert response.status_code == 200
        assert response.json()["prediction"] in {"Fatal", "Grave", "Leve"}
    finally:
        client.close()
