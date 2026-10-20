"""Versioned API routes and legacy aliases."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ..domain.schema import validate
from ..services.artifacts import initialize_runtime_model
from ..services.model_service import run
from ..services.two_stream_demo import build_demo
from .errors import APIError

Route = Callable[[bytes], tuple[int, dict[str, Any]]]


def health(_: bytes) -> tuple[int, dict[str, Any]]:
    try:
        artifact, source = initialize_runtime_model()
    except (OSError, ValueError, json.JSONDecodeError):
        return 503, {
            "ok": False,
            "error": {
                "code": "MODEL_UNAVAILABLE",
                "message": "Train or repair the local synthetic model artifact.",
            },
        }
    return 200, {
        "ok": True,
        "model_name": artifact["model_name"],
        "model_version": artifact["model_version"],
        "training_data": artifact["training_data"],
        "model_source": source,
        "warning": artifact["warning"],
    }


def demo(_: bytes) -> tuple[int, dict[str, Any]]:
    try:
        return 200, build_demo()
    except (FileNotFoundError, OSError, KeyError, ArithmeticError, ValueError) as exc:
        raise APIError(
            500, "DEMO_ERROR", "The reproducible synthetic demo could not be built."
        ) from exc


def model(body: bytes) -> tuple[int, dict[str, Any]]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise APIError(
            400, "INVALID_JSON", "Request body must be a valid UTF-8 JSON object."
        ) from exc
    try:
        clean = validate(payload)
    except ValueError as exc:
        raise APIError(400, "INVALID_INPUT", str(exc)) from exc
    try:
        return 200, run(clean)
    except FileNotFoundError as exc:
        raise APIError(
            503,
            "MODEL_UNAVAILABLE",
            "Train the local synthetic model artifact before running inference.",
        ) from exc
    except (OSError, KeyError, ArithmeticError, ValueError) as exc:
        raise APIError(
            500, "MODEL_ERROR", "The local model could not complete this request."
        ) from exc


GET_ROUTES: dict[str, Route] = {
    "/api/v1/health": health,
    "/api/health": health,
    "/api/v1/demo": demo,
}
POST_ROUTES: dict[str, Route] = {"/api/v1/model": model, "/api/model": model}
