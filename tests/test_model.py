import math
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from masld_app import config
from masld_app.domain.markers import marker_summary
from masld_app.domain.schema import validate
from masld_app.domain.simulation import oxygen_pde, simulate
from masld_app.services import artifacts
from masld_app.services.data_generation import FEATURES, build_dataset
from masld_app.services.training import (
    assumption_uncertainty_propagation,
    fit_regressor,
    train,
)


def test_schema_enforces_ranges_and_genomic_consent():
    with pytest.raises(ValueError):
        validate({"age_years": 17})
    with pytest.raises(ValueError, match="genomic_consent"):
        validate({"pnpla3_genotype": "GG"})
    assert validate({"reduce_uptake": True})["reduce_uptake"] is True
    with pytest.raises(ValueError, match="Unsupported"):
        validate({"unsupported_flag": True})


def test_marker_arithmetic_and_zero_alt_guard():
    summary = marker_summary(
        {
            "height_m": 1.7,
            "weight_kg": 70,
            "age_years": 50,
            "ast_u_l": 40,
            "alt_u_l": 25,
            "platelets_10e9_l": 200,
        }
    )
    assert summary["bmi_kg_m2"] == 24.22
    assert summary["fib4_arithmetic_only"] > 0
    assert "fib4_arithmetic_only" not in marker_summary(
        {"age_years": 50, "ast_u_l": 20, "alt_u_l": 0, "platelets_10e9_l": 200}
    )


def test_synthetic_training_is_seed_reproducible_and_compares_estimators():
    assert build_dataset(100, 31) == build_dataset(100, 31)
    result_a, result_b = train(400, 31), train(400, 31)
    assert result_a["weights"] == result_b["weights"]
    assert (
        result_a["comparison"]["ols"]["targets"].keys()
        == result_a["comparison"]["ridge_alpha_0_01"]["targets"].keys()
    )
    assert result_a["metrics"]["holdout_rows"] == 80
    assert math.isfinite(result_a["comparison"]["ols"]["targets"]["d_ffa"]["r_squared"])
    assert result_a["comparison"]["ols"]["inference_latency_ms_per_1000_rows"] >= 0
    assert set(result_a["feature_ranges"]) == set(FEATURES)
    assert all(
        math.isfinite(value)
        for coefficients in result_a["weights"].values()
        for value in coefficients
    )
    with pytest.raises(TypeError, match="seed"):
        build_dataset(100, True)


def test_simulation_and_pde_are_nonnegative_and_reject_invalid_state():
    model = {
        "model_name": "test",
        "model_version": 1,
        "weights": fit_regressor(build_dataset(400, 9)),
    }
    output = simulate(
        duration=10,
        steps=300,
        model=model,
        initial_state={"ffa": 0.1, "triglyceride": 0.3, "ros": 0.2, "ecm": 0.02},
    )
    assert len(output["zonal_states"]) == 5
    assert all(
        value >= 0 and math.isfinite(value)
        for zone in output["zonal_states"]
        for value in zone["state"].values()
    )
    assert all(value >= 0 and math.isfinite(value) for value in oxygen_pde(cells=81))
    with pytest.raises(ValueError, match="Initial state"):
        simulate(
            model=model,
            initial_state={"ffa": -1, "triglyceride": 0, "ros": 0, "ecm": 0},
        )
    with pytest.raises(ValueError):
        oxygen_pde(cells=2)


def test_scenario_outputs_name_generic_assumptions_only():
    model = {
        "model_name": "test",
        "model_version": 1,
        "weights": fit_regressor(build_dataset(400, 8)),
    }
    result = simulate({"reduce_uptake": True}, model=model)
    assert result["active_perturbations"] == ["reduce_uptake"]
    assert result["assumptions_changed"] == [
        {
            "parameter": "uptake",
            "baseline_factor": 1.0,
            "scenario_factor": 0.9,
            "source": "illustrative synthetic model assumption",
        }
    ]


