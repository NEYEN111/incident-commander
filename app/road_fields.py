"""Minimal STATS19 accident data, shared by validation and the web forms.

Codes follow the classic STATS19 accident table. Missing data is stored as NULL;
explicit unknown categories retain their STATS19 codes. Speed limits use mph.
"""

from datetime import date as DateValue
from datetime import time as TimeValue
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

ROAD_FIELDS = {
    "date": {"label": "Fecha del accidente", "type": "date"},
    "time": {"label": "Hora del accidente", "type": "time"},
    "latitude": {"label": "Latitud", "type": "number", "min": -90, "max": 90},
    "longitude": {"label": "Longitud", "type": "number", "min": -180, "max": 180},
    "road_type": {
        "label": "Tipo de vía",
        "type": "select",
        "options": {
            1: "Rotonda",
            2: "Sentido único",
            3: "Calzadas separadas",
            6: "Calzada única",
            7: "Ramal de acceso/salida",
            9: "Desconocido",
        },
    },
    "speed_limit": {
        "label": "Límite de velocidad (mph)",
        "type": "number",
        "min": 1,
        "max": 200,
    },
    "urban_or_rural_area": {
        "label": "Zona del accidente",
        "type": "select",
        "options": {1: "Urbana", 2: "Rural", 3: "No determinada"},
    },
    "light_conditions": {
        "label": "Condiciones de iluminación",
        "type": "select",
        "options": {
            1: "Luz diurna",
            4: "Oscuridad con alumbrado encendido",
            5: "Oscuridad con alumbrado apagado",
            6: "Oscuridad sin alumbrado",
            7: "Oscuridad, iluminación desconocida",
        },
    },
    "weather_conditions": {
        "label": "Condiciones meteorológicas",
        "type": "select",
        "options": {
            1: "Despejado sin viento fuerte",
            2: "Lluvia sin viento fuerte",
            3: "Nieve sin viento fuerte",
            4: "Despejado con viento fuerte",
            5: "Lluvia con viento fuerte",
            6: "Nieve con viento fuerte",
            7: "Niebla/neblina",
            8: "Otro",
            9: "Desconocido",
        },
    },
    "road_surface_conditions": {
        "label": "Estado de la superficie",
        "type": "select",
        "options": {
            1: "Seca",
            2: "Mojada/húmeda",
            3: "Nieve",
            4: "Hielo/escarcha",
            5: "Inundación de más de 3 cm",
        },
    },
}


class RoadData(BaseModel):
    date: DateValue | None = None
    time: TimeValue | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    road_type: Literal[1, 2, 3, 6, 7, 9] | None = None
    speed_limit: int | None = Field(default=None, ge=1, le=200)
    urban_or_rural_area: Literal[1, 2, 3] | None = None
    light_conditions: Literal[1, 4, 5, 6, 7] | None = None
    weather_conditions: Literal[1, 2, 3, 4, 5, 6, 7, 8, 9] | None = None
    road_surface_conditions: Literal[1, 2, 3, 4, 5] | None = None


def validate_road_data(raw: dict) -> dict:
    values = {key: (None if value == "" else value) for key, value in raw.items()}
    # HTML select values arrive as strings; preserve categorical codes as integers.
    for key, spec in ROAD_FIELDS.items():
        if spec["type"] == "select" and isinstance(values.get(key), str):
            try:
                values[key] = int(values[key])
            except ValueError:
                pass  # Pydantic reports an invalid category below.
    try:
        return RoadData.model_validate(values).model_dump(exclude_unset=True)
    except ValidationError as exc:
        labels = list(dict.fromkeys(ROAD_FIELDS[e["loc"][0]]["label"] for e in exc.errors()))
        raise ValueError("Datos viales no válidos: " + ", ".join(labels)) from exc


async def road_form(request: Request) -> dict:
    form = await request.form()
    try:
        return validate_road_data({key: form[key] for key in ROAD_FIELDS if key in form})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def road_values(incident) -> dict:
    return {key: getattr(incident, key) for key in ROAD_FIELDS}


def road_display(key, value) -> str:
    if value is None:
        return "Sin datos"
    spec = ROAD_FIELDS[key]
    if spec["type"] == "select":
        return spec["options"].get(value, "Sin datos")
    if key == "date":
        return value.strftime("%d/%m/%Y")
    if key == "time":
        return value.strftime("%H:%M")
    if key == "speed_limit":
        return f"{value} mph"
    return str(value)
