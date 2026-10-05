from app.i18n import priority_display
from app.models import SeverityLevel


def test_priority_names_follow_configuration_without_inventing_urgency():
    level = SeverityLevel(label="SEV1", rank=7, color="#000000")
    assert priority_display(level) == "Nivel 7 (SEV1)"
    assert "Alta" not in priority_display(level)
    level.label = "Atención inmediata"
    assert priority_display(level) == "Atención inmediata"
    assert priority_display(None) == "Sin asignar"
