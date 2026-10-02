"""Road analytics based on accident dates and one latest ML result per accident."""

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from math import isfinite

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import Incident, IncidentPrediction
from app.road_fields import ROAD_FIELDS, road_display
from app.services.incident_predictions import PredictionDataError, prediction_request_from_incident

WEEKDAYS = ("Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado")
ROAD_BREAKDOWNS = (
    "urban_or_rural_area",
    "road_type",
    "weather_conditions",
    "road_surface_conditions",
    "light_conditions",
)


def window_since(days: int, *, today: date | None = None) -> date | None:
    """Inclusive calendar window: today plus the previous days-1 dates (UTC)."""
    if days <= 0:
        return None
    return (today or datetime.now(UTC).date()) - timedelta(days=days - 1)


def _bars(counts: Counter, labels: list[str], *, denominator: int) -> list[dict]:
    maximum = max(counts.values(), default=0) or 1
    return [
        {
            "label": label,
            "count": counts[label],
            "width": round(counts[label] / maximum * 100, 1),
            "percentage": round(counts[label] / denominator * 100, 1) if denominator else 0,
        }
        for label in labels
    ]


def _coordinates(incident: Incident) -> bool:
    lat, lon = incident.latitude, incident.longitude
    return (
        lat is not None
        and lon is not None
        and isfinite(lat)
        and isfinite(lon)
        and -90 <= lat <= 90
        and -180 <= lon <= 180
    )


def _timeline(dates: list[date], since: date | None, until: date | None) -> dict:
    start = since or min(dates, default=None)
    end = until or max(dates, default=None)
    if start is None or end is None:
        return {"granularity": "Diaria", "rows": []}
    monthly = (end - start).days > 90
    counts = Counter(d.strftime("%Y-%m" if monthly else "%d/%m/%Y") for d in dates)
    labels = []
    cursor = start.replace(day=1) if monthly else start
    while cursor <= end:
        labels.append(cursor.strftime("%Y-%m" if monthly else "%d/%m/%Y"))
        if monthly:
            cursor = date(cursor.year + cursor.month // 12, cursor.month % 12 + 1, 1)
        else:
            cursor += timedelta(days=1)
    return {
        "granularity": "Mensual" if monthly else "Diaria",
        "rows": _bars(counts, labels, denominator=len(dates)),
    }


def compute_insights(db: Session, *, since: date | None, until: date | None = None) -> dict:
    # One outer join, with deterministic ties: never load predictions per accident.
    latest = select(
        IncidentPrediction.incident_id,
        IncidentPrediction.predicted_severity,
        func.row_number()
        .over(
            partition_by=IncidentPrediction.incident_id,
            order_by=(IncidentPrediction.created_at.desc(), IncidentPrediction.id.desc()),
        )
        .label("position"),
    ).subquery()
    query = select(Incident, latest.c.predicted_severity).outerjoin(
        latest, and_(latest.c.incident_id == Incident.id, latest.c.position == 1)
    )
    if since is not None:
        until = until or datetime.now(UTC).date()
        query = query.where(Incident.date >= since, Incident.date <= until)
    rows = list(db.execute(query))
    total = len(rows)
    predicted = Counter(severity for _, severity in rows if severity is not None)
    with_prediction = sum(predicted.values())
    dates = [incident.date for incident, _ in rows if incident.date is not None]
    hours = Counter(
        f"{incident.time.hour:02d}:00" for incident, _ in rows if incident.time is not None
    )
    weekdays = Counter(WEEKDAYS[(d.weekday() + 1) % 7] for d in dates)
    with_coordinates = sum(_coordinates(incident) for incident, _ in rows)
    ml_ready = 0
    for incident, _ in rows:
        try:
            prediction_request_from_incident(incident)
        except PredictionDataError:
            continue
        ml_ready += 1
    # Undated records stay outside a date-filtered sample; in Todo they are included.
    undated = (
        db.scalar(select(func.count()).select_from(Incident).where(Incident.date.is_(None)))
        if since is not None
        else total - len(dates)
    )
    distributions = []
    for field in ROAD_BREAKDOWNS:
        counts = Counter(road_display(field, getattr(incident, field)) for incident, _ in rows)
        labels = list(ROAD_FIELDS[field]["options"].values())
        if counts["Sin datos"]:
            labels.append("Sin datos")
        distributions.append(
            {"title": ROAD_FIELDS[field]["label"], "rows": _bars(counts, labels, denominator=total)}
        )
    return {
        "total": total,
        "with_prediction": with_prediction,
        "without_prediction": total - with_prediction,
        "with_coordinates": with_coordinates,
        "ml_ready": ml_ready,
        "undated": undated,
        "without_time": total - sum(hours.values()),
        "since": since,
        "until": until,
        "prediction_distribution": _bars(
            predicted, ["Fatal", "Grave", "Leve"], denominator=with_prediction
        ),
        "road_distributions": distributions,
        "weekdays": _bars(weekdays, list(WEEKDAYS), denominator=len(dates)),
        "hours": _bars(hours, [f"{h:02d}:00" for h in range(24)], denominator=sum(hours.values())),
        "timeline": _timeline(dates, since, until),
        "quality": _bars(
            Counter(
                {
                    "Con coordenadas": with_coordinates,
                    "Con los 11 datos compatibles con ML": ml_ready,
                    "Con al menos una predicción ML": with_prediction,
                }
            ),
            [
                "Con coordenadas",
                "Con los 11 datos compatibles con ML",
                "Con al menos una predicción ML",
            ],
            denominator=total,
        ),
    }
