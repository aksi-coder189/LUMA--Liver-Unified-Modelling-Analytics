"""Train synthetic derivative regressors and write reproducible diagnostics."""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

from ..config import ensure_supported_runtime
from ..domain.simulation import DEFAULT_PARAMETERS, oxygen_pde, simulate
from .data_generation import FEATURES, TARGETS, build_dataset
from .evaluation import evaluate, feature_sensitivity, write_residual_svg

ROOT = Path(__file__).resolve().parents[3]
MODEL_PATH = ROOT / "model" / "synthetic_ode_model.json"


def solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting for small normal equations."""
    a = [row[:] + [value] for row, value in zip(matrix, vector)]
    n = len(vector)
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(a[row][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise ValueError(
                "Synthetic design matrix is singular; cannot fit coefficients."
            )
        a[col], a[pivot] = a[pivot], a[col]
        divisor = a[col][col]
        a[col] = [value / divisor for value in a[col]]
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            a[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(a[row], a[col])
            ]
    return [a[i][-1] for i in range(n)]


def fit_regressor(
    dataset: list[tuple[list[float], list[float]]], ridge_alpha: float = 0.0
) -> dict[str, list[float]]:
    if not dataset:
        raise ValueError("At least one training sample is required.")
    if (
        isinstance(ridge_alpha, bool)
        or not isinstance(ridge_alpha, (int, float))
        or not math.isfinite(ridge_alpha)
        or ridge_alpha < 0
    ):
        raise ValueError("ridge_alpha must be finite and non-negative.")
    for features, targets in dataset:
        if (
            len(features) != len(FEATURES)
            or len(targets) != len(TARGETS)
            or any(not math.isfinite(value) for value in (*features, *targets))
        ):
            raise ValueError(
                "Training rows must contain finite values with the documented feature and target widths."
            )
    n = len(FEATURES)
    scales = [1.0] + [
        max(math.sqrt(sum(x[i] * x[i] for x, _ in dataset) / len(dataset)), 1e-12)
        for i in range(1, n)
    ]
    scaled = (
        [([value / scales[i] for i, value in enumerate(x)], y) for x, y in dataset]
        if ridge_alpha
        else dataset
    )
    gram = [[sum(x[i] * x[j] for x, _ in scaled) for j in range(n)] for i in range(n)]
    for i in range(1, n):
        gram[i][i] += ridge_alpha
    weights = {}
    for target_index, name in enumerate(TARGETS):
        rhs = [sum(x[i] * y[target_index] for x, y in scaled) for i in range(n)]
        coefficients = solve(gram, rhs)
        weights[name] = (
            [value / scales[i] for i, value in enumerate(coefficients)]
            if ridge_alpha
            else coefficients
        )
    return weights


def fit(
    dataset: list[tuple[list[float], list[float]]],
) -> tuple[dict[str, list[float]], dict[str, float]]:
    """Compatibility helper preserving the original 80/20 OLS result shape."""
    split = int(len(dataset) * 0.8)
    weights = fit_regressor(dataset[:split])
    details = evaluate(weights, dataset[split:])
    metrics = {
        f"{target}_holdout_rmse": details[f"{target}_holdout_rmse"]
        for target in TARGETS
    }
    metrics["holdout_rows"] = float(details["holdout_rows"])
    return weights, metrics


def train(rows: int = 8000, seed: int = 20261019) -> dict[str, Any]:
    data = build_dataset(rows, seed)
    split = int(len(data) * 0.8)
    train_rows, holdout = data[:split], data[split:]
    ols = fit_regressor(train_rows)
    # Fixed before looking at holdout: ridge alpha 0.01 is a comparator only.
    ridge = fit_regressor(train_rows, ridge_alpha=0.01)
    ols_metrics, ridge_metrics = evaluate(ols, holdout), evaluate(ridge, holdout)
    return {
        "weights": ols,
        "metrics": ols_metrics,
        "comparison": {
            "ols": ols_metrics,
            "ridge_alpha_0_01": ridge_metrics,
            "selected_for_inference": "OLS (prespecified equation-recovery baseline; comparator is not selected on holdout)",
        },
        "sensitivity": feature_sensitivity(ols, holdout),
        "feature_ranges": {
            name: {
                "minimum": min(row[0][index] for row in train_rows),
                "maximum": max(row[0][index] for row in train_rows),
            }
            for index, name in enumerate(FEATURES)
        },
        "dataset": data,
        "holdout": holdout,
        "train_rows": len(train_rows),
        "seed": seed,
    }


def numerical_stability(weights: dict[str, list[float]]) -> dict[str, Any]:
    model = {
        "model_name": "synthetic_ode_derivative_surrogate",
        "model_version": 2,
        "weights": weights,
    }
    ode = []
    for steps in (300, 600, 1200):
        result = simulate(duration=30, steps=steps, model=model)
        end = {
            name: sum(zone["state"][name] for zone in result["zonal_states"])
            / len(result["zonal_states"])
            for name in ("ffa", "triglyceride", "ros", "ecm")
        }
        ode.append({"steps": steps, "final_state": end})
    fine = ode[-1]["final_state"]
    for item in ode:
        item["max_abs_difference_from_1200"] = max(
            abs(item["final_state"][name] - fine[name]) for name in fine
        )
    profiles = {cells: oxygen_pde(cells=cells) for cells in (21, 41, 81)}
    fine_profile = profiles[81]
    pde = []
    for cells, profile in profiles.items():
        at_common_positions = [profile[round(i * (cells - 1) / 4)] for i in range(5)]
        fine_at_common_positions = [fine_profile[round(i * 80 / 4)] for i in range(5)]
        pde.append(
            {
                "cells": cells,
                "max_abs_difference_from_81_cells": max(
                    abs(a - b)
                    for a, b in zip(at_common_positions, fine_at_common_positions)
                ),
                "nonnegative_finite": all(
                    math.isfinite(value) and value >= 0 for value in profile
                ),
            }
        )
    initial = []
    for scale in (0.5, 1.0, 1.5):
        result = simulate(
            duration=30,
            steps=600,
            model=model,
            initial_state={
                "ffa": 0.4 * scale,
                "triglyceride": 0.2 * scale,
                "ros": 0.1 * scale,
                "ecm": 0.05 * scale,
            },
        )
        initial.append(
            {
                "initial_state_scale": scale,
                "final_state": {
                    name: sum(z["state"][name] for z in result["zonal_states"])
                    / len(result["zonal_states"])
                    for name in fine
                },
            }
        )
    return {
        "ode_timestep_refinement": ode,
        "pde_grid_refinement": pde,
        "initial_condition_sweep": initial,
        "scope": "Numerical behavior for this synthetic coefficient set; not empirical or biological validity.",
    }


def assumption_uncertainty_propagation(
    weights: dict[str, list[float]], samples: int = 100, seed: int = 20261020
) -> dict[str, Any]:
    """Propagate explicitly assumed input ranges through the synthetic ODE."""
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 20:
        raise ValueError("samples must be an integer of at least 20.")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer.")
    rng = random.Random(seed)
    model = {
        "model_name": "synthetic_ode_derivative_surrogate",
        "model_version": 2,
        "weights": weights,
    }
    state_names = ("ffa", "triglyceride", "ros", "ecm")
    initial = {"ffa": 0.4, "triglyceride": 0.2, "ros": 0.1, "ecm": 0.05}
    values = {name: [] for name in state_names}
    for _ in range(samples):
        parameters = {
            name: value * rng.uniform(0.9, 1.1)
            for name, value in DEFAULT_PARAMETERS.items()
        }
        initial_state = {
            name: value * rng.uniform(0.95, 1.05) for name, value in initial.items()
        }
        result = simulate(
            duration=30,
            steps=300,
            model=model,
            parameters=parameters,
            initial_state=initial_state,
        )
        for name in state_names:
            values[name].append(
                sum(zone["state"][name] for zone in result["zonal_states"])
                / len(result["zonal_states"])
            )

    def quantile(observations: list[float], probability: float) -> float:
        ordered = sorted(observations)
        position = (len(ordered) - 1) * probability
        low = math.floor(position)
        high = math.ceil(position)
        return ordered[low] + (ordered[high] - ordered[low]) * (position - low)

    return {
        "method": "Deterministic-seed Monte Carlo propagation of uniform ±10% default-rate and ±5% initial-state ranges through the toy ODE.",
        "samples": samples,
        "seed": seed,
        "final_mean_state_quantiles": {
            name: {
                "p05": quantile(observations, 0.05),
                "median": quantile(observations, 0.5),
                "p95": quantile(observations, 0.95),
            }
            for name, observations in values.items()
        },
        "interpretation": "Sensitivity to invented input ranges only; not fitted parameter uncertainty, a confidence/prediction interval, patient uncertainty, or clinical risk.",
    }


def write_report(result: dict[str, Any], rows: int) -> None:
    report_dir = ROOT / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    write_residual_svg(
        result["weights"], result["holdout"], report_dir / "synthetic_residuals.svg"
    )
    stability = numerical_stability(result["weights"])
    uncertainty = assumption_uncertainty_propagation(result["weights"])
    lines = [
        "# Synthetic equation recovery experiment",
        "",
        "This report measures recovery of the program's own generated equations. It is not biological or clinical validation.",
        "",
        f"- Rows: {rows} ({result['train_rows']} train / {len(result['holdout'])} holdout)",
        f"- Seed: {result['seed']}",
        "- Split: deterministic shuffled 80/20",
        "- Inference estimator: ordinary least squares (prespecified)",
        "- Comparator: ridge regression, alpha=0.01 (fixed before holdout evaluation)",
        "",
        "## Holdout metrics",
        "",
        "| Target | OLS RMSE | OLS MAE | OLS R² | Ridge RMSE | Ridge MAE | Ridge R² |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for target in TARGETS:
        ols = result["comparison"]["ols"]["targets"][target]
        ridge = result["comparison"]["ridge_alpha_0_01"]["targets"][target]
        lines.append(
            f"| {target} | {ols['rmse']:.8g} | {ols['mae']:.8g} | {ols['r_squared']:.8g} | {ridge['rmse']:.8g} | {ridge['mae']:.8g} | {ridge['r_squared']:.8g} |"
        )
    lines += [
        "",
        "Inference latency is a local wall-clock measurement on the holdout batch, reported per 1,000 rows; it is a rough benchmark, not a deployment SLA.",
        "",
        f"- OLS: {result['comparison']['ols']['inference_latency_ms_per_1000_rows']:.4f} ms / 1,000 rows",
        f"- Ridge: {result['comparison']['ridge_alpha_0_01']['inference_latency_ms_per_1000_rows']:.4f} ms / 1,000 rows",
        "",
        "The generated held-out targets are the reference simulator outputs for this equation-recovery experiment; they are not external or biological ground truth.",
        "",
        "## Sensitivity",
        "",
        "For each input, the table reports the predicted absolute output shift for a 10% holdout input range shift. This is model sensitivity, not biological importance.",
        "",
        "| Feature | Input shift | Mean absolute output change (dFFA / dTG / dROS / dECM) |",
        "|---|---:|---|",
    ]
    for feature, item in result["sensitivity"].items():
        changes = item["mean_absolute_output_change"]
        lines.append(
            f"| {feature} | {item['input_shift']:.6g} | "
            + " / ".join(f"{changes[t]:.6g}" for t in TARGETS)
            + " |"
        )
    lines += [
        "",
        "## Numerical convergence and stability",
        "",
        "ODE uses forward Euler and is compared at increasing step counts over the same arbitrary duration. PDE time step is automatically bounded from the explicit diffusion/advection stability limit; grid profiles are compared at common spatial locations.",
        "",
        "### ODE step refinement",
        "",
        "| Steps | Maximum final-state difference from 1,200 steps |",
        "|---:|---:|",
    ]
    for item in stability["ode_timestep_refinement"]:
        lines.append(
            f"| {item['steps']} | {item['max_abs_difference_from_1200']:.8g} |"
        )
    lines += [
        "",
        "### Oxygen PDE grid refinement",
        "",
        "| Cells | Max profile difference from 81-cell grid | Non-negative and finite |",
        "|---:|---:|---|",
    ]
    for item in stability["pde_grid_refinement"]:
        lines.append(
            f"| {item['cells']} | {item['max_abs_difference_from_81_cells']:.8g} | {item['nonnegative_finite']} |"
        )
    lines += [
        "",
        "### Initial condition sweep",
        "",
        "| Initial state scale | Final mean FFA | TG | ROS | ECM |",
        "|---:|---:|---:|---:|---:|",
    ]
    for item in stability["initial_condition_sweep"]:
        state = item["final_state"]
        lines.append(
            f"| {item['initial_state_scale']:.1f} | "
            + " | ".join(
                f"{state[name]:.6g}" for name in ("ffa", "triglyceride", "ros", "ecm")
            )
            + " |"
        )
    lines += [
        "",
        "## Assumption-range uncertainty propagation",
        "",
        uncertainty["method"],
        "",
        uncertainty["interpretation"],
        "",
        "| Final mean state | 5th percentile | Median | 95th percentile |",
        "|---|---:|---:|---:|",
    ]
    for name, interval in uncertainty["final_mean_state_quantiles"].items():
        lines.append(
            f"| {name} | {interval['p05']:.6g} | {interval['median']:.6g} | {interval['p95']:.6g} |"
        )
    lines += [
        "",
        "## Limitations",
        "",
        "- The generated targets use the same illustrative equations that the model fits.",
        "- Numeric coefficients are toy values; literature only motivates qualitative mechanisms.",
        "- No patient data, treatment effects, diagnosis, prognosis, or clinical accuracy are represented.",
        "- Residual visualization: `reports/synthetic_residuals.svg`.",
        "",
    ]
    (report_dir / "experiment_report.md").write_text("\n".join(lines), encoding="utf-8")


def artifact_from_result(result: dict[str, Any], rows: int) -> dict[str, Any]:
    """Build the model payload without writing files (also used by server fallback)."""
    return {
        "model_name": "synthetic_ode_derivative_surrogate",
        "model_version": 2,
        "training_data": f"{rows:,} generated synthetic equation samples; no patient or external data",
        "seed": result["seed"],
        "feature_names": FEATURES,
        "feature_ranges": result["feature_ranges"],
        "target_names": TARGETS,
        "weights": result["weights"],
        "metrics": result["metrics"],
        "comparison": result["comparison"],
        "sensitivity": result["sensitivity"],
        "warning": "Synthetic-only equation fitting. Not a clinical model, prediction, or learned treatment effect.",
    }


def write_outputs(result: dict[str, Any], rows: int) -> dict[str, Any]:
    artifact = artifact_from_result(result, rows)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    write_report(result, rows)
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=8000)
    parser.add_argument("--seed", type=int, default=20261019)
    args = parser.parse_args(argv)
    try:
        ensure_supported_runtime()
        result = train(args.rows, args.seed)
    except (RuntimeError, ValueError, ArithmeticError) as exc:
        print(f"Training error: {exc}", file=sys.stderr)
        return 2
    write_outputs(result, args.rows)
    print(
        json.dumps(
            {
                "artifact": str(MODEL_PATH),
                "report": str(ROOT / "reports" / "experiment_report.md"),
                "training_rows": result["train_rows"],
                "holdout_rows": len(result["holdout"]),
                "metrics": result["metrics"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
