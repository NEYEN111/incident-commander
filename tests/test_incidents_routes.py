import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import create_app
from app.models import Incident, Role, SeverityLevel, StatusCategory, StatusLevel
from app.services import statuses
from app.services.incidents import list_incidents
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


def _sev(db_session):
    statuses.seed_status_levels(db_session)
    db_session.flush()
    lvl = SeverityLevel(label="SEV1", color="#FF5D5D", rank=1, is_default=False)
    db_session.add(lvl)
    db_session.flush()
    return lvl.id


def test_list_loads_priority_and_status_without_per_row_queries(db_session):
    statuses.seed_status_levels(db_session)
    states = list(db_session.scalars(select(StatusLevel).order_by(StatusLevel.rank)))[:3]
    for index, state in enumerate(states):
        priority = SeverityLevel(label=f"P{index}", color="#000000", rank=index)
        db_session.add(priority)
        db_session.flush()
        db_session.add(
            Incident(
                title=f"Accidente {index}",
                severity_level_id=priority.id,
                status_id=state.id,
                creation_state={},
            )
        )
    db_session.commit()
    queries = []

    def count_select(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    with Session(db_session.get_bind()) as fresh:
        connection = fresh.connection()
        event.listen(connection, "before_cursor_execute", count_select)
        try:
            rows = list_incidents(fresh)
            assert len(rows) == 3
            assert all(row.severity_level.label and row.status.label for row in rows)
            assert len(queries) == 1, f"Consultas SELECT observadas: {len(queries)}"
        finally:
            event.remove(connection, "before_cursor_execute", count_select)


def test_readonly_cannot_create(client, db_session):
    _login(client, db_session, "ro@x.io", Role.read_only)
    sev_id = _sev(db_session)
    r = client.post(
        "/incidents",
        data={"title": "X", "severity_level_id": str(sev_id)},
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_ic_can_create_and_close(client, db_session):
    _login(client, db_session, "ic@x.io", Role.incident_commander)
    sev_id = _sev(db_session)
    assert "Todavía no hay accidentes registrados." in client.get("/").text
    r = client.post(
        "/incidents",
        data={"title": "Checkout down", "severity_level_id": str(sev_id)},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert "Checkout down" in r.text
    # list shows it
    listed = client.get("/").text
    assert "Checkout down" in listed
    assert "Todavía no hay accidentes registrados." not in listed
    # close it (find id via detail listing)
    from app.services.incidents import list_incidents

    inc = list_incidents(db_session)[0]
    detail = client.get(f"/incidents/{inc.id}").text
    assert 'href="#operational-edit"' in detail and 'id="operational-edit"' in detail
    assert 'href="#edit-date"' not in detail
    r2 = client.post(f"/incidents/{inc.id}/close", headers={"HX-Request": "true"})
    assert r2.status_code == 200
    db_session.refresh(inc)
    assert inc.is_closed and inc.closed_at is not None
    assert inc.status.category == StatusCategory.closed
    assert "Cerrado" in r2.text
    assert f'action="/incidents/{inc.id}/close"' not in r2.text


def test_create_incident_with_system_and_component(client, db_session):
    # reuse this file's real helper: _login(client, db_session, email, role)
    from sqlalchemy import select

    from app.models import Incident, Role, SeverityLevel
    from app.services.catalog import create_component, create_system

    _login(client, db_session, "ic@x.io", Role.incident_commander)
    lvl = SeverityLevel(label="SEV1", color="#FF5D5D", rank=1, is_default=True)
    db_session.add(lvl)
    s = create_system(db_session, name="Billing")
    db_session.flush()
    c = create_component(db_session, name="Invoicer", system_id=s.id)
    db_session.flush()
    client.post(
        "/incidents",
        data={
            "title": "Down",
            "severity_level_id": str(lvl.id),
            "system_id": str(s.id),
            "component_ids": [str(c.id)],
        },
        headers={"HX-Request": "true"},
    )
    inc = db_session.scalar(select(Incident).order_by(Incident.id.desc()))
    assert inc.system_id == s.id and [x.name for x in inc.components] == ["Invoicer"]
