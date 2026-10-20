"""Synthetic ODE/PDE simulation routines."""

from __future__ import annotations

import math
from typing import Any

from ..services.artifacts import load_trained_model
from .scenarios import genetic_modifier, parameter_perturbations


def predict_derivatives(
    features: list[float], weights: dict[str, list[float]]
) -> tuple[float, float, float, float]:
    return tuple(
        sum(x * coefficient for x, coefficient in zip(features, weights[target]))
        for target in ("d_ffa", "d_tg", "d_ros", "d_ecm")
    )


def oxygen_pde(cells: int = 41, duration: float = 0.2) -> list[float]:
    """Explicit teaching solver with a conservative grid-dependent stable step."""
    if (
        isinstance(cells, bool)
        or not isinstance(cells, int)
        or not 5 <= cells <= 401
        or isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or not 0 < duration <= 10
    ):
        raise ValueError(
            "PDE cells must be 5..401 and duration must be positive and at most 10."
        )
    dx, velocity, diffusivity, uptake = 1 / (cells - 1), 0.15, 0.08, 0.12
    dt_limit = 0.45 / (2 * diffusivity / dx**2 + velocity / dx)
    steps = max(1, math.ceil(duration / dt_limit))
    dt = duration / steps
    c = [65 - 40 * i / (cells - 1) for i in range(cells)]
    for _ in range(steps):
        old = c[:]
        for i in range(1, cells - 1):
            adv = -velocity * (old[i] - old[i - 1]) / dx
            diff = diffusivity * (old[i + 1] - 2 * old[i] + old[i - 1]) / dx**2
            c[i] = max(0, old[i] + dt * (adv + diff - uptake))
        c[0], c[-1] = 65, 25
    return [round(v, 2) for v in c]


DEFAULT_PARAMETERS = {"uptake": 0.045, "dnl": 0.035, "beta_oxidation": 0.055}
SIMULATION_FEATURES = (
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
)
EXPLAINED_STATES = ("triglyceride", "ros", "ecm")
STATE_TARGETS = {"triglyceride": "d_tg", "ros": "d_ros", "ecm": "d_ecm"}
FEATURE_LABELS = {
    "intercept": "Surrogate intercept",
    "uptake": "Substrate uptake feature",
    "dnl": "DNL feature",
    "ffa": "FFA state feature",
    "tg": "TG state feature",
    "beta_oxidation": "β-oxidation feature",
    "ros": "ROS state feature",
    "ecm": "ECM state feature",
    "hsc_signal": "HSC signal feature",
    "mmp_signal": "MMP signal feature",
}


def _explanation_point(
    state_value: float,
    initial_value: float,
    cumulative_terms: dict[str, float],
    step: int,
    time: float,
) -> dict[str, Any]:
    term_sum = sum(cumulative_terms.values())
    net_change = state_value - initial_value
    clipping_adjustment = net_change - term_sum
    return {
        "step": step,
        "time": round(time, 8),
        "state_value": round(state_value, 8),
        "net_state_change": round(net_change, 10),
        "cumulative_contributions": {
            name: round(value, 10) for name, value in cumulative_terms.items()
        },
        "clipping_adjustment": round(clipping_adjustment, 10),
        "reconstructed_change": round(term_sum + clipping_adjustment, 10),
        "reconciliation_error": round(term_sum + clipping_adjustment - net_change, 12),
    }


