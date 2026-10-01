from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.i18n import APP_NAME, ui_es
from app.models import effective_role
from app.road_fields import ROAD_FIELDS, road_display, road_values
from app.services.markdown import render_markdown


def _auth_context(request) -> dict:
    # get_current_user stashes the resolved user on request.state; routes without
    # an auth dependency (login, invite, ...) never set it, so default to None.
    return {"current_user": getattr(request.state, "current_user", None)}


templates = Jinja2Templates(
    directory=str(Path(__file__).parent / "templates"),
    context_processors=[_auth_context],
)

# Available in every template (e.g. base.html nav gating).
templates.env.globals["effective_role"] = effective_role
templates.env.globals.update(
    app_name=APP_NAME, road_fields=ROAD_FIELDS, road_values=road_values, road_display=road_display
)
templates.env.filters["ui_es"] = ui_es

# Jinja2 filter: {{ text | markdown }} → sanitized HTML string
templates.env.filters["markdown"] = render_markdown


def _from_json(s):
    import json

    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return []


templates.env.filters["from_json"] = _from_json

from app.services.custom_fields import display_value  # noqa: E402

templates.env.globals["display_value"] = display_value


def _timeago(dt) -> str:
    if not dt:
        return "—"
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    d = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    secs = (now - d).total_seconds()
    if secs < 60:
        return "ahora"
    if secs < 3600:
        return f"hace {int(secs // 60)} min"
    if secs < 86400:
        return f"hace {int(secs // 3600)} h"
    return f"hace {int(secs // 86400)} días"


templates.env.filters["timeago"] = _timeago
