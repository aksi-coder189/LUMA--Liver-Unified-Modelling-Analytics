"""Deterministic synthetic two-stream fusion and forecast demonstration."""

from __future__ import annotations

import random
from typing import Any

from ..domain.simulation import DEFAULT_PARAMETERS, simulate
from .artifacts import load_runtime_model


def _solve_linear(matrix: list[list[float]], target: list[float]) -> list[float]:
    """Solve a small full-rank normal-equation system with pivoted elimination."""
    augmented = [row[:] + [value] for row, value in zip(matrix, target, strict=True)]
    size = len(target)
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("Synthetic forecast training matrix is singular.")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                left - factor * right
                for left, right in zip(augmented[row], augmented[column], strict=True)
            ]
    return [augmented[row][-1] for row in range(size)]


def _forecast_features(row: dict[str, float]) -> list[float]:
    return [
        1.0,
        row["starting_tg_proxy"],
        (7000.0 - row["mean_steps"]) / 1000.0,
        7.0 - row["mean_sleep_hours"],
        (row["mean_resting_hr"] - 65.0) / 10.0,
    ]


def _synthetic_ground_truth(row: dict[str, float], noise: float) -> float:
    """Independent scenario generator for a synthetic 30-day TG proxy target."""
    f = _forecast_features(row)
    return max(0.0, f[1] + 0.018 * f[2] + 0.012 * f[3] + 0.009 * f[4] + noise)


def _evaluate_forecast(seed: int = 20301020) -> tuple[dict[str, Any], list[float]]:
    rng = random.Random(seed)
    records: list[tuple[list[float], float, float]] = []
    for index in range(500):
        row = {
            "starting_tg_proxy": rng.uniform(0.12, 0.75),
            "mean_steps": rng.uniform(1800, 12500),
            "mean_sleep_hours": rng.uniform(4.5, 9.0),
            "mean_resting_hr": rng.uniform(48, 100),
        }
        truth = _synthetic_ground_truth(row, rng.gauss(0, 0.012))
        records.append((_forecast_features(row), truth, row["starting_tg_proxy"]))
    split = 400
    train, holdout = records[:split], records[split:]
    width = len(train[0][0])
    gram = [
        [sum(row[0][i] * row[0][j] for row in train) for j in range(width)]
        for i in range(width)
    ]
    rhs = [sum(row[0][i] * row[1] for row in train) for i in range(width)]
    coefficients = _solve_linear(gram, rhs)
    predictions = [
        sum(a * b for a, b in zip(coefficients, row[0], strict=True)) for row in holdout
    ]
    actuals = [row[1] for row in holdout]
    baseline = [row[2] for row in holdout]

    def metrics(predicted: list[float]) -> dict[str, float]:
        errors = [
            prediction - actual
            for prediction, actual in zip(predicted, actuals, strict=True)
        ]
        return {
            "mae": round(sum(abs(error) for error in errors) / len(errors), 6),
            "rmse": round(
                (sum(error * error for error in errors) / len(errors)) ** 0.5, 6
            ),
        }

    return (
        {
            "target": "synthetic dimensionless TG proxy at 30 days",
            "horizon_days": 30,
            "training_records": len(train),
            "heldout_records": len(holdout),
            "seed": seed,
            "split": "first 400 generated records train; separately held-out final 100 evaluated once",
            "ground_truth": "Independent deterministic synthetic target equation plus seeded Gaussian noise; not the ODE output and not patient observations.",
            "ground_truth_equation": "max(0, starting_TG + 0.018*((7000-mean_steps)/1000) + 0.012*(7-mean_sleep_hours) + 0.009*((mean_resting_hr-65)/10) + seeded_noise_sd_0.012)",
            "forecast_model": {
                "type": "ordinary least-squares linear regression",
                "features": [
                    "starting synthetic TG proxy",
                    "mean activity steps/day",
                    "mean sleep hours/night",
                    "mean resting heart rate",
                ],
            },
            "heldout_metrics": {
                "model": metrics(predictions),
                "persistence_baseline": metrics(baseline),
            },
            "limitation": "This benchmark measures recovery of an independently generated synthetic target only. It is not clinical forecast performance or validation.",
        },
        coefficients,
    )


