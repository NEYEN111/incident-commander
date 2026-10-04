from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import create_app
from app.models import Group, User, effective_role
from app.services.users import bootstrap_admin


class RoleOptions(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_role = False
        self.values = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "select":
            self.in_role = attrs.get("name") == "role"
        if tag == "option" and self.in_role:
            self.values.append(attrs["value"])

    def handle_endtag(self, tag):
        if tag == "select":
            self.in_role = False


@pytest.mark.parametrize("path", ["/users", "/groups"])
@pytest.mark.parametrize("role", ["incident_commander", "read_only"])
def test_rendered_role_can_be_submitted(path, role, db_session, get_db_override):
    app = create_app()
    app.dependency_overrides[get_db] = get_db_override
    client = TestClient(app)
    _, password = bootstrap_admin(db_session, "admin@localhost")
    db_session.flush()
    client.post("/login", data={"email": "admin@localhost", "password": password})
    client.post("/account/password", data={"new_password": "Admin-123", "confirm": "Admin-123"})
    options = RoleOptions()
    options.feed(client.get(path).text)
    assert role in options.values
    payload = {"name": "Prueba", "role": options.values[options.values.index(role)]}
    if path == "/users":
        payload["email"] = "new@x.io"
    response = client.post(path, data=payload, follow_redirects=False)
    assert response.status_code == 303
    if path == "/users":
        entity = db_session.scalar(select(User).where(User.email == payload["email"]))
        assert effective_role(entity).value == role
    else:
        entity = db_session.scalar(select(Group).where(Group.name == payload["name"]))
        assert entity.role.value == role
