from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.auth import require_user
from app.db import get_db
from app.models import Incident, User
from app.services.incident_predictions import PredictionDataError, PredictionUnavailableError
from app.services.incidents import list_incidents
from app.services.llm_assistant import (
    AssistantUnavailableError,
    analyze_incident,
    assistant_configured,
    explain_analysis,
)
from app.templating import templates

router = APIRouter()


def _context(db: Session, incident_id: int | None) -> dict:
    context = {
        "configured": assistant_configured(),
        "incident": None,
        "analysis": None,
        "error": None,
    }
    if incident_id is not None:
        incident = db.get(Incident, incident_id)
        if incident is None:
            raise HTTPException(status_code=404, detail="Accidente no encontrado")
        context["incident"] = incident
        try:
            context["analysis"] = analyze_incident(incident)
        except (PredictionDataError, PredictionUnavailableError) as exc:
            context["error"] = str(exc)
    return context


@router.get("/assistant", response_class=HTMLResponse)
def assistant_page(
    request: Request,
    incident_id: int | None = Query(default=None, ge=1),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    context = _context(db, incident_id)
    return templates.TemplateResponse(
        request,
        "assistant.html",
        {**context, "incidents": list_incidents(db), "current_user": user},
    )


@router.post("/assistant/ask", response_class=HTMLResponse)
def assistant_ask(
    request: Request,
    incident_id: int = Form(ge=1),
    question: str = Form(default=""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    question = question.strip()
    # Reject excessive/empty input before inference or an external call.
    if not question or len(question) > 2000:
        context = {
            "configured": assistant_configured(),
            "incident": db.get(Incident, incident_id),
            "analysis": None,
            "error": "Escribe una pregunta de entre 1 y 2000 caracteres.",
        }
        if context["incident"] is None:
            raise HTTPException(status_code=404, detail="Accidente no encontrado")
    else:
        context = _context(db, incident_id)
    context.update(question=question[:2000], answer=None)
    if not context["error"]:
        try:
            context["answer"] = explain_analysis(context["analysis"], question)
        except AssistantUnavailableError as exc:
            context["error"] = str(exc)
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(request, "partials/assistant_exchange.html", context)
    return templates.TemplateResponse(
        request,
        "assistant.html",
        {**context, "incidents": list_incidents(db), "current_user": user},
    )
