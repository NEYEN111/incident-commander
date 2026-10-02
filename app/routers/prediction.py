import logging

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_user
from app.schemas.prediction import PredictionRequest, PredictionResponse
from app.services.ml_prediction import get_predictor

router = APIRouter(prefix="/api", tags=["Predicciones"], dependencies=[Depends(require_user)])
log = logging.getLogger(__name__)


@router.post(
    "/predict",
    response_model=PredictionResponse,
    responses={503: {"description": "Modelo ML ausente o incompatible"}},
)
def predict(inputs: PredictionRequest) -> PredictionResponse:
    try:
        predictor = get_predictor()
    except Exception as exc:
        log.exception("No se pudo cargar el modelo ML")
        raise HTTPException(status_code=503, detail="Modelo ML no disponible") from exc
    return predictor.predict(inputs)
