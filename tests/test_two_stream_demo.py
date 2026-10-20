from masld_app.services.two_stream_demo import build_demo


def test_two_stream_demo_is_reproducible_and_fuses_lab_and_sensor_streams():
    first = build_demo()
    second = build_demo()
    assert first["scenario_id"] == "luma-two-stream-demo-v1"
    assert first["patient_record"] == second["patient_record"]
    assert first["sensor_stream"] == second["sensor_stream"]
    assert first["forecast"] == second["forecast"]
    assert len(first["patient_record"]["historical_laboratory_values"]) == 3
    assert len(first["sensor_stream"]["observations"]) == 7
    assert (
        first["twin_update"]["laboratory_only_final_state"]
        != first["twin_update"]["lab_plus_sensor_final_state"]
    )
    assert any(
        value != 0 for value in first["twin_update"]["visible_stream_effects"].values()
    )
    assert first["twin_update"]["fused_simulation"]["explainability"][
        "mean_trajectory"
    ]["triglyceride"]


def test_forecast_reports_heldout_synthetic_ground_truth_and_persistence_baseline():
    forecast = build_demo()["forecast"]
    assert forecast["target"] == "synthetic dimensionless TG proxy at 30 days"
    assert forecast["training_records"] == 400
    assert forecast["heldout_records"] == 100
    assert (
        "Independent deterministic synthetic target equation"
        in forecast["ground_truth"]
    )
    assert set(forecast["heldout_metrics"]) == {"model", "persistence_baseline"}
    assert forecast["heldout_metrics"]["model"]["mae"] < 0.1
    assert forecast["scenario_prediction"]["value"] >= 0
