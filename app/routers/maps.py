from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.auth import require_user
from app.db import get_db
from app.models import User
from app.services.accident_map import map_incidents
from app.templating import templates

router = APIRouter()


@router.get("/maps", response_class=HTMLResponse)
def maps_page(request: Request, user: User = Depends(require_user)):
    return templates.TemplateResponse(request, "maps.html", {"current_user": user})


@router.get("/maps/incidents.json")
def incidents_json(
    date_from: date | None = None,
    date_to: date | None = None,
    prediction: Literal["Fatal", "Grave", "Leve", "none"] | None = None,
    zone: int | None = Query(default=None, ge=1, le=3),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status_code=422, detail="La fecha inicial no puede superar la fecha final"
        )
    return map_incidents(db, date_from=date_from, date_to=date_to, prediction=prediction, zone=zone)
