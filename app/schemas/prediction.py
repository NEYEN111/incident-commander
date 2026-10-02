"""Inputs use the STATS19 codes supported by the saved 2025 Pipeline."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    day_of_week: int = Field(ge=1, le=7, description="STATS19: 1=domingo, 7=sábado")
    hour: int = Field(ge=0, le=23)
    road_type: Literal[1, 2, 3, 6, 7, 9]
    speed_limit: Literal[20, 30, 40, 50, 60, 70] = Field(
        description="Límite de velocidad en mph observado durante el entrenamiento"
    )
    urban_or_rural_area: Literal[1, 2, 3]
    light_conditions: Literal[-1, 1, 4, 5, 6, 7]
    weather_conditions: Literal[1, 2, 3, 4, 5, 6, 7, 8, 9]
    road_surface_conditions: Literal[-1, 1, 2, 3, 4, 5, 9]
    number_of_vehicles: int = Field(ge=1, le=17)
    junction_detail: Literal[-1, 0, 13, 16, 17, 18, 19, 99]
    first_road_class: Literal[-1, 1, 2, 3, 4, 5, 6]

    @field_validator("*", mode="before")
    @classmethod
    def require_integer(cls, value):
        # Literal[int] otherwise also accepts booleans and integral floats.
        if type(value) is not int:
            raise ValueError("Debe ser un entero JSON; no se aceptan booleanos ni cadenas")
        return value


class PredictionProbabilities(BaseModel):
    Fatal: float = Field(ge=0, le=1)
    Grave: float = Field(ge=0, le=1)
    Leve: float = Field(ge=0, le=1)


class PredictionResponse(BaseModel):
    prediction: Literal["Fatal", "Grave", "Leve"]
    probabilities: PredictionProbabilities
    model_version: str
