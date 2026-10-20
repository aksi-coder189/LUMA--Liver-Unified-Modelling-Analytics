"""Loading and validating the generated model artifact."""

from __future__ import annotations

import json
import math
import threading
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODEL_PATH = PROJECT_ROOT / "model" / "synthetic_ode_model.json"
FEATURE_NAMES = [
    "intercept",
    "uptake",
    "dnl",
    "ffa",
    "tg",
    "beta_oxidation",
    "ros",
    "ecm",
    "hsc_signal",
    "mmp_signal",
]
_runtime_artifact: dict[str, Any] | None = None
_runtime_source = "checked-in artifact"
_runtime_lock = threading.Lock()


def load_trained_model() -> dict[str, Any]:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            "Trained synthetic artifact not found. Run: python src/train_synthetic.py"
        )
    artifact = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    if not isinstance(artifact, dict):
        raise TypeError("Model artifact must contain a JSON object.")
    if artifact.get("feature_names") != FEATURE_NAMES:
        raise ValueError(
            "Model artifact feature schema does not match this application."
        )
    if not isinstance(artifact.get("model_name"), str) or (
        isinstance(artifact.get("model_version"), bool)
        or not isinstance(artifact.get("model_version"), int)
    ):
        raise TypeError("Model artifact metadata is incomplete.")
    if not isinstance(artifact.get("training_data"), str) or not isinstance(
        artifact.get("warning"), str
    ):
        raise TypeError("Model artifact provenance is incomplete.")
    weights = artifact.get("weights")
    targets = ("d_ffa", "d_tg", "d_ros", "d_ecm")
    if not isinstance(weights, dict) or any(
        not isinstance(weights.get(target), list)
        or len(weights[target]) != len(FEATURE_NAMES)
        for target in targets
    ):
        raise ValueError("Model artifact coefficient schema is invalid.")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for target in targets
        for value in weights[target]
    ):
        raise ValueError("Model artifact coefficients must be finite numbers.")
    return artifact


def initialize_runtime_model() -> tuple[dict[str, Any], str]:
    """Use the checked-in artifact, or train a clearly labelled memory-only fallback.

    The fallback helps the local demo remain inspectable if a release extraction is
    missing its model JSON. It never writes files and remains synthetic-only.
    """
    global _runtime_artifact, _runtime_source
    with _runtime_lock:
        if _runtime_artifact is not None:
            return _runtime_artifact, _runtime_source
        try:
            _runtime_artifact = load_trained_model()
            _runtime_source = "checked-in artifact"
        except (OSError, ValueError, json.JSONDecodeError):
            from .training import artifact_from_result, train

            result = train(rows=8000, seed=20261019)
            _runtime_artifact = artifact_from_result(result, rows=8000)
            _runtime_artifact["model_name"] = (
                "synthetic_ode_derivative_surrogate_memory_fallback"
            )
            _runtime_artifact["training_data"] += (
                "; generated in memory because the packaged artifact was missing or invalid"
            )
            _runtime_artifact["warning"] += (
                " Runtime fallback is ephemeral and must not be interpreted as clinical inference."
            )
            _runtime_source = "in-memory synthetic fallback"
        return _runtime_artifact, _runtime_source


def load_runtime_model() -> dict[str, Any]:
    """Return the initialized model artifact used by inference services."""
    return initialize_runtime_model()[0]
