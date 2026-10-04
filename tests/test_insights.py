from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import event

from app.models import Incident, IncidentPrediction, Role, SeverityLevel
from app.services import insights
from app.services.users import create_user


@pytest.fixture
def user(db_session):
    user = create_user(
        db_session,
        email="analytics@test.local",
        name="Consulta",
        role=Role.read_only,
        password="password123",
    )
    db_session.flush()
    return user


def accident(db, **values):
    fields = dict(
        title="Accidente",
        date=date(2026, 9, 27),
        time=time(0, 45),
        road_type=6,
        speed_limit=30,
        urban_or_rural_area=1,
        light_conditions=1,
        weather_conditions=1,
        road_surface_conditions=1,
        number_of_vehicles=2,
        junction_detail=0,
        first_road_class=3,
        latitude=0,
        longitude=0,
        creation_state={},
    )
    incident = Incident(**{**fields, **values})
    db.add(incident)
    db.flush()
    return incident


def prediction(db, incident, user, label, when):
    probs = {"Fatal": (1, 0, 0), "Grave": (0, 1, 0), "Leve": (0, 0, 1)}[label]
    db.add(
        IncidentPrediction(
            incident_id=incident.id,
            created_by=user.id,
            predicted_severity=label,
            prob_fatal=probs[0],
            prob_grave=probs[1],
            prob_leve=probs[2],
            model_version="analytics-test",
            input_data={},
            created_at=when,
        )
    )
    db.flush()


def counts(rows):
    return {row["label"]: row["count"] for row in rows}


def test_calendar_windows():
    today = date(2026, 10, 2)
    assert insights.window_since(0, today=today) is None
    assert insights.window_since(30, today=today) == today - timedelta(days=29)
    assert insights.window_since(90, today=today) == today - timedelta(days=89)


def test_window_uses_accident_date_not_creation_and_separates_undated(db_session):
    today = date(2026, 10, 2)
    since = insights.window_since(30, today=today)
    now = datetime.now(UTC)
    accident(db_session, date=since, created_at=now - timedelta(days=200))
    accident(db_session, date=today, created_at=now - timedelta(days=200))
    accident(db_session, date=since - timedelta(days=1), created_at=now)
    accident(db_session, date=today + timedelta(days=1), created_at=now)
    accident(db_session, date=None)
    data = insights.compute_insights(db_session, since=since, until=today)
    assert data["total"] == 2 and data["undated"] == 1
    assert len(data["timeline"]["rows"]) == 30
    assert sum(row["count"] for row in data["timeline"]["rows"]) == 2
    assert insights.compute_insights(db_session, since=None)["total"] == 5


