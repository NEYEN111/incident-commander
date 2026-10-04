import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import create_app
from app.models import Alert, InboundIntegration, Incident, Role, SeverityLevel
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


def _alert(db_session):
    integ = InboundIntegration(name="i", kind="generic", token="tk")
    db_session.add(integ)
    db_session.flush()
    a = Alert(
        integration_id=integ.id, source="generic", dedup_key="dk", title="Boom", status="firing"
    )
    db_session.add(a)
    db_session.add(SeverityLevel(label="SEV1", color="#FF5D5D", rank=1, is_default=True))
    db_session.commit()
    return a


def test_inbox_requires_login(client, db_session):
    assert client.get("/alerts", follow_redirects=False).status_code in (302, 303, 307)


def test_inbox_renders_sidebar_when_authenticated(client, db_session):
    # Regression: the inbox route must pass current_user so base.html renders the
    # left sidebar nav (it was missing, leaving the page without navigation).
    _login(client, db_session, "ic@x.io", Role.incident_commander)
    response = client.get("/alerts")
    assert response.status_code == 200
    html = response.text
    assert '<aside class="pilot-sidebar" aria-label="Barra lateral">' in html
    assert 'aria-label="Navegación principal"' in html
    for route in ("/", "/maps", "/insights", "/follow-ups", "/account/password", "/logout"):
        assert f'href="{route}"' in html
    assert "ic@x.io" in html
    # SRE catalog navigation is intentionally hidden, not removed from the backend.
    assert 'href="/systems"' not in html
    assert client.get("/systems").status_code == 200
    for route in ("/users", "/groups", "/settings"):
        assert f'href="{route}"' not in html
        assert client.get(route).status_code == 403


def test_login_page_renders_without_sidebar_when_unauthenticated(client, db_session):
    # The current_user context processor must default to None for routes without an
    # auth dependency (request.state.current_user unset), so unauthenticated pages
    # use the plain layout — and never leak a previous request's user.
    _login(client, db_session, "ic@x.io", Role.incident_commander)
    client.post("/logout")
    html = client.get("/login").text
    assert 'aria-label="Barra lateral"' not in html
    assert 'aria-label="Navegación principal"' not in html
    assert "ic@x.io" not in html


def test_readonly_cannot_declare(client, db_session):
    a = _alert(db_session)
    _login(client, db_session, "ro@x.io", Role.read_only)
    assert client.post(f"/alerts/{a.id}/declare", follow_redirects=False).status_code == 403


def test_declare_creates_and_links_incident(client, db_session):
    a = _alert(db_session)
    _login(client, db_session, "ic@x.io", Role.incident_commander)
    r = client.post(f"/alerts/{a.id}/declare", follow_redirects=False)
    assert r.status_code == 303
    db_session.refresh(a)
    inc = db_session.scalar(select(Incident).where(Incident.id == a.incident_id))
    assert inc is not None and inc.title == "Boom"


def test_attach_to_existing(client, db_session):
    a = _alert(db_session)
    _login(client, db_session, "ic@x.io", Role.incident_commander)
    client.post(f"/alerts/{a.id}/declare", follow_redirects=False)  # creates incident 1
    db_session.refresh(a)
    inc_id = a.incident_id
    a.incident_id = None
    db_session.commit()
    r = client.post(
        f"/alerts/{a.id}/attach", data={"incident_id": str(inc_id)}, follow_redirects=False
    )
    assert r.status_code == 303
    db_session.refresh(a)
    assert a.incident_id == inc_id


def test_resolve(client, db_session):
    a = _alert(db_session)
    _login(client, db_session, "ic@x.io", Role.incident_commander)
    client.post(f"/alerts/{a.id}/resolve", follow_redirects=False)
    db_session.refresh(a)
    assert a.status == "resolved"
