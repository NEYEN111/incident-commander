"""Build validated inputs and save independent prediction snapshots."""

import logging

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Incident, IncidentPrediction
from app.road_fields import ROAD_FIELDS
from app.schemas.prediction import PredictionRequest
from app.services.ml_prediction import get_predictor

log = logging.getLogger(__name__)


class PredictionDataError(ValueError):
    """The accident is missing data or has values outside the model contract."""


class PredictionUnavailableError(RuntimeError):
    """The saved model could not perform inference."""


def prediction_request_from_incident(incident: Incident) -> PredictionRequest:
    values = {
        name: getattr(incident, name)
        for name in PredictionRequest.model_fields
        if name not in ("day_of_week", "hour")
    }
    values["day_of_week"] = (incident.date.weekday() + 1) % 7 + 1 if incident.date else None
    values["hour"] = incident.time.hour if incident.time else None
    try:
        return PredictionRequest.model_validate(values)
    except ValidationError as exc:
        missing, incompatible = [], []
        sources = {"day_of_week": "date", "hour": "time"}
        for error in exc.errors():
            field = error["loc"][0]
            label = ROAD_FIELDS[sources.get(field, field)]["label"]
            if values[field] is None:
                missing.append(label)
            else:
                if field == "speed_limit":
                    label += " (20, 30, 40, 50, 60 o 70 mph)"
                incompatible.append(label)
        messages = []
        if missing:
            messages.append("Faltan datos necesarios: " + ", ".join(missing))
        if incompatible:
            messages.append("Datos incompatibles con el modelo: " + ", ".join(incompatible))
        raise PredictionDataError(
            ". ".join(messages) + ". Revisa los datos del accidente."
        ) from exc


def create_prediction(db: Session, incident: Incident, *, created_by: int) -> IncidentPrediction:
    inputs = prediction_request_from_incident(incident)
    try:
        result = get_predictor().predict(inputs)
    except Exception as exc:
        log.exception("No se pudo ejecutar la predicción ML del accidente %s", incident.id)
        raise PredictionUnavailableError(
            "No se pudo ejecutar el modelo ML. Inténtalo de nuevo más tarde."
        ) from exc
    prediction = IncidentPrediction(
        incident_id=incident.id,
        created_by=created_by,
        predicted_severity=result.prediction,
        prob_fatal=result.probabilities.Fatal,
        prob_grave=result.probabilities.Grave,
        prob_leve=result.probabilities.Leve,
        model_version=result.model_version,
        input_data=inputs.model_dump(),
    )
    db.add(prediction)
    db.flush()
    return prediction


def latest_prediction_labels(db: Session, incident_ids: list[int]) -> dict[int, str]:
    """Load the list's latest labels in one query, including timestamp ties."""
    if not incident_ids:
        return {}
    ranked = (
        select(
            IncidentPrediction.incident_id,
            IncidentPrediction.predicted_severity,
            func.row_number()
            .over(
                partition_by=IncidentPrediction.incident_id,
                order_by=(IncidentPrediction.created_at.desc(), IncidentPrediction.id.desc()),
            )
            .label("position"),
        )
        .where(IncidentPrediction.incident_id.in_(incident_ids))
        .subquery()
    )
    return dict(
        db.execute(
            select(ranked.c.incident_id, ranked.c.predicted_severity).where(ranked.c.position == 1)
        ).all()
    )


def recent_predictions(db: Session, incident_id: int) -> list[IncidentPrediction]:
    # One latest result plus up to five earlier results, including timestamp ties.
    return list(
        db.scalars(
            select(IncidentPrediction)
            .where(IncidentPrediction.incident_id == incident_id)
            .order_by(IncidentPrediction.created_at.desc(), IncidentPrediction.id.desc())
            .limit(6)
        )
    )