def simulate(
    data: dict[str, Any] | None = None,
    duration: float = 30,
    steps: int = 600,
    zones: int = 5,
    model: dict[str, Any] | None = None,
    *,
    initial_state: dict[str, float] | None = None,
    parameters: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Use the synthetic-trained derivative surrogate in a dimensionless ODE demo."""
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise TypeError("Simulation input must be a JSON-style object.")
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration <= 0
        or isinstance(steps, bool)
        or not isinstance(steps, int)
        or not 10 <= steps <= 10000
        or isinstance(zones, bool)
        or not isinstance(zones, int)
        or not 1 <= zones <= 20
    ):
        raise ValueError("duration must be positive, steps 10..10000, zones 1..20.")
    model = model or load_trained_model()
    params = {**DEFAULT_PARAMETERS, **(parameters or {})}
    if set(params) != set(DEFAULT_PARAMETERS) or any(
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not math.isfinite(v)
        or v < 0
        for v in params.values()
    ):
        raise ValueError(
            "Simulation parameters must be finite, non-negative values for the documented parameter set."
        )
    initial = {"ffa": 0.4, "triglyceride": 0.2, "ros": 0.1, "ecm": 0.05}
    if initial_state is not None:
        if set(initial_state) != set(initial) or any(
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            or v < 0
            for v in initial_state.values()
        ):
            raise ValueError(
                "Initial state must provide finite non-negative FFA, triglyceride, ROS, and ECM values."
            )
        initial.update(initial_state)
    factors, active = parameter_perturbations(data)
    gri = genetic_modifier(data).get("grI_toy_multiplier", 1.0)
    dt = duration / steps
    zonal = []
    zone_histories = []
    zonal_explanations = []
    feature_ranges = model.get("feature_ranges")
    feature_names = model.get("feature_names", list(SIMULATION_FEATURES))
    if feature_names != list(SIMULATION_FEATURES):
        raise ValueError(
            "Model feature names do not match the simulator feature order."
        )
    domain_counts: dict[str, int] = {}
    evaluated_features = 0
    for z in range(zones):
        oxygen = 1 - 0.62 * z / max(1, zones - 1)
        ffa, tg, ros, ecm = (
            initial["ffa"],
            initial["triglyceride"],
            initial["ros"],
            initial["ecm"],
        )
        history = []
        initial_values = {
            "triglyceride": tg,
            "ros": ros,
            "ecm": ecm,
        }
        cumulative_terms = {
            state_name: {feature: 0.0 for feature in feature_names}
            for state_name in EXPLAINED_STATES
        }
        explanation_history = {state_name: [] for state_name in EXPLAINED_STATES}
        for step in range(steps + 1):
            if step % 10 == 0:
                history.append({"ffa": ffa, "triglyceride": tg, "ros": ros, "ecm": ecm})
                state_values = {"triglyceride": tg, "ros": ros, "ecm": ecm}
                for state_name in EXPLAINED_STATES:
                    explanation_history[state_name].append(
                        _explanation_point(
                            state_values[state_name],
                            initial_values[state_name],
                            cumulative_terms[state_name],
                            step,
                            duration * step / steps,
                        )
                    )
            if step == steps:
                break
            uptake = params["uptake"] * factors["uptake"] * gri
            dnl = params["dnl"] * factors["dnl"]
            beta_ox = (
                params["beta_oxidation"]
                * factors["beta_oxidation"]
                * oxygen
                * ffa
                / (0.3 + ffa)
            )
            hsc_signal = ros / (0.2 + ros)
            mmp_signal = ecm * factors["mmp_degradation"]
            features = [
                1.0,
                uptake,
                dnl,
                ffa,
                tg,
                beta_ox,
                ros,
                ecm,
                hsc_signal,
                mmp_signal,
            ]
            if isinstance(feature_ranges, dict) and len(feature_names) == len(features):
                evaluated_features += len(features)
                for name, value in zip(feature_names, features):
                    bounds = feature_ranges.get(name)
                    if (
                        isinstance(bounds, dict)
                        and isinstance(bounds.get("minimum"), (int, float))
                        and isinstance(bounds.get("maximum"), (int, float))
                        and not bounds["minimum"] <= value <= bounds["maximum"]
                    ):
                        domain_counts[name] = domain_counts.get(name, 0) + 1
            d_ffa, d_tg, d_ros, d_ecm = predict_derivatives(features, model["weights"])
            for state_name, target_name in STATE_TARGETS.items():
                for feature_name, feature_value, coefficient in zip(
                    feature_names, features, model["weights"][target_name], strict=True
                ):
                    cumulative_terms[state_name][feature_name] += (
                        dt * feature_value * coefficient
                    )
            ffa, tg = max(0, ffa + dt * d_ffa), max(0, tg + dt * d_tg)
            ros, ecm = max(0, ros + dt * d_ros), max(0, ecm + dt * d_ecm)
        zonal.append(
            {
                "zone_fraction": round(z / max(1, zones - 1), 3),
                "relative_oxygen": round(oxygen, 3),
                "state": {
                    "ffa": round(ffa, 4),
                    "triglyceride": round(tg, 4),
                    "ros": round(ros, 4),
                    "ecm": round(ecm, 4),
                },
            }
        )
        zone_histories.append(history)
        zonal_explanations.append(
            {
                "zone_fraction": round(z / max(1, zones - 1), 3),
                "trajectories": explanation_history,
            }
        )
    mean_trajectory = []
    for point in range(len(zone_histories[0])):
        mean_trajectory.append(
            {
                name: sum(zone_histories[z][point][name] for z in range(zones)) / zones
                for name in ("ffa", "triglyceride", "ros", "ecm")
            }
        )
    mean_explanations: dict[str, list[dict[str, Any]]] = {
        state_name: [] for state_name in EXPLAINED_STATES
    }
    for point in range(len(zone_histories[0])):
        for state_name in EXPLAINED_STATES:
            source_points = [
                zone["trajectories"][state_name][point] for zone in zonal_explanations
            ]
            mean_state = mean_trajectory[point][state_name]
            mean_terms = {
                feature: sum(
                    row["cumulative_contributions"][feature] for row in source_points
                )
                / zones
                for feature in feature_names
            }
            mean_explanations[state_name].append(
                _explanation_point(
                    mean_state,
                    initial[state_name],
                    mean_terms,
                    source_points[0]["step"],
                    source_points[0]["time"],
                )
            )
    return {
        "model": model["model_name"],
        "model_name": model["model_name"],
        "model_version": model["model_version"],
        "time_units": "arbitrary, not months or years",
        "duration": duration,
        "steps": steps,
        "active_perturbations": active,
        "parameter_factors": factors,
        "parameter_baseline": params,
        "assumptions_changed": [
            {
                "parameter": name,
                "baseline_factor": 1.0,
                "scenario_factor": value,
                "source": "illustrative synthetic model assumption",
            }
            for name, value in factors.items()
            if value != 1.0
        ],
        "zonal_states": zonal,
        "zonal_trajectories": [
            {"zone_fraction": zonal[index]["zone_fraction"], "trajectory": history}
            for index, history in enumerate(zone_histories)
        ],
        "mean_trajectory": mean_trajectory,
        "explainability": {
            "method": "For the fitted linear derivative surrogate, each feature contribution is its observed feature value multiplied by its fitted coefficient, integrated over the forward-Euler steps. Contributions explain this synthetic calculation only; they are not causal or clinical attributions.",
            "state_change_units": "dimensionless arbitrary state units",
            "time_units": "arbitrary model-time units",
            "feature_labels": FEATURE_LABELS,
            "targets": list(EXPLAINED_STATES),
            "mean_trajectory": mean_explanations,
            "zones": zonal_explanations,
            "reconciliation": "Cumulative feature contributions plus the non-negative clamp adjustment equal the displayed state change from initialization; the residual is reported per time point.",
        },
        "oxygen_pde_profile_mmhg": oxygen_pde(),
        "state_units": "dimensionless arbitrary model units",
        "surrogate_domain_check": {
            "status": "unassessed"
            if evaluated_features == 0
            else "outside_synthetic_training_range"
            if domain_counts
            else "within_synthetic_training_range",
            "outside_feature_evaluations": domain_counts,
            "evaluated_feature_values": evaluated_features,
            "scope": "Compares internal dimensionless simulation features with synthetic training ranges only. It is not a clinical out-of-distribution detector or safety guarantee.",
        },
        "interpretation": "Relative model states only; no stage labels, calibrated probabilities, clinical trajectory, or treatment effect claims.",
        "limitations": [
            "all rate and perturbation coefficients are illustrative assumptions",
            "not fitted to patients",
            "not validated",
            "Euler/PDE discretization is a teaching approximation",
        ],
    }


def physics_residual_snapshot(
    simulation: dict[str, Any], model: dict[str, Any]
) -> dict[str, Any]:
    """PINN contract remains untrained; derivative surrogate was fit synthetically."""
    return {
        "status": "synthetic_surrogate_trained_pinn_not_trained",
        "loss_terms": [
            "ODE residuals for FFA, TG, ROS, ECM",
            "PDE residual for oxygen field",
            "supervised clinical endpoint loss",
            "calibration loss",
        ],
        "why_pinn_not_trained": "No governed longitudinal cohort, endpoint definitions, reference labels, or held-out clinical evaluation set was supplied.",
        "surrogate_training": {
            "training_data": model["training_data"],
            "metrics": model["metrics"],
        },
        "residual_computation": "The fitted linear derivative surrogate is used by the ODE solver. A neural PINN and clinical endpoint model are not implemented.",
    }
