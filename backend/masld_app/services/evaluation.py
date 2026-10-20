"""Reproducible holdout evaluation and compact diagnostic report generation."""

from __future__ import annotations

import math
from pathlib import Path
from time import perf_counter_ns
from typing import Any

from .data_generation import FEATURES, TARGETS


def predict(features: list[float], coefficients: list[float]) -> float:
    return sum(x * w for x, w in zip(features, coefficients))


def evaluate(
    weights: dict[str, list[float]], holdout: list[tuple[list[float], list[float]]]
) -> dict[str, Any]:
    errors_by_target: dict[str, list[float]] = {}
    metrics: dict[str, Any] = {"holdout_rows": len(holdout), "targets": {}}
    started = perf_counter_ns()
    for index, target in enumerate(TARGETS):
        observed = [y[index] for _, y in holdout]
        predictions = [predict(x, weights[target]) for x, _ in holdout]
        errors = [
            prediction - actual for prediction, actual in zip(predictions, observed)
        ]
        errors_by_target[target] = errors
        rmse = math.sqrt(sum(error * error for error in errors) / max(1, len(errors)))
        mae = sum(abs(error) for error in errors) / max(1, len(errors))
        mean = sum(observed) / max(1, len(observed))
        total_sum_squares = sum((actual - mean) ** 2 for actual in observed)
        residual_sum_squares = sum(error * error for error in errors)
        r_squared = (
            1 - residual_sum_squares / total_sum_squares if total_sum_squares else 0.0
        )
        metrics["targets"][target] = {
            "rmse": rmse,
            "mae": mae,
            "r_squared": r_squared,
            "residual_mean": sum(errors) / max(1, len(errors)),
        }
        metrics[f"{target}_holdout_rmse"] = (
            rmse  # compatibility for existing artifact readers
        )
    elapsed_ms = (perf_counter_ns() - started) / 1_000_000
    metrics["inference_latency_ms_per_1000_rows"] = (
        elapsed_ms * 1000 / max(1, len(holdout))
    )
    return metrics


def feature_sensitivity(
    weights: dict[str, list[float]], rows: list[tuple[list[float], list[float]]]
) -> dict[str, Any]:
    """Mean absolute prediction change for a 10% range shift in one feature."""
    if not rows:
        return {}
    result = {}
    for feature_index, feature in enumerate(FEATURES):
        values = [row[0][feature_index] for row in rows]
        span = max(values) - min(values)
        shift = span * 0.1
        if feature == "intercept":
            continue
        output = {}
        for target in TARGETS:
            output[target] = sum(
                abs(weights[target][feature_index] * shift) for _ in rows
            ) / len(rows)
        result[feature] = {"input_shift": shift, "mean_absolute_output_change": output}
    return result


def write_residual_svg(
    weights: dict[str, list[float]],
    holdout: list[tuple[list[float], list[float]]],
    path: Path,
) -> None:
    width, height = 760, 300
    panels = []
    for panel, target in enumerate(TARGETS):
        left = 45 + panel * 180
        errors = [
            predict(x, weights[target]) - y[i]
            for x, y in holdout[:250]
            for i, name in enumerate(TARGETS)
            if name == target
        ]
        extent = max(max((abs(v) for v in errors), default=1e-6), 1e-6)
        points = []
        for i, error in enumerate(errors):
            cx = left + 12 + (i % 32) * 4.3
            cy = (
                78 + panel * 0
            )  # shared diagnostic band; target label distinguishes groups
            y = cy - 30 * error / extent
            points.append(
                f'<circle cx="{cx:.1f}" cy="{y:.1f}" r="1.6" fill="#58856d" opacity=".45"/>'
            )
        panels.append(
            f'<text x="{left}" y="35" font-size="12">{target} residual</text>'
            + "".join(points)
        )
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#fbfcf9"/><text x="20" y="20" font-size="12">Holdout residuals · synthetic equation units</text><line x1="35" y1="78" x2="740" y2="78" stroke="#cbd5ce"/>{"".join(panels)}<text x="20" y="150" font-size="11" fill="#555">Points show prediction error around zero; no clinical accuracy is implied.</text></svg>'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")
