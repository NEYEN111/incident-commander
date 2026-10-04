import hashlib
import json
from pathlib import Path


def test_documented_metrics_match_saved_notebook_and_artifact():
    root = Path(__file__).resolve().parents[1]
    evaluation = json.loads((root / "models/modelo_evaluacion.json").read_text(encoding="utf-8"))
    source = root / evaluation["source"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == evaluation["source_sha256"]
    assert (
        hashlib.sha256((root / "models/modelo_final.joblib").read_bytes()).hexdigest()
        == evaluation["model_sha256"]
    )
    notebook = json.loads(source.read_text(encoding="utf-8"))
    outputs = "".join(
        "".join(o.get("text", [])) for o in notebook["cells"][evaluation["source_cell"]]["outputs"]
    )
    for key, label in [
        ("accuracy", "Accuracy"),
        ("f1_macro", "F1 Macro"),
        ("balanced_accuracy", "Balanced Accuracy"),
        ("roc_auc_macro_ovr", "ROC-AUC Macro OVR"),
    ]:
        assert f"{label}: {evaluation['metrics'][key]}" in outputs
    for row in evaluation["class_report_rounded"]:
        assert f"{row['support']}" in outputs
