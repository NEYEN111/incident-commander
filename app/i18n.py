"""Spanish labels for existing catalogue values without rewriting stored data."""

APP_NAME = "Sistema de Gestión de Accidentes Viales"

_LABELS = {
    "triage": "Pendiente",
    "active": "En atención",
    "admin": "Administrador",
    "incident_commander": "Coordinador",
    "read_only": "Solo lectura",
    "Admins": "Administradores",
    "Incident Commanders": "Coordinadores",
    "Read-only": "Solo lectura",
    "Incident Lead": "Responsable del accidente",
    "Communications": "Comunicaciones",
    "Scribe": "Relator",
    "Triage": "Pendiente",
    "Investigating": "En atención",
    "Identified": "Identificado",
    "Monitoring": "En seguimiento",
    "Closed": "Cerrado",
    "open": "Pendiente",
    "completed": "Completado",
    "cancelled": "Cancelado",
    "opened": "Registro",
    "closed": "Cierre",
    "reopened": "Reapertura",
    "note": "Nota",
    "update": "Actualización",
    "status_changed": "Cambio de estado",
    "roles_changed": "Cambio de responsables",
    "followup": "Seguimiento",
    "Incident declared.": "Accidente registrado.",
    "Incident closed.": "Accidente cerrado.",
    "Incident reopened.": "Accidente reabierto.",
    "Invalid credentials": "Correo o contraseña incorrectos",
    "Local login is disabled — sign in with SSO.": "El acceso con contraseña está desactivado. Utiliza SSO.",
    "Passwords must match and be at least 8 chars": "Las contraseñas deben coincidir y tener al menos 8 caracteres",
    "Note cannot be empty": "La nota no puede estar vacía",
    "Update message cannot be empty": "La actualización no puede estar vacía",
    "No closed status configured": "No hay un estado de cierre configurado",
    "Incident already closed": "El accidente ya está cerrado",
    "Unknown status": "Estado no válido",
    "This invitation link is invalid or has already been used.": "La invitación no es válida o ya ha sido utilizada.",
    "Passwords must match and be at least 8 characters.": "Las contraseñas deben coincidir y tener al menos 8 caracteres.",
    "Your account is ready — sign in.": "Tu cuenta está lista. Inicia sesión.",
}


def ui_es(value) -> str:
    if isinstance(value, str):
        for prefix, translated in {
            "Follow-up added: ": "Tarea añadida: ",
            "Follow-up completed: ": "Tarea completada: ",
            "Follow-up cancelled: ": "Tarea cancelada: ",
            "Follow-up reopened: ": "Tarea reabierta: ",
        }.items():
            if value.startswith(prefix):
                return translated + value.removeprefix(prefix)
        for label in ("Incident Lead", "Communications", "Scribe"):
            if value.startswith(label + ": "):
                return (
                    ui_es(label)
                    + ": "
                    + value.removeprefix(label + ": ").replace("unassigned", "sin asignar")
                )
    if isinstance(value, str) and value.startswith("Status changed from ") and " to " in value:
        old, new = value.removeprefix("Status changed from ").removesuffix(".").split(" to ", 1)
        return f"Estado cambiado de {ui_es(old)} a {ui_es(new)}."
    return _LABELS.get(value, value)
