"""Application service composing model outputs for API and CLI callers."""

from __future__ import annotations

from typing import Any

from ..domain.markers import marker_summary
from ..domain.scenarios import genetic_modifier
from ..domain.schema import PERTURBATIONS
from ..domain.simulation import DEFAULT_PARAMETERS, physics_residual_snapshot, simulate
from .artifacts import load_runtime_model


def run(data: dict[str, Any]) -> dict[str, Any]:
    model = load_runtime_model()
    baseline_input = {
        key: value for key, value in data.items() if key not in PERTURBATIONS
    }
    baseline = simulate(baseline_input, model=model)
    scenario = simulate(data, model=model)
    sensitivity = []
    final_names = ("ffa", "triglyceride", "ros", "ecm")
    for parameter, baseline_value in DEFAULT_PARAMETERS.items():
        endpoints = []
        for multiplier in (0.8, 1.2):
            altered = dict(DEFAULT_PARAMETERS)
            altered[parameter] = baseline_value * multiplier
            response = simulate(baseline_input, model=model, parameters=altered)
            endpoints.append(
                {
                    name: sum(zone["state"][name] for zone in response["zonal_states"])
                    / len(response["zonal_states"])
                    for name in final_names
                }
            )
        sensitivity.append(
            {
                "parameter": parameter,
                "range": [
                    round(baseline_value * 0.8, 6),
                    round(baseline_value * 1.2, 6),
                ],
                "final_state_range": {
                    name: [
                        round(min(endpoint[name] for endpoint in endpoints), 4),
                        round(max(endpoint[name] for endpoint in endpoints), 4),
                    ]
                    for name in final_names
                },
            }
        )
    comparisons = []
    for base_zone, scenario_zone in zip(
        baseline["zonal_states"], scenario["zonal_states"]
    ):
        row: dict[str, Any] = {"zone_fraction": scenario_zone["zone_fraction"]}
        for state_name, scenario_value in scenario_zone["state"].items():
            base_value = base_zone["state"][state_name]
            row[state_name] = {
                "baseline": base_value,
                "scenario": scenario_value,
                "relative_delta_percent": None
                if base_value == 0
                else round(100 * (scenario_value - base_value) / base_value, 2),
            }
        comparisons.append(row)
    return {
        "notice": "SYNTHETIC RESEARCH SCAFFOLD — NOT FOR CLINICAL USE",
        "marker_summary": marker_summary(data),
        "genetic_scenario": genetic_modifier(data),
        "mechanistic_simulation": scenario,
        "scenario_vs_unmodified_toy_baseline": {
            "warning": "Purely mathematical comparison with generic perturbations removed and other synthetic inputs held constant; not a clinical response estimate.",
            "baseline_mean_trajectory": baseline["mean_trajectory"],
            "scenario_mean_trajectory": scenario["mean_trajectory"],
            "baseline_zonal_trajectories": baseline["zonal_trajectories"],
            "baseline_explainability": baseline["explainability"],
            "zonal_state_deltas": comparisons,
        },
        "parameter_sensitivity": {
            "meaning": "Final state ranges when one illustrative coefficient varies by ±20%; this is assumption sensitivity, not patient uncertainty.",
            "results": sensitivity,
        },
        "physics_informed_ml": physics_residual_snapshot({}, model),
        "privacy": {
            "persistence": "none by this program",
            "network": "none",
            "genotype_echoed": False,
            "note": "Input file remains under the caller's control; this is not a consent-management system.",
        },
    }
