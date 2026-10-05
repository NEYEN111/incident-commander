import json
import logging
from copy import deepcopy
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from httpx import Client, HTTPStatusError, MockTransport, Request, Response
from pydantic import SecretStr
from sqlalchemy import func, select

from app.config import get_settings
from app.db import get_db
from app.main import create_app
from app.models import Incident, IncidentPrediction, Role
from app.schemas.prediction import PredictionRequest, PredictionResponse
from app.services import llm_assistant as service
from app.services.incident_predictions import prediction_request_from_incident
from app.services.users import create_user

KEY = "assistant-test-secret-not-a-real-key"
ROAD_DATA = {
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


@pytest.fixture
def llm(monkeypatch):
    settings = get_settings().model_copy(
        update={
            "hive_api_key": SecretStr(KEY),
            "hive_model": "custom-flash",
            "hive_base_url": "https://hive.test/api/v3/",
        }
    )
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    predictor = MagicMock()
    predictor.predict.return_value = PredictionResponse(
        prediction="Grave",
        probabilities={"Fatal": 0.18, "Grave": 0.57, "Leve": 0.25},
        model_version="rf-test",
    )
    monkeypatch.setattr(service, "get_predictor", lambda: predictor)
    client = MagicMock()
    client.__enter__.return_value = client
    client.post.return_value.json.return_value = {
        "choices": [
            {"message": {"content": "El Random Forest estima Grave. No representa certeza."}}
        ]
    }
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(service, "Client", factory)
    return SimpleNamespace(settings=settings, predictor=predictor, client=client, factory=factory)


@pytest.fixture
def client(db_session, get_db_override, llm):
    app = create_app()
    app.dependency_overrides[get_db] = get_db_override
    client = TestClient(app)
    yield client
    client.close()


@pytest.fixture
def authenticated(client, db_session):
    user = create_user(
        db_session,
        email="assistant@test.local",
        name="Consulta",
        role=Role.read_only,
        password="password123",
    )
    db_session.commit()
    client.post("/login", data={"email": user.email, "password": "password123"})
    return client, user


@pytest.fixture
def accident(db_session):
    incident = Incident(
        title="Accidente del asistente",
        description="Texto privado que no se envía",
        latitude=51.5,
        longitude=-0.1,
        creation_state={},
        **ROAD_DATA,
    )
    db_session.add(incident)
    db_session.commit()
    return incident


def test_page_and_navigation_load_for_readonly(authenticated, llm):
    client, _ = authenticated
    html = client.get("/assistant").text
    assert 'href="/assistant" class="active" aria-current="page"' in html
    assert "Random Forest → Fatal / Grave / Leve" in html
    assert "DeepSeek vía Hive → explicación conversacional" in html
    assert "Gemini" not in html
    assert "Todavía no hay accidentes registrados" in html
    assert KEY not in html
    llm.predictor.predict.assert_not_called()
    llm.factory.assert_not_called()


@pytest.mark.parametrize("htmx", [False, True])
def test_auth_policy_for_page_and_question(client, htmx):
    headers = {"HX-Request": "true"} if htmx else {}
    for method, path, data in [
        ("get", "/assistant", None),
        ("post", "/assistant/ask", {"incident_id": 1, "question": "Explica"}),
    ]:
        response = getattr(client, method)(
            path, **({"data": data} if data else {}), headers=headers, follow_redirects=False
        )
        assert response.status_code == (401 if htmx else 303)
        assert response.headers["hx-redirect" if htmx else "location"] == "/login"


def test_selection_uses_exact_inputs_and_does_not_save(authenticated, accident, db_session, llm):
    client, _ = authenticated
    before = deepcopy({c.key: getattr(accident, c.key) for c in Incident.__mapper__.column_attrs})
    response = client.get(f"/assistant?incident_id={accident.id}")
    assert response.status_code == 200
    inputs = llm.predictor.predict.call_args.args[0]
    assert isinstance(inputs, PredictionRequest)
    assert inputs.model_dump() == prediction_request_from_incident(accident).model_dump()
    assert inputs.day_of_week == 1 and inputs.hour == 14
    assert "GRAVE" in response.text and "57.0 %" in response.text
    assert "Ver los 11 datos utilizados" in response.text
    llm.factory.assert_not_called()
    db_session.refresh(accident)
    assert {c.key: getattr(accident, c.key) for c in Incident.__mapper__.column_attrs} == before
    assert db_session.scalar(select(func.count()).select_from(IncidentPrediction)) == 0


@pytest.mark.parametrize(
    "field, label",
    [
        ("date", "Fecha del accidente"),
        ("time", "Hora del accidente"),
        ("weather_conditions", "Condiciones meteorológicas"),
    ],
)
def test_missing_data_never_calls_predictor_or_hive(
    authenticated, accident, db_session, llm, field, label
):
    client, _ = authenticated
    setattr(accident, field, None)
    db_session.commit()
    for response in [
        client.get(f"/assistant?incident_id={accident.id}"),
        client.post(
            "/assistant/ask",
            data={"incident_id": accident.id, "question": "Explícame"},
            headers={"HX-Request": "true"},
        ),
    ]:
        assert response.status_code == 200
        assert "Faltan datos necesarios" in response.text and label in response.text
    llm.predictor.predict.assert_not_called()
    llm.factory.assert_not_called()


def test_explanation_receives_only_real_inference_context(authenticated, accident, db_session, llm):
    client, user = authenticated
    saved = IncidentPrediction(
        incident_id=accident.id,
        created_by=user.id,
        predicted_severity="Fatal",
        prob_fatal=1,
        prob_grave=0,
        prob_leve=0,
        model_version="older",
        input_data={"saved": "unchanged"},
    )
    db_session.add(saved)
    db_session.commit()
    snapshot = deepcopy(
        {c.key: getattr(saved, c.key) for c in IncidentPrediction.__mapper__.column_attrs}
    )
    response = client.post(
        "/assistant/ask",
        data={"incident_id": accident.id, "question": "¿Qué probabilidades estimó?"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    llm.client.post.assert_called_once()
    assert llm.client.post.call_args.args == ("https://hive.test/api/v3/chat/completions",)
    call = llm.client.post.call_args.kwargs
    body = call["json"]
    assert set(body) == {"model", "messages", "stream", "reasoning_effort", "max_completion_tokens"}
    assert len(body["messages"]) == 2
    assert body["messages"][0] == {"role": "system", "content": service.SYSTEM_INSTRUCTION}
    assert body["messages"][1]["role"] == "user"
    contents = body["messages"][1]["content"]
    payload = json.loads(contents)
    assert payload["variables"] == prediction_request_from_incident(accident).model_dump()
    assert len(payload["variables"]) == 11 and len(payload["datos_legibles"]) == 11
    assert payload["resultado_random_forest"] == llm.predictor.predict.return_value.model_dump()
    assert payload["pregunta"] == "¿Qué probabilidades estimó?"
    assert KEY not in contents
    assert "Texto privado" not in contents and accident.title not in contents
    assert "latitude" not in contents and "longitude" not in contents
    assert "day_of_week" not in response.text
    assert "18.0 %" in response.text and "57.0 %" in response.text and "25.0 %" in response.text
    assert body["model"] == "custom-flash"
    assert body["stream"] is False
    assert body["reasoning_effort"] == "none"
    assert body["max_completion_tokens"] == 600
    for instruction in (
        "texto plano, sin Markdown",
        "no uses **, #, tablas Markdown ni backticks",
        "porcentajes con una decimal",
        "0.095 se muestra como 9.5 %",
        "incluye las 11 variables completas",
    ):
        assert instruction in body["messages"][0]["content"]
    assert call["headers"] == {
        "Authorization": f"Bearer {llm.settings.hive_api_key.get_secret_value()}",
        "Content-Type": "application/json",
    }
    assert type(call["headers"]["Authorization"]) is str
    llm.factory.assert_called_once_with(timeout=30.0)
    llm.client.post.return_value.raise_for_status.assert_called_once_with()
    assert "No hay SHAP" in service.SYSTEM_INSTRUCTION
    assert KEY not in response.text
    assert db_session.scalar(select(func.count()).select_from(IncidentPrediction)) == 1
    db_session.refresh(saved)
    assert {
        c.key: getattr(saved, c.key) for c in IncidentPrediction.__mapper__.column_attrs
    } == snapshot


def test_no_key_keeps_app_and_ml_available(authenticated, accident, llm):
    client, _ = authenticated
    llm.settings.hive_api_key = SecretStr("")
    response = client.get(f"/assistant?incident_id={accident.id}")
    assert "El asistente LLM no está configurado en este entorno" in response.text
    assert "GRAVE" in response.text
    assert client.get("/healthz").status_code == 200
    assert client.get("/").status_code == 200
    html = client.post(
        "/assistant/ask", data={"incident_id": accident.id, "question": "Explica"}
    ).text
    assert "no está configurado" in html and "GRAVE" in html
    llm.factory.assert_not_called()


def test_blank_model_uses_configurable_flash_default(authenticated, accident, llm):
    client, _ = authenticated
    llm.settings.hive_model = " "
    llm.settings.hive_base_url = " "
    response = client.post(
        "/assistant/ask", data={"incident_id": accident.id, "question": "Explica"}
    )
    assert response.status_code == 200
    assert llm.client.post.call_args.kwargs["json"]["model"] == service.DEFAULT_HIVE_MODEL
    assert llm.client.post.call_args.args == (f"{service.DEFAULT_HIVE_BASE_URL}/chat/completions",)
    llm.factory.assert_called_once_with(timeout=30.0)


def test_real_http_client_sends_hive_contract_without_network(llm, monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        return Response(200, json={"choices": [{"message": {"content": "Explicación de prueba"}}]})

    monkeypatch.setattr(
        service, "Client", lambda **options: Client(transport=MockTransport(respond), **options)
    )
    analysis = service.AssistantAnalysis(
        inputs=prediction_request_from_incident(Incident(**ROAD_DATA)),
        result=llm.predictor.predict.return_value,
    )
    assert service.explain_analysis(analysis, "Explica") == "Explicación de prueba"
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == "https://hive.test/api/v3/chat/completions"
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert request.headers["Content-Type"] == "application/json"
    payload = json.loads(request.content)
    assert payload == {
        "model": "custom-flash",
        "messages": [
            {"role": "system", "content": service.SYSTEM_INSTRUCTION},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "variables": analysis.inputs.model_dump(),
                        "datos_legibles": analysis.input_rows(),
                        "resultado_random_forest": analysis.result.model_dump(),
                        "pregunta": "Explica",
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "stream": False,
        "reasoning_effort": "none",
        "max_completion_tokens": 600,
    }


@pytest.mark.parametrize(
    "body",
    [
        {"error": {"message": KEY}},
        {"choices": []},
        {"choices": [{"message": {"content": None}}]},
        {"choices": [{"message": {"content": {"unexpected": KEY}}}]},
    ],
)
def test_malformed_hive_response_is_safe_and_keeps_ml(authenticated, accident, llm, caplog, body):
    client, _ = authenticated
    llm.client.post.return_value.json.return_value = body
    response = client.post(
        "/assistant/ask",
        data={"incident_id": accident.id, "question": "Explica"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "El asistente IA no pudo responder en este momento." in response.text
    assert "57.0 %" in response.text
    assert KEY not in response.text and KEY not in caplog.text
    llm.client.post.assert_called_once()


@pytest.mark.parametrize("failure", [RuntimeError(KEY), TimeoutError("timeout"), None])
def test_hive_failure_is_safe_and_keeps_ml(authenticated, accident, llm, failure, caplog):
    client, _ = authenticated
    if failure:
        llm.client.post.side_effect = failure
    else:
        llm.client.post.return_value.json.return_value = {"choices": [{"message": {"content": ""}}]}
    response = client.post(
        "/assistant/ask",
        data={"incident_id": accident.id, "question": "Explica"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "El asistente IA no pudo responder" in response.text and "57.0 %" in response.text
    assert KEY not in response.text and KEY not in caplog.text


def test_permission_denied_logs_only_type_and_http_code(authenticated, accident, llm, caplog):
    client, _ = authenticated
    caplog.set_level(logging.WARNING, logger=service.__name__)
    request = Request(
        "POST",
        "https://hive.test/api/v3/chat/completions",
        headers={"Authorization": f"Bearer {KEY}"},
    )
    error_response = Response(403, request=request, json={"error": {"message": KEY}})
    llm.client.post.return_value.raise_for_status.side_effect = HTTPStatusError(
        KEY, request=request, response=error_response
    )
    response = client.post(
        "/assistant/ask",
        data={"incident_id": accident.id, "question": "Explica"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "El asistente IA no pudo responder en este momento." in response.text
    assert "57.0 %" in response.text
    records = [r for r in caplog.records if r.name == service.__name__]
    assert len(records) == 1
    assert records[0].getMessage() == "Fallo del LLM: tipo=HTTPStatusError codigo=403"
    assert records[0].levelno == logging.WARNING
    assert records[0].exc_info is None
    assert KEY not in response.text and KEY not in caplog.text


def test_non_numeric_error_code_cannot_leak_credentials(authenticated, accident, llm, caplog):
    client, _ = authenticated
    caplog.set_level(logging.WARNING, logger=service.__name__)
    failure = RuntimeError(KEY)
    failure.code = KEY
    llm.client.post.side_effect = failure
    response = client.post(
        "/assistant/ask",
        data={"incident_id": accident.id, "question": "Explica"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "El asistente IA no pudo responder en este momento." in response.text
    assert "tipo=RuntimeError codigo=None" in caplog.text
    assert KEY not in response.text and KEY not in caplog.text


def test_question_and_response_are_escaped_and_key_redacted(authenticated, accident, llm):
    client, _ = authenticated
    llm.client.post.return_value.json.return_value = {
        "choices": [{"message": {"content": f"<script>alert(1)</script> {KEY}"}}]
    }
    html = client.post(
        "/assistant/ask",
        data={"incident_id": accident.id, "question": "<img src=x onerror=alert(1)>"},
        headers={"HX-Request": "true"},
    ).text
    assert "<script>" not in html and "<img" not in html
    assert "&lt;script&gt;" in html and "&lt;img" in html
    assert KEY not in html and "[credencial oculta]" in html


@pytest.mark.parametrize("question", [" ", "x" * 2001])
def test_invalid_question_does_not_call_services(authenticated, accident, llm, question):
    client, _ = authenticated
    response = client.post(
        "/assistant/ask",
        data={"incident_id": accident.id, "question": question},
        headers={"HX-Request": "true"},
    )
    assert "entre 1 y 2000 caracteres" in response.text
    llm.predictor.predict.assert_not_called()
    llm.factory.assert_not_called()


def test_unknown_accident_does_not_call_services(authenticated, llm):
    client, _ = authenticated
    assert client.get("/assistant?incident_id=9999").status_code == 404
    assert (
        client.post("/assistant/ask", data={"incident_id": 9999, "question": "Explica"}).status_code
        == 404
    )
    llm.predictor.predict.assert_not_called()
    llm.factory.assert_not_called()


def test_model_failure_does_not_call_hive(authenticated, accident, llm):
    client, _ = authenticated
    llm.predictor.predict.side_effect = RuntimeError("Model unavailable")
    html = client.post(
        "/assistant/ask", data={"incident_id": accident.id, "question": "Explica"}
    ).text
    assert "No se pudo ejecutar el modelo ML" in html
    llm.factory.assert_not_called()


def test_real_random_forest_inference_without_persistence(
    authenticated, accident, db_session, monkeypatch, llm
):
    from app.services.ml_prediction import get_predictor

    client, _ = authenticated
    real = get_predictor()
    predictor = MagicMock(wraps=real)
    monkeypatch.setattr(service, "get_predictor", lambda: predictor)
    html = client.get(f"/assistant?incident_id={accident.id}").text
    predictor.predict.assert_called_once()
    expected = real.predict(prediction_request_from_incident(accident))
    assert expected.prediction.upper() in html
    for p in expected.probabilities.model_dump().values():
        assert f"{p * 100:.1f} %" in html
    assert db_session.scalar(select(func.count()).select_from(IncidentPrediction)) == 0
    llm.factory.assert_not_called()
