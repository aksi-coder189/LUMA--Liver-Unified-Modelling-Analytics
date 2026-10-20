"""Playwright integration checks for the local API and 3D dashboard."""

from __future__ import annotations

import importlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest

pytest.importorskip(
    "playwright.sync_api", reason="Install requirements-dev.txt for browser tests"
)
playwright_api = importlib.import_module("playwright.sync_api")
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def app_url():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env["MASLD_PORT"] = str(port)
    process = subprocess.Popen(
        [sys.executable, "src/server.py", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}/"
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"LUMA server exited with status {process.returncode}")
        try:
            with urlopen(url + "api/v1/health", timeout=1) as response:
                if response.status == 200:
                    break
        except (OSError, URLError):
            time.sleep(0.1)
    else:
        process.terminate()
        raise RuntimeError("LUMA server did not become ready within 20 seconds")
    yield url
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@pytest.fixture(scope="module")
def playwright_runtime():
    manager = sync_playwright()
    try:
        runtime = manager.start()
    except PermissionError as exc:
        pytest.skip(f"Runner blocks Playwright's local driver process: {exc}")
    yield runtime
    runtime.stop()


def test_api_response_matches_displayed_liver_state(app_url, playwright_runtime):
    browser = playwright_runtime.chromium.launch(
        args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"]
    )
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto(app_url, wait_until="networkidle")
    with page.expect_response(
        lambda response: (
            response.url.endswith("/api/v1/model") and response.request.method == "POST"
        )
    ) as response_info:
        page.get_by_role("button", name="Run model").click()
    payload = response_info.value.json()
    trajectory = payload["scenario_vs_unmodified_toy_baseline"][
        "scenario_mean_trajectory"
    ]
    final_state = trajectory[-1]
    page.get_by_text("SYNTHETIC MODEL RUN", exact=True).wait_for(timeout=15000)
    assert (
        page.locator("#liver-tg-value").inner_text()
        == f"{final_state['triglyceride']:.3f}"
    )
    assert page.locator("#liver-ros-value").inner_text() == f"{final_state['ros']:.3f}"
    assert page.locator("#liver-ecm-value").inner_text() == f"{final_state['ecm']:.3f}"
    chart_data = json.loads(
        page.locator("#analysis-trend").get_attribute("data-payload")
    )
    assert chart_data["scenario"][-1] == final_state
    explanation = page.locator("#explainability-chart")
    explanation_payload = json.loads(explanation.get_attribute("data-payload"))
    assert explanation_payload["metric"] == "triglyceride"
    assert explanation_payload["points"][-1]["terms"]
    assert (
        "Reconciles within numerical tolerance"
        in page.locator("#explainability-reconciliation").inner_text()
    )
    page.locator("#explainability-metric").select_option("ros")
    whole_liver_ros = json.loads(explanation.get_attribute("data-payload"))
    page.locator("#liver-zone").select_option("2")
    zone_payload = json.loads(explanation.get_attribute("data-payload"))
    assert zone_payload["metric"] == "ros"
    assert "Zone 3" in page.locator("#explainability-title").inner_text()
    assert zone_payload["points"][-1]["terms"] != whole_liver_ros["points"][-1]["terms"]
    page.locator("#liver-comparison").select_option("difference")
    assert zone_payload["mode"] == "scenario"
    difference_payload = json.loads(explanation.get_attribute("data-payload"))
    assert difference_payload["mode"] == "difference"
    assert (
        "Scenario minus baseline" in page.locator("#explainability-title").inner_text()
    )
    assert (
        "Reconciles within numerical tolerance"
        in page.locator("#explainability-reconciliation").inner_text()
    )
    browser.close()


def test_complete_two_stream_synthetic_story_is_displayed(app_url, playwright_runtime):
    browser = playwright_runtime.chromium.launch(
        args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"]
    )
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(app_url, wait_until="networkidle")
    with page.expect_response(
        lambda response: response.url.endswith("/api/v1/demo")
    ) as response_info:
        page.get_by_role("button", name="Run complete synthetic story").click()
    demo = response_info.value.json()
    page.locator("#two-stream-dashboard").wait_for(state="visible")
    assert len(demo["patient_record"]["historical_laboratory_values"]) == 3
    assert len(demo["sensor_stream"]["observations"]) == 7
    assert demo["twin_update"]["visible_stream_effects"]["triglyceride"] != 0
    assert demo["forecast"]["heldout_records"] == 100
    assert "persistence" in page.locator("#demo-evaluation").inner_text().lower()
    assert "labs + sensors" in page.locator("#demo-state-comparison").inner_text()
    assert page.locator("#demo-twin-chart").evaluate(
        "el => el.width > 0 && el.height > 0"
    )
    assert not errors, errors
    browser.close()


