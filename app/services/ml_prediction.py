"""Inference only: keep the complete, versioned Pipeline in memory per process."""

import json
import warnings
from functools import lru_cache
from pathlib import Path
from threading import Lock

import joblib
import pandas as pd
from sklearn.exceptions import InconsistentVersionWarning
from sklearn.pipeline import Pipeline

from app.schemas.prediction import PredictionRequest, PredictionResponse

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
_load_lock = Lock()


class MLPredictor:
    def __init__(self, models_dir: Path = MODELS_DIR):
        model_path = models_dir / "modelo_final.joblib"
        if not model_path.is_file():
            raise FileNotFoundError(f"No se encontró el modelo: {model_path}")
        with (models_dir / "modelo_info.json").open(encoding="utf-8") as file:
            metadata = json.load(file)
        with warnings.catch_warnings():
            warnings.simplefilter("error", InconsistentVersionWarning)
            self.pipeline = joblib.load(model_path)
        if not isinstance(self.pipeline, Pipeline):
            raise ValueError("El archivo debe contener el Pipeline completo")
        self.features = list(self.pipeline.feature_names_in_)
        expected = set(PredictionRequest.model_fields)
        if (
            len(self.features) != len(expected)
            or set(self.features) != expected
            or metadata["variables"] != list(PredictionRequest.model_fields)
        ):
            raise ValueError("Las variables del modelo y la metadata no coinciden con el contrato")
        self.classes = [str(label) for label in self.pipeline.classes_]
        if len(self.classes) != 3 or set(self.classes) != {"Fatal", "Grave", "Leve"}:
            raise ValueError("Clases del modelo no compatibles")
        if set(metadata["clases"]) != set(self.classes):
            raise ValueError("Las clases de la metadata no coinciden con el modelo")
        self.version = str(metadata["version"])

    def predict(self, inputs: PredictionRequest) -> PredictionResponse:
        # The saved ColumnTransformer selects named columns; preserve its original order.
        frame = pd.DataFrame([inputs.model_dump()], columns=self.features)
        prediction = str(self.pipeline.predict(frame)[0])
        probabilities = self.pipeline.predict_proba(frame)[0]
        return PredictionResponse(
            prediction=prediction,
            probabilities=dict(zip(self.classes, map(float, probabilities), strict=True)),
            model_version=self.version,
        )


@lru_cache(maxsize=1)
def _load_predictor() -> MLPredictor:
    return MLPredictor()


def get_predictor() -> MLPredictor:
    # Lock around the cache lookup as well, so concurrent first requests load only once.
    with _load_lock:
        return _load_predictor()