def test_simulation_explainability_reconciles_fitted_feature_terms():
    feature_names = [
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
    weights = {
        target: [0.0] * len(feature_names)
        for target in ("d_ffa", "d_tg", "d_ros", "d_ecm")
    }
    weights["d_tg"][3], weights["d_tg"][4] = 0.06, -0.05
    weights["d_ros"][3], weights["d_ros"][6] = 0.09, -0.035
    weights["d_ecm"][8], weights["d_ecm"][9] = 0.025, -0.008
    model = {
        "model_name": "exact-synthetic-test-equations",
        "model_version": 1,
        "feature_names": feature_names,
        "weights": weights,
    }

    result = simulate(duration=1, steps=100, zones=5, model=model)
    explanation = result["explainability"]
    assert explanation["targets"] == ["triglyceride", "ros", "ecm"]
    assert len(explanation["mean_trajectory"]["triglyceride"]) == 11
    for state_name in explanation["targets"]:
        for point in explanation["mean_trajectory"][state_name]:
            term_sum = sum(point["cumulative_contributions"].values())
            assert math.isclose(
                term_sum + point["clipping_adjustment"],
                point["net_state_change"],
                abs_tol=1e-7,
            )
            assert abs(point["reconciliation_error"]) < 1e-9

    tg_final = explanation["mean_trajectory"]["triglyceride"][-1][
        "cumulative_contributions"
    ]
    ros_final = explanation["mean_trajectory"]["ros"][-1]["cumulative_contributions"]
    ecm_final = explanation["mean_trajectory"]["ecm"][-1]["cumulative_contributions"]
    assert tg_final["ffa"] > 0 and tg_final["tg"] < 0 and tg_final["dnl"] == 0
    assert ros_final["ffa"] > 0 and ros_final["ros"] < 0
    assert ecm_final["hsc_signal"] > 0 and ecm_final["mmp_signal"] < 0


def test_simulation_rejects_malformed_runtime_parameters():
    model = {
        "model_name": "test",
        "model_version": 1,
        "weights": fit_regressor(build_dataset(400, 8)),
    }
    with pytest.raises(ValueError, match="duration"):
        simulate(model=model, duration=True)
    with pytest.raises(ValueError, match="duration"):
        simulate(model=model, steps=10.5)


def test_surrogate_feature_range_check_flags_synthetic_extrapolation():
    model = {
        "model_name": "test",
        "model_version": 1,
        "weights": fit_regressor(build_dataset(400, 19)),
        "feature_names": FEATURES,
        "feature_ranges": {name: {"minimum": 0.0, "maximum": 0.0} for name in FEATURES},
    }
    result = simulate(model=model, steps=10)
    check = result["surrogate_domain_check"]
    assert check["status"] == "outside_synthetic_training_range"
    assert check["outside_feature_evaluations"]
    assert "not a clinical" in check["scope"]


def test_reference_scenario_stays_inside_synthetic_feature_ranges():
    from masld_app.services.training import train

    trained = train(800, 20261019)
    model = {
        "model_name": "test",
        "model_version": 1,
        "weights": trained["weights"],
        "feature_names": FEATURES,
        "feature_ranges": trained["feature_ranges"],
    }
    result = simulate(model=model)
    assert (
        result["surrogate_domain_check"]["status"] == "within_synthetic_training_range"
    )


def test_model_artifact_rejects_missing_corrupt_and_incompatible_files(monkeypatch):
    path = Path(__file__).resolve().parents[1] / f".test-artifact-{os.getpid()}.json"
    try:
        monkeypatch.setattr(artifacts, "MODEL_PATH", path)
        with pytest.raises(FileNotFoundError, match="Run"):
            artifacts.load_trained_model()
        path.write_text("{broken", encoding="utf-8")
        with pytest.raises(ValueError):
            artifacts.load_trained_model()
        path.write_text('{"feature_names": []}', encoding="utf-8")
        with pytest.raises(ValueError, match="feature schema"):
            artifacts.load_trained_model()
    finally:
        path.unlink(missing_ok=True)


def test_runtime_model_uses_ephemeral_synthetic_fallback_when_artifact_is_missing(
    monkeypatch,
):
    path = (
        Path(__file__).resolve().parents[1] / f".test-missing-model-{os.getpid()}.json"
    )
    monkeypatch.setattr(artifacts, "MODEL_PATH", path)
    monkeypatch.setattr(artifacts, "_runtime_artifact", None)
    monkeypatch.setattr(artifacts, "_runtime_source", "checked-in artifact")
    artifact, source = artifacts.initialize_runtime_model()
    assert source == "in-memory synthetic fallback"
    assert "memory" in artifact["training_data"]
    assert artifact["model_name"].endswith("memory_fallback")
    assert not path.exists()
    path.write_text("{invalid", encoding="utf-8")
    monkeypatch.setattr(artifacts, "_runtime_artifact", None)
    artifact, source = artifacts.initialize_runtime_model()
    assert source == "in-memory synthetic fallback"
    assert artifact["model_name"].endswith("memory_fallback")
    assert path.read_text(encoding="utf-8") == "{invalid"
    path.unlink()


def test_runtime_guard_accepts_current_runtime_and_rejects_python_3131(monkeypatch):
    config.ensure_supported_runtime()
    monkeypatch.setattr(
        config.sys,
        "version_info",
        SimpleNamespace(major=3, minor=13, micro=1, releaselevel="final"),
    )
    with pytest.raises(RuntimeError, match="3.13.16"):
        config.ensure_supported_runtime()


def test_assumption_uncertainty_propagation_is_reproducible_and_explicitly_nonclinical():
    weights = fit_regressor(build_dataset(400, 23))
    first = assumption_uncertainty_propagation(weights, samples=20, seed=4)
    second = assumption_uncertainty_propagation(weights, samples=20, seed=4)
    assert first == second
    assert "not fitted parameter uncertainty" in first["interpretation"]
    assert all(
        item["p05"] <= item["median"] <= item["p95"]
        for item in first["final_mean_state_quantiles"].values()
    )
