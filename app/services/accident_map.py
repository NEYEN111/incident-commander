"""Minimal map data, filtered by the latest ML prediction rather than operational priority."""

from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.i18n import priority_label
from app.models import Incident, IncidentPrediction, SeverityLevel, StatusLevel


def map_incidents(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    prediction: str | None = None,
    zone: int | None = None,
) -> dict:
    ranked = select(
        IncidentPrediction.incident_id,
        IncidentPrediction.predicted_severity,
        IncidentPrediction.prob_fatal,
        IncidentPrediction.prob_grave,
        IncidentPrediction.prob_leve,
        func.row_number()
        .over(
            partition_by=IncidentPrediction.incident_id,
            order_by=(IncidentPrediction.created_at.desc(), IncidentPrediction.id.desc()),
        )
        .label("position"),
    ).subquery()
    query = (
        select(
            Incident.id,
            Incident.title,
            Incident.latitude,
            Incident.longitude,
            Incident.date,
            Incident.time,
            Incident.urban_or_rural_area,
            SeverityLevel.label.label("operational_priority"),
            SeverityLevel.rank.label("priority_rank"),
            StatusLevel.label.label("status"),
            ranked.c.predicted_severity,
            ranked.c.prob_fatal,
            ranked.c.prob_grave,
            ranked.c.prob_leve,
        )
        .outerjoin(ranked, and_(ranked.c.incident_id == Incident.id, ranked.c.position == 1))
        .outerjoin(SeverityLevel, SeverityLevel.id == Incident.severity_level_id)
        .outerjoin(StatusLevel, StatusLevel.id == Incident.status_id)
        .where(
            Incident.latitude.between(-90, 90),
            Incident.longitude.between(-180, 180),
        )
    )
    if date_from is not None:
        query = query.where(Incident.date >= date_from)
    if date_to is not None:
        query = query.where(Incident.date <= date_to)
    if prediction == "none":
        query = query.where(ranked.c.predicted_severity.is_(None))
    elif prediction is not None:
        query = query.where(ranked.c.predicted_severity == prediction)
    if zone is not None:
        query = query.where(Incident.urban_or_rural_area == zone)
    incidents = []
    for row in db.execute(query.order_by(Incident.id)):
        incidents.append(
            {
                "id": row.id,
                "title": row.title,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "date": row.date.isoformat() if row.date is not None else None,
                "time": row.time.isoformat(timespec="minutes") if row.time is not None else None,
                "urban_or_rural_area": row.urban_or_rural_area,
                "operational_priority": row.operational_priority,
                "operational_priority_label": priority_label(
                    row.operational_priority, row.priority_rank
                ),
                "status": row.status,
                "latest_prediction": {
                    "prediction": row.predicted_severity,
                    "probabilities": {
                        "Fatal": row.prob_fatal,
                        "Grave": row.prob_grave,
                        "Leve": row.prob_leve,
                    },
                }
                if row.predicted_severity is not None
                else None,
            }
        )
    return {"incidents": incidents, "count": len(incidents)}
