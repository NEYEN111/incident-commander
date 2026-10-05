from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.auth import require_user
from app.db import get_db
from app.models import User
from app.services.insights import (
    compute_insights,
    load_model_evaluation,
    load_model_metadata,
    window_since,
)
from app.templating import templates

router = APIRouter()


@router.get("/about", response_class=HTMLResponse)
def about_project(request: Request, user: User = Depends(require_user)):
    return templates.TemplateResponse(
        request,
        "about.html",
        {
            "current_user": user,
            "model_info": load_model_metadata(),
            "model_evaluation": load_model_evaluation(),
        },
    )


@router.get("/insights", response_class=HTMLResponse)
def insights_page(
    request: Request,
    days: int = Query(default=30, ge=0),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if days not in (0, 30, 90):
        raise HTTPException(status_code=422, detail="Selecciona 30 días, 90 días o Todo")
    data = compute_insights(db, since=window_since(days))
    return templates.TemplateResponse(
        request,
        "insights.html",
        {
            "current_user": user,
            "data": data,
            "days": days,
            "model_info": load_model_metadata(),
            "model_evaluation": load_model_evaluation(),
        },
    )