def test_latest_prediction_only_with_timestamp_and_id_ties_and_no_n_plus_one(db_session, user):
    a, b, _ = [accident(db_session) for _ in range(3)]
    when = datetime(2026, 9, 28, tzinfo=UTC)
    prediction(db_session, a, user, "Fatal", when)
    prediction(db_session, a, user, "Grave", when + timedelta(hours=1))
    prediction(db_session, b, user, "Fatal", when)
    prediction(db_session, b, user, "Leve", when)
    queries = []
    engine = db_session.get_bind()

    def record_queries(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(engine, "before_cursor_execute", record_queries)
    try:
        data = insights.compute_insights(
            db_session, since=date(2026, 9, 1), until=date(2026, 9, 30)
        )
    finally:
        event.remove(engine, "before_cursor_execute", record_queries)
    assert len(queries) == 2  # joined latest results plus count of undated accidents
    assert data["total"] == 3 and data["with_prediction"] == 2
    assert data["without_prediction"] == 1
    assert counts(data["prediction_distribution"]) == {"Fatal": 0, "Grave": 1, "Leve": 1}
    assert [row["percentage"] for row in data["prediction_distribution"]] == [0, 50, 50]


def test_road_labels_and_zone_unknown_is_distinct_from_missing(db_session):
    for zone in (1, 1, 2, 3, None):
        accident(db_session, urban_or_rural_area=zone)
    data = insights.compute_insights(db_session, since=None)
    by_title = {item["title"]: counts(item["rows"]) for item in data["road_distributions"]}
    assert by_title["Zona del accidente"] == {
        "Urbana": 2,
        "Rural": 1,
        "No determinada": 1,
        "Sin datos": 1,
    }
    assert by_title["Tipo de vía"]["Calzada única"] == 5
    assert by_title["Condiciones meteorológicas"]["Despejado sin viento fuerte"] == 5
    assert by_title["Estado de la superficie"]["Seca"] == 5
    assert by_title["Condiciones de iluminación"]["Luz diurna"] == 5


def test_weekday_hour_and_evolution_do_not_invent_missing_values(db_session):
    sunday = date(2026, 9, 27)
    for day in range(7):
        accident(db_session, date=sunday + timedelta(days=day), time=time(day, 59))
    accident(db_session, date=None, time=None)
    data = insights.compute_insights(db_session, since=None)
    assert list(counts(data["weekdays"])) == list(insights.WEEKDAYS)
    assert set(counts(data["weekdays"]).values()) == {1}
    hours = counts(data["hours"])
    assert all(hours[f"{hour:02d}:00"] == 1 for hour in range(7))
    assert sum(hours.values()) == 7 and data["without_time"] == 1
    assert len(data["timeline"]["rows"]) == 7
    assert sum(row["count"] for row in data["timeline"]["rows"]) == 7
    assert data["undated"] == 1


@pytest.mark.parametrize(
    "missing",
    [
        "date",
        "time",
        "road_type",
        "speed_limit",
        "urban_or_rural_area",
        "light_conditions",
        "weather_conditions",
        "road_surface_conditions",
        "number_of_vehicles",
        "junction_detail",
        "first_road_class",
    ],
)
def test_ml_completeness_requires_each_of_11_source_fields(db_session, missing):
    accident(db_session)
    accident(db_session, **{missing: None})
    data = insights.compute_insights(db_session, since=None)
    assert data["ml_ready"] == 1 and data["total"] == 2


def test_ml_completeness_rejects_incompatible_speed_and_coordinates_require_pair(db_session):
    accident(db_session, speed_limit=173)
    accident(db_session, longitude=None)
    accident(db_session, date=None, time=None, latitude=None)
    data = insights.compute_insights(db_session, since=None)
    assert data["ml_ready"] == 1
    assert data["with_coordinates"] == 1  # zero coordinates are valid
    assert counts(data["quality"]) == {
        "Con coordenadas": 1,
        "Con los 11 datos compatibles con ML": 1,
        "Con al menos una predicción ML": 0,
    }


def test_operational_priority_never_enters_ml_distribution(db_session, user):
    severity = SeverityLevel(label="SEV1", rank=1, color="#ff0000", is_default=True)
    db_session.add(severity)
    db_session.flush()
    a = accident(db_session, severity_level_id=severity.id)
    accident(db_session, severity_level_id=severity.id)
    prediction(db_session, a, user, "Leve", datetime.now(UTC))
    data = insights.compute_insights(db_session, since=None)
    assert counts(data["prediction_distribution"]) == {"Fatal": 0, "Grave": 0, "Leve": 1}
    assert data["without_prediction"] == 1
    assert "SEV1" not in str(data) and "by_severity" not in data


def test_empty_and_monthly_all_time_evolution(db_session):
    data = insights.compute_insights(db_session, since=None)
    assert data["total"] == 0 and data["timeline"]["rows"] == []
    assert all(row["percentage"] == 0 for row in data["quality"])
    accident(db_session, date=date(2025, 12, 31))
    accident(db_session, date=date(2026, 4, 1))
    data = insights.compute_insights(db_session, since=None)
    assert data["timeline"]["granularity"] == "Mensual"
    assert counts(data["timeline"]["rows"]) == {
        "2025-12": 1,
        "2026-01": 0,
        "2026-02": 0,
        "2026-03": 0,
        "2026-04": 1,
    }


@pytest.mark.parametrize("span, granularity", [(6, "Diaria"), (120, "Mensual")])
def test_evolution_keeps_zero_intervals_and_counts_analyzed_accidents_once(
    db_session, user, span, granularity
):
    start = date(2026, 1, 1)
    first = accident(db_session, date=start)
    accident(db_session, date=start)
    last = accident(db_session, date=start + timedelta(days=span))
    undated = accident(db_session, date=None)
    now = datetime.now(UTC)
    prediction(db_session, first, user, "Fatal", now)
    prediction(db_session, first, user, "Leve", now + timedelta(hours=1))
    prediction(db_session, last, user, "Grave", now)
    prediction(db_session, undated, user, "Leve", now)
    data = insights.compute_insights(db_session, since=None)
    timeline = data["timeline"]
    assert timeline["granularity"] == granularity
    assert data["with_prediction"] == 3
    assert timeline["dated_total"] == 3 and timeline["predicted_total"] == 2
    assert timeline["rows"][0]["count"] == 2
    assert timeline["rows"][0]["predicted_count"] == 1
    assert timeline["rows"][-1]["predicted_count"] == 1
    assert all(row["count"] == row["predicted_count"] == 0 for row in timeline["rows"][1:-1])
    assert sum(row["predicted_count"] for row in timeline["rows"]) == 2
    assert all(row["count"] >= row["predicted_count"] for row in timeline["rows"])


def test_model_metadata_unavailable_or_invalid_is_not_fabricated(tmp_path):
    path = tmp_path / "missing.json"
    assert insights.load_model_metadata(path) is None
    path.write_text("not json", encoding="utf-8")
    assert insights.load_model_metadata(path) is None
    path.write_text("[]", encoding="utf-8")
    assert insights.load_model_metadata(path) is None
