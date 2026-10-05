from fastapi.testclient import TestClient

from app.main import create_app
from app.routers import alerts, automation, catalog, postmortems


def test_road_app_does_not_register_legacy_sre_routes():
    app = create_app()
    paths = set(app.openapi()["paths"])
    for router in (alerts.router, automation.router, catalog.router, postmortems.router):
        assert all(route.path not in paths for route in router.routes)
    # Removing a shared router must not disconnect the active road application.
    assert {
        "/",
        "/incidents/{incident_id}",
        "/maps",
        "/insights",
        "/follow-ups",
        "/users",
        "/groups",
        "/settings",
        "/api/predict",
    } <= paths
    client = TestClient(app)
    for path in ("/postmortems", "/automations", "/alerts", "/components", "/systems"):
        assert client.get(path, follow_redirects=False).status_code == 404
