from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import create_app
from app.models import Role, SlackConnection
from app.services.users import bootstrap_admin, create_user
from app.settings_store import google_settings, slack_settings


@pytest.fixture
def client(db_session, get_db_override):
    app = create_app()
    app.dependency_overrides[get_db] = get_db_override
    return TestClient(app)


def _admin(client, db_session):
    _, pw = bootstrap_admin(db_session, "admin@localhost")
    db_session.flush()
    client.post("/login", data={"email": "admin@localhost", "password": pw})
    client.post("/account/password", data={"new_password": "Admin-123", "confirm": "Admin-123"})


def test_settings_hides_configured_integrations_but_preserves_install(client, db_session):
    _admin(client, db_session)
    s = slack_settings(db_session)
    s.client_id, s.client_secret, s.enabled = "cid", "csec", True
    g = google_settings(db_session)
    g.service_account_json = '{"type":"service_account","client_email":"bot@proj.iam"}'
    g.impersonate_email = "ops@acme.io"
    g.enabled = True
    db_session.add(
        SlackConnection(team_id="T1", team_name="Acme", bot_token="xoxb-1", created_by=1)
    )
    db_session.flush()
    response = client.get("/settings")
    assert response.status_code == 200
    html = response.text
    # SRE integrations are intentionally hidden even when configured. GET must
    # neither erase their settings/connections nor expose their credentials.
    assert "/connections/slack/install" not in html
    assert 'name="service_account_json"' not in html
    assert "bot@proj.iam" not in html and "xoxb-1" not in html
    db_session.expire_all()
    assert slack_settings(db_session).client_secret == "csec"
    assert google_settings(db_session).impersonate_email == "ops@acme.io"
    connection = db_session.scalar(select(SlackConnection).where(SlackConnection.team_id == "T1"))
    assert connection.team_name == "Acme" and connection.bot_token == "xoxb-1"
    install = client.get("/connections/slack/install", follow_redirects=False)
    assert install.status_code == 307
    destination = urlparse(install.headers["location"])
    assert destination.scheme == "https" and destination.netloc == "slack.com"
    query = parse_qs(destination.query)
    assert query["client_id"] == ["cid"]
    assert query["state"][0] and query["scope"][0]


def test_settings_hides_unconfigured_integrations_and_rejects_install(client, db_session):
    _admin(client, db_session)
    response = client.get("/settings")
    assert response.status_code == 200
    html = response.text
    assert "/connections/slack/install" not in html
    assert 'name="service_account_json"' not in html
    assert "/connections/google/connect" not in html
    # The preserved route still refuses an unconfigured integration.
    install = client.get("/connections/slack/install", follow_redirects=False)
    assert install.status_code == 303 and install.headers["location"] == "/settings"
    assert not slack_settings(db_session).enabled


def test_settings_hides_sre_forms_and_preserves_admin_permissions(client, db_session):
    _admin(client, db_session)
    response = client.get("/settings")
    assert response.status_code == 200
    html = response.text
    assert 'name="service_account_json"' not in html
    assert 'name="impersonate_email"' not in html
    assert "/connections/google/connect" not in html
    # Required administration remains present; hidden SRE routes retain RBAC.
    for action in ("smtp", "sso", "severity", "statuses"):
        assert f'action="/settings/{action}"' in html
    create_user(
        db_session,
        email="reader@example.test",
        name="Reader",
        role=Role.read_only,
        password="pw-123456",
    )
    db_session.commit()
    client.post("/logout")
    client.post("/login", data={"email": "reader@example.test", "password": "pw-123456"})
    assert client.get("/settings").status_code == 403
    assert client.get("/connections/slack/install", follow_redirects=False).status_code == 403
    assert client.post("/settings/google", data={"enabled": "true"}).status_code == 403
    assert client.post("/settings/slack", data={"enabled": "true"}).status_code == 403
    assert not google_settings(db_session).enabled
    assert not slack_settings(db_session).enabled


def test_connections_redirects_to_settings_for_admin(client, db_session):
    _admin(client, db_session)
    r = client.get("/connections", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/settings"