def build_demo() -> dict[str, Any]:
    """Build the same fully synthetic, reproducible lab + wearable story per call."""
    patient = {
        "record_id": "LUMA-SYN-001",
        "synthetic": True,
        "demographics": {
            "age_years": 52,
            "height_m": 1.70,
            "weight_kg": 84.0,
            "bmi_kg_m2": 29.1,
        },
        "historical_laboratory_values": [
            {
                "date": "2026-07-20",
                "alt_u_l": 36,
                "ast_u_l": 31,
                "cap_db_m": 260,
                "lsm_kpa": 5.9,
                "fasting_glucose_mmol_l": 5.4,
            },
            {
                "date": "2026-08-20",
                "alt_u_l": 41,
                "ast_u_l": 34,
                "cap_db_m": 276,
                "lsm_kpa": 6.1,
                "fasting_glucose_mmol_l": 5.6,
            },
            {
                "date": "2026-09-20",
                "alt_u_l": 46,
                "ast_u_l": 37,
                "cap_db_m": 294,
                "lsm_kpa": 6.4,
                "fasting_glucose_mmol_l": 5.8,
            },
        ],
    }
    sensors = [
        {"day": index + 1, "steps": steps, "sleep_hours": sleep, "resting_hr_bpm": hr}
        for index, (steps, sleep, hr) in enumerate(
            [
                (4100, 6.1, 78),
                (5200, 6.4, 76),
                (3600, 5.8, 81),
                (6100, 6.7, 75),
                (4700, 6.0, 79),
                (5500, 6.5, 77),
                (3900, 5.9, 80),
            ]
        )
    ]
    latest = patient["historical_laboratory_values"][-1]
    mean_steps = sum(item["steps"] for item in sensors) / len(sensors)
    mean_sleep = sum(item["sleep_hours"] for item in sensors) / len(sensors)
    mean_hr = sum(item["resting_hr_bpm"] for item in sensors) / len(sensors)
    bmi = (
        patient["demographics"]["weight_kg"] / patient["demographics"]["height_m"] ** 2
    )
    lab_initial = {
        "ffa": 0.30 + max(0, latest["fasting_glucose_mmol_l"] - 4.0) * 0.025,
        "triglyceride": 0.12
        + (latest["cap_db_m"] - 100) / 1000
        + max(0, bmi - 25) * 0.003,
        "ros": 0.05 + latest["alt_u_l"] * 0.0015,
        "ecm": 0.025 + latest["lsm_kpa"] * 0.012,
    }
    parameters = {
        "uptake": DEFAULT_PARAMETERS["uptake"]
        * max(0.8, min(1.2, 1 + (7000 - mean_steps) / 70000)),
        "dnl": DEFAULT_PARAMETERS["dnl"]
        * max(0.85, min(1.15, 1 + (7 - mean_sleep) * 0.03)),
        "beta_oxidation": DEFAULT_PARAMETERS["beta_oxidation"]
        * max(0.8, min(1.2, 1 + (mean_steps - 7000) / 70000)),
    }
    sensor_mapping = {
        "mean_steps_per_day": round(mean_steps, 1),
        "mean_sleep_hours_per_night": round(mean_sleep, 2),
        "mean_resting_hr_bpm": round(mean_hr, 1),
        "mapped_model_parameters": parameters,
        "mapping_note": "Only illustrative software couplings: activity scales uptake and beta-oxidation coefficients; sleep scales DNL. These coefficients are arbitrary assumptions, not validated biological effects.",
    }
    model = load_runtime_model()
    lab_only = simulate(
        {}, model=model, initial_state=lab_initial, parameters=DEFAULT_PARAMETERS
    )
    fused = simulate({}, model=model, initial_state=lab_initial, parameters=parameters)
    forecast_report, coefficients = _evaluate_forecast()
    forecast_row = {
        "starting_tg_proxy": lab_initial["triglyceride"],
        "mean_steps": mean_steps,
        "mean_sleep_hours": mean_sleep,
        "mean_resting_hr": mean_hr,
    }
    forecast = max(
        0.0,
        sum(
            a * b
            for a, b in zip(coefficients, _forecast_features(forecast_row), strict=True)
        ),
    )
    return {
        "scenario_id": "luma-two-stream-demo-v1",
        "notice": "SYNTHETIC DEMONSTRATION · NOT FOR CLINICAL USE · DO NOT ENTER REAL PATIENT DATA",
        "patient_record": patient,
        "sensor_stream": {
            "source": "synthetic wearable-like daily observations",
            "observations": sensors,
            "summary": sensor_mapping,
        },
        "twin_update": {
            "mapping_version": "synthetic-demo-mapping-1",
            "initial_state_mapping": "Latest synthetic CAP, ALT, LSM, fasting glucose and calculated BMI are mapped by fixed arbitrary formulas into dimensionless ODE starting states. The earlier lab rows are displayed as history but do not separately estimate a trend.",
            "lab_only_initial_state": lab_initial,
            "laboratory_only_final_state": lab_only["mean_trajectory"][-1],
            "lab_plus_sensor_final_state": fused["mean_trajectory"][-1],
            "laboratory_only_simulation": lab_only,
            "fused_simulation": fused,
            "visible_stream_effects": {
                name: round(
                    fused["mean_trajectory"][-1][name]
                    - lab_only["mean_trajectory"][-1][name],
                    6,
                )
                for name in ("ffa", "triglyceride", "ros", "ecm")
            },
        },
        "forecast": {
            **forecast_report,
            "scenario_prediction": {
                "value": round(forecast, 6),
                "unit": "dimensionless synthetic TG proxy",
                "persistence_baseline": round(lab_initial["triglyceride"], 6),
            },
        },
        "clinician_dashboard": {
            "sections": [
                "synthetic demographic record",
                "dated laboratory history",
                "seven-day sensor observations",
                "lab-only versus fused twin output",
                "30-day synthetic forecast and held-out benchmark",
                "equation-level explanation from the fused ODE",
            ],
            "review_note": "A demo layout for technical review only; not a clinical decision-support or clinician-facing medical device.",
        },
        "reproducibility": {
            "scenario_id": "luma-two-stream-demo-v1",
            "forecast_seed": forecast_report["seed"],
            "data_generation": "fixed in source; no network, random runtime input, or persistence",
        },
    }