def test_desktop_api_scenario_playback_zones_rotation_and_zoom(
    app_url, playwright_runtime
):
    browser = playwright_runtime.chromium.launch(
        args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"]
    )
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console",
        lambda message: (
            errors.append(message.text) if message.type == "error" else None
        ),
    )
    page.goto(app_url, wait_until="networkidle")
    expect(page.locator("#liver-reset-camera")).to_be_enabled(timeout=15000)
    page.get_by_role("button", name="Load example").click()
    page.get_by_text("SYNTHETIC MODEL RUN", exact=True).wait_for(timeout=15000)
    assert page.locator("#liver-canvas").evaluate("el => el.width > 0 && el.height > 0")

    page.locator("#liver-zone").select_option("2")
    assert "ZONE 3" in page.locator("#liver-selected-zone").inner_text()
    page.locator('[data-view-mode="zones"]').click()
    page.locator("#liver-time").evaluate(
        "el => { el.value = '0'; el.dispatchEvent(new Event('input', {bubbles:true})); }"
    )
    page.locator("#liver-play").click()
    page.wait_for_timeout(350)
    assert int(page.locator("#liver-time").input_value()) > 0
    page.locator("#liver-play").click()
    page.locator("#liver-scenario").select_option("reduce_uptake")
    page.locator("#liver-comparison").select_option("difference")
    page.locator("#liver-zoom").evaluate(
        "el => { el.value = '1.6'; el.dispatchEvent(new Event('input', {bubbles:true})); }"
    )
    page.locator('[data-view-mode="liver"]').click()
    canvas = page.locator("#liver-canvas")
    box = canvas.bounding_box()
    assert box and box["width"] > 0 and box["height"] > 0
    before_rotation = canvas.screenshot()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(
        box["x"] + box["width"] / 2 + 45,
        box["y"] + box["height"] / 2 + 18,
        steps=5,
    )
    page.mouse.up()
    page.wait_for_timeout(80)
    assert canvas.screenshot() != before_rotation
    page.locator("#liver-reset-camera").click()
    assert page.locator("#liver-zoom").input_value() == "1"
    assert not errors, errors
    browser.close()


def test_mobile_layout_and_failed_asset_fallback(app_url, playwright_runtime):
    browser = playwright_runtime.chromium.launch(
        args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"]
    )
    mobile = browser.new_page(
        viewport={"width": 390, "height": 844}, device_scale_factor=1
    )
    mobile.goto(app_url, wait_until="networkidle")
    assert mobile.locator("#liver-canvas").evaluate(
        "el => el.getBoundingClientRect().width > 0"
    )
    mobile.close()

    page = browser.new_page()
    page.route("**/*.glb", lambda route: route.abort())
    page.goto(app_url, wait_until="networkidle")
    page.locator("#liver-static-fallback").wait_for(state="visible", timeout=10000)
    assert "Static anatomy" in page.locator("#liver-model-message").inner_text()
    assert page.locator("#load-example").is_enabled()
    browser.close()


def test_webgl_unavailable_uses_static_fallback(app_url, playwright_runtime):
    browser = playwright_runtime.chromium.launch()
    page = browser.new_page()
    page.add_init_script("""
          const original = HTMLCanvasElement.prototype.getContext;
          HTMLCanvasElement.prototype.getContext = function(type, ...args) {
            if (String(type).startsWith('webgl')) throw new Error('WebGL disabled by browser test');
            return original.call(this, type, ...args);
          };
    """)
    page.goto(app_url, wait_until="networkidle")
    page.locator("#liver-static-fallback").wait_for(state="visible", timeout=10000)
    assert "3D is unavailable" in page.locator("#liver-model-message").inner_text()
    assert page.locator("#load-example").is_enabled()
    browser.close()
