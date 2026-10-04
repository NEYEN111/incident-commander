"""Explicit synthetic demo data. Never imported by application startup."""

import argparse
import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import (
    FollowUp,
    Incident,
    IncidentPrediction,
    Role,
    SeverityLevel,
    StatusLevel,
    User,
    effective_role,
)
from app.services.catalog import seed_severity_levels
from app.services.followups import create_followup
from app.services.incident_predictions import create_prediction
from app.services.incidents import create_incident, set_incident_status
from app.services.statuses import seed_status_levels

MARKER = "Escenario sintético de demostración; no describe un accidente real."
# Valid STATS19 categories, chosen as synthetic scenarios, never as target labels.
# road, mph, area, light, weather, surface, vehicles, junction, road class
SCENARIOS = [
    ("Colisión urbana en cruce", (6, 30, 1, 1, 1, 1, 2, 13, 3)),
    ("Salida de vía rural nocturna", (6, 60, 2, 6, 1, 1, 1, 0, 3)),
    ("Colisión en avenida con lluvia", (3, 40, 1, 4, 2, 2, 3, 17, 3)),
    ("Incidente en rotonda", (1, 20, 1, 1, 1, 1, 2, 16, 4)),
    ("Colisión en carretera principal", (3, 70, 2, 1, 1, 1, 2, 0, 1)),
    ("Salida de vía con superficie mojada", (6, 50, 2, 7, 2, 2, 1, 0, 6)),
    ("Colisión urbana de baja velocidad", (6, 20, 1, 1, 1, 1, 2, 18, 6)),
    ("Colisión rural con niebla", (6, 60, 2, 6, 7, 2, 2, 0, 3)),
    ("Colisión en intersección iluminada", (6, 30, 1, 4, 1, 1, 3, 17, 4)),
    ("Incidente en carretera secundaria", (6, 40, 2, 1, 1, 1, 1, 19, 5)),
    ("Registro pendiente de análisis", None),
    ("Registro sin ubicación confirmada", None),
]
FEATURES = [
    "road_type",
    "speed_limit",
    "urban_or_rural_area",
    "light_conditions",
    "weather_conditions",
    "road_surface_conditions",
    "number_of_vehicles",
    "junction_detail",
    "first_road_class",
]


def validate_demo_url(value: str | None) -> str:
    if not value:
        raise ValueError("Define DEMO_DATABASE_URL explícitamente; no se usa DATABASE_URL ni .env.")
    url = make_url(value)
    if url.get_backend_name() != "postgresql" or "demo" not in (url.database or "").lower():
        raise ValueError("Se requiere PostgreSQL y un nombre de base que contenga 'demo'.")
    return value


def seed_demo(db: Session, *, actor_email: str) -> dict:
    actor = db.scalar(select(User).where(User.email == actor_email, User.is_active.is_(True)))
    if actor is None or effective_role(actor) not in (Role.admin, Role.incident_commander):
        raise ValueError(
            "El actor debe ser un usuario existente, activo y autorizado para gestionar accidentes."
        )
    # Serialize simultaneous runs, without schema changes or a demo marker migration.
    db.execute(text("SELECT pg_advisory_xact_lock(6241606)"))
    seed_severity_levels(db)
    seed_status_levels(db)
    priorities = list(db.scalars(select(SeverityLevel).order_by(SeverityLevel.rank)))
    states = list(db.scalars(select(StatusLevel).order_by(StatusLevel.rank)))
    today = datetime.now(UTC).date()
    created, analyzed, ids = 0, 0, []
    for index, (name, values) in enumerate(SCENARIOS):
        title = f"[DEMO {index + 1:02d}] {name}"
        incident = db.scalar(select(Incident).where(Incident.title == title))
        if incident is not None and incident.description != MARKER:
            raise ValueError(
                f"Conflicto con un registro ajeno al DEMO: {title}; no se sobrescribe."
            )
        if incident is None:
            road = {
                "date": today - timedelta(days=index * 3),
                "time": time((8 + index * 2) % 24, 15),
            }
            if index != 11:
                # Synthetic locations near Leeds; no real collision is represented.
                road.update(latitude=53.8008 + index * 0.009, longitude=-1.5491 + index * 0.011)
            if values is not None:
                road.update(zip(FEATURES, values, strict=True))
            incident = create_incident(
                db,
                title=title,
                description=MARKER,
                severity_level_id=priorities[index % len(priorities)].id,
                is_private=False,
                created_by=actor.id,
                road_data=road,
            )
            set_incident_status(
                db, incident, status_id=states[index % len(states)].id, by_user=actor.id
            )
            created += 1
        ids.append(incident.id)
        if (
            values is not None
            and db.scalar(
                select(IncidentPrediction.id)
                .where(IncidentPrediction.incident_id == incident.id)
                .limit(1)
            )
            is None
        ):
            create_prediction(db, incident, created_by=actor.id)
            analyzed += 1
        if index in (0, 2, 7):
            task_title = "[DEMO] Revisar documentación sintética"
            if (
                db.scalar(
                    select(FollowUp.id).where(
                        FollowUp.incident_id == incident.id, FollowUp.title == task_title
                    )
                )
                is None
            ):
                create_followup(
                    db,
                    incident,
                    title=task_title,
                    description=MARKER,
                    assignee_id=actor.id,
                    due_on=today + timedelta(days=3),
                    created_by=actor.id,
                )
    predictions = list(
        db.scalars(
            select(IncidentPrediction)
            .where(IncidentPrediction.incident_id.in_(ids))
            .order_by(IncidentPrediction.id)
        )
    )
    latest = {p.incident_id: p.predicted_severity for p in predictions}
    return {
        "created": created,
        "new_predictions": analyzed,
        "demo_accidents": len(ids),
        "latest_prediction_distribution": dict(Counter(latest.values())),
        "without_prediction": len(ids) - len(latest),
        "incident_ids": ids,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-demo",
        action="store_true",
        help="Confirma que la base es exclusiva de demostración",
    )
    parser.add_argument(
        "--actor-email", required=True, help="Usuario gestor existente en la base DEMO"
    )
    args = parser.parse_args()
    if not args.confirm_demo:
        parser.error("Debes confirmar la base de demostración con --confirm-demo.")
    try:
        url = validate_demo_url(os.environ.get("DEMO_DATABASE_URL"))
        engine = create_engine(url)
        try:
            with Session(engine) as db, db.begin():
                summary = seed_demo(db, actor_email=args.actor_email)
        finally:
            engine.dispose()
    except Exception as exc:
        # Never echo database connection strings, credentials or driver errors.
        parser.exit(
            1,
            f"No se cargó el DEMO ({type(exc).__name__}). Revisa la base, el actor y el modelo. No se guardaron cambios parciales.\n",
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
