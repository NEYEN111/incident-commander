import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import create_app
from app.models import Role
from app.services.users import bootstrap_admin, create_user


@pytest.fixture
def client(db_session, get_db_override):
    app = create_app()
    app.dependency_overrides[get_db] = get_db_override
    return TestClient(app)


def _login(client, db_session, email, role):
    bootstrap_admin(db_session, "admin@localhost")
    create_user(db_session, email=email, name="U", role=role, password="pw-123456")
    db_session.flush()
    client.post("/login", data={"email": email, "password": "pw-123456"})


def test_removed_systems_route_returns_404(client, db_session):
    _login(client, db_session, "ic@x.io", Role.incident_commander)

    response = client.post(
        "/systems",
        data={"name": "Checkout", "owner_team_id": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 404
