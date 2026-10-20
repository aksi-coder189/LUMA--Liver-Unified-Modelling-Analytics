import { requestHealth, requestModel, requestDemo } from "./assets/js/api-client.js?v=16";
import { createStore } from "./assets/js/store.js?v=15";
import { drawComparisonChart } from "./assets/js/components/chart.js?v=15";
import { renderSimulationAnalysis, resizeAnalysisChart } from "./assets/js/components/analysis-dashboard.js?v=15";
import { renderExplainability, resizeExplainabilityChart } from "./assets/js/components/explainability-dashboard.js?v=15";
import { createLiverRenderer } from "./assets/js/components/liver-renderer.js?v=15";
import { extractReport } from "./assets/js/components/report-importer.js?v=15";

(() => {
  "use strict";

  // Requests are sent only to the same-origin loopback Python server. No storage or analytics.
  const form = document.querySelector("#model-form");
  const errorBox = document.querySelector("#form-error");
  const consent = document.querySelector("#genomic-consent");
  const genotypeFields = document.querySelector("#genotype-fields");
  const runButton = form.querySelector(".run-button");
  const topRunButton = document.querySelector("#run-model-top");
  const reportFile = document.querySelector("#report-file");
  const reportStatus = document.querySelector("#report-import-status");
  const reportReview = document.querySelector("#report-import-review");
  const titles = { triglyceride: "Triglyceride", ros: "ROS", ecm: "ECM" };
  const scenarioLabels = {
    selected: "Selected assumptions", baseline: "Baseline",
    reduce_uptake: "Reduced uptake assumption", reduce_dnl: "Reduced DNL assumption",
    increase_oxidation: "Increased oxidation assumption", increase_matrix_turnover: "Increased matrix turnover assumption"
  };
  const scenarioKeys = ["reduce_uptake", "reduce_dnl", "increase_oxidation", "increase_matrix_turnover"];
  const liverSelect = document.querySelector("#liver-scenario");
  const liverRenderer = createLiverRenderer(document.querySelector("#liver-canvas"));
  const store = createStore({ currentRun: 0, scenarioCache: {}, result: null, demo: null });
  const zoneSelect = document.querySelector("#liver-zone");
  const comparisonSelect = document.querySelector("#liver-comparison");
  const timeInput = document.querySelector("#liver-time");
  const playButton = document.querySelector("#liver-play");
  const zoomInput = document.querySelector("#liver-zoom");
  const resetCameraButton = document.querySelector("#liver-reset-camera");
  const zoneMetric = document.querySelector("#analysis-zone-metric");
  const trendMetric = document.querySelector("#analysis-trend-metric");
  const explainabilityMetric = document.querySelector("#explainability-metric");
  let playbackTimer = null;
  const example = {
    age_years: 45, height_m: 1.68, weight_kg: 72, alt_u_l: 42, ast_u_l: 35,
    platelets_10e9_l: 220, cap_db_m: 285, lsm_kpa: 6.8,
    bia_phase_angle_deg: 5.4, fasting_glucose_mmol_l: 5.7
  };

  consent.addEventListener("change", () => {
    genotypeFields.hidden = !consent.checked;
    if (!consent.checked) genotypeFields.querySelectorAll("select").forEach((select) => { select.value = ""; });
  });

  document.querySelector("#load-example").addEventListener("click", () => {
    form.reset(); genotypeFields.hidden = true;
    Object.entries(example).forEach(([key, value]) => { form.elements.namedItem(key).value = value; });
    runModel();
  });

  // The sticky heading button is associated with this form via its `form` attribute,
  // so both run controls use this single submit path.
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    runModel().catch((error) => showError(error.message || "The local model run could not be completed."));
  });
  reportFile.addEventListener("change", importReport);
  liverSelect.addEventListener("change", () => showLiverScenario(liverSelect.value));
  zoneSelect.addEventListener("change", () => { liverRenderer.setZone(zoneSelect.value === "all" ? -1 : Number(zoneSelect.value)); updateLiverFrame(); });
  comparisonSelect.addEventListener("change", updateLiverFrame);
  timeInput.addEventListener("input", updateLiverFrame);
  zoneMetric.addEventListener("change", updateLiverFrame);
  trendMetric.addEventListener("change", updateLiverFrame);
  explainabilityMetric.addEventListener("change", updateLiverFrame);
  zoomInput.addEventListener("input", () => liverRenderer.setZoom(zoomInput.value));
  resetCameraButton.addEventListener("click", () => { liverRenderer.resetCamera(); zoomInput.value = "1"; });
  liverRenderer.ready.then((ready) => { resetCameraButton.disabled = !ready; });
  playButton.addEventListener("click", togglePlayback);
  document.querySelectorAll(".view-mode").forEach((button) => button.addEventListener("click", () => {
    document.querySelectorAll(".view-mode").forEach((item) => { const active = item === button; item.classList.toggle("active", active); item.setAttribute("aria-pressed", String(active)); });
    liverRenderer.setViewMode(button.dataset.viewMode);
  }));
  document.querySelectorAll("[data-zone-marker]").forEach((button) => button.addEventListener("click", () => { zoneSelect.value = button.dataset.zoneMarker; zoneSelect.dispatchEvent(new Event("change")); }));
  liverRenderer.onLiverClick = () => document.querySelector('[data-view-mode="liver"]').click();
  document.querySelector("#download-json").addEventListener("click", () => downloadResults("json"));
  document.querySelector("#download-csv").addEventListener("click", () => downloadResults("csv"));
  checkBackend();
  document.querySelector("#load-two-stream-demo").addEventListener("click", loadTwoStreamDemo);

  async function loadTwoStreamDemo() {
    const button = document.querySelector("#load-two-stream-demo");
    button.disabled = true;
    button.textContent = "Building reproducible story…";
    try {
      const demo = await requestDemo();
      store.setState({ demo });
      document.querySelector("#two-stream-dashboard").hidden = false;
      renderTwoStreamDemo(demo);
      document.querySelector("#run-status").textContent = "SYNTHETIC TWO-STREAM STORY";
      document.querySelector("#two-stream-dashboard").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      showError(error.message || "The synthetic two-stream story could not be loaded.");
    } finally {
      button.disabled = false;
      button.textContent = "Run complete synthetic story ↗";
    }
  }

  function renderTwoStreamDemo(demo) {
    const record = demo.patient_record;
    const facts = document.querySelector("#demo-demographics"); facts.replaceChildren();
    for (const [label, value] of Object.entries({ "Record ID": record.record_id, Age: `${record.demographics.age_years} years`, Height: `${record.demographics.height_m} m`, Weight: `${record.demographics.weight_kg} kg`, "BMI (synthetic)": record.demographics.bmi_kg_m2 })) addFact(facts, label, value);
    const labs = document.querySelector("#demo-labs"); labs.replaceChildren();
    addTable(labs, ["Date", "ALT U/L", "AST U/L", "CAP dB/m", "LSM kPa", "Glucose mmol/L"], record.historical_laboratory_values.map((row) => [row.date, row.alt_u_l, row.ast_u_l, row.cap_db_m, row.lsm_kpa, row.fasting_glucose_mmol_l]));
    const sensors = document.querySelector("#demo-sensors"); sensors.replaceChildren();
    addTable(sensors, ["Day", "Steps", "Sleep h", "Resting HR bpm"], demo.sensor_stream.observations.map((row) => [row.day, row.steps, row.sleep_hours, row.resting_hr_bpm]));
    const summary = demo.sensor_stream.summary;
    document.querySelector("#demo-sensor-mapping").textContent = `Seven-day means: ${summary.mean_steps_per_day} steps/day, ${summary.mean_sleep_hours_per_night} h/night, ${summary.mean_resting_hr_bpm} bpm. ${summary.mapping_note}`;
    document.querySelector("#two-stream-notice").textContent = demo.notice;
    document.querySelector("#demo-mapping-note").textContent = `${demo.twin_update.initial_state_mapping} Sensor mapping: ${summary.mapping_note}`;
    const stateList = document.querySelector("#demo-state-comparison"); stateList.replaceChildren();
    const labels = { ffa: "FFA proxy", triglyceride: "TG proxy", ros: "ROS proxy", ecm: "ECM proxy" };
    for (const [key, label] of Object.entries(labels)) {
      const lab = demo.twin_update.laboratory_only_final_state[key], fused = demo.twin_update.lab_plus_sensor_final_state[key], delta = demo.twin_update.visible_stream_effects[key];
      addFact(stateList, label, `Labs only ${lab.toFixed(4)} → labs + sensors ${fused.toFixed(4)} · Δ ${delta >= 0 ? "+" : ""}${delta.toFixed(4)}`);
    }
    drawDemoTwinChart(demo.twin_update.laboratory_only_simulation.mean_trajectory, demo.twin_update.fused_simulation.mean_trajectory);
    const forecast = demo.forecast;
    const prediction = document.querySelector("#demo-forecast"); prediction.replaceChildren();
    addFact(prediction, forecast.target, `${forecast.scenario_prediction.value.toFixed(4)} ${forecast.scenario_prediction.unit}`);
    addFact(prediction, "Simple persistence baseline", forecast.scenario_prediction.persistence_baseline.toFixed(4));
    const m = forecast.heldout_metrics;
    document.querySelector("#demo-evaluation").textContent = `Held-out synthetic evaluation: ${forecast.heldout_records} separately generated cases (seed ${forecast.seed}; ${forecast.training_records} train). OLS MAE ${m.model.mae}, RMSE ${m.model.rmse}; persistence MAE ${m.persistence_baseline.mae}, RMSE ${m.persistence_baseline.rmse}. Ground truth: ${forecast.ground_truth} ${forecast.limitation}`;
    document.querySelector("#demo-clinician-note").textContent = demo.clinician_dashboard.review_note;
    const terms = demo.twin_update.fused_simulation.explainability.mean_trajectory.triglyceride.at(-1).cumulative_contributions;
    const largest = Object.entries(terms).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 3).map(([name, value]) => `${name} ${value >= 0 ? "+" : ""}${value.toFixed(4)}`).join(" · ");
    document.querySelector("#demo-explanation-note").textContent = `Fused-run TG equation terms at the final step (largest by absolute magnitude): ${largest}. ${demo.twin_update.fused_simulation.explainability.method}`;
  }

  function drawDemoTwinChart(labOnly, fused) {
    const canvas = document.querySelector("#demo-twin-chart");
    const width = canvas.clientWidth || 500, height = 180, ratio = window.devicePixelRatio || 1;
    canvas.width = width * ratio; canvas.height = height * ratio;
    const context = canvas.getContext("2d"); context.scale(ratio, ratio); context.clearRect(0, 0, width, height);
    const values = [...labOnly.map((point) => point.triglyceride), ...fused.map((point) => point.triglyceride)];
    const low = Math.min(...values), high = Math.max(...values), span = Math.max(0.001, high - low);
    const pad = { left: 38, right: 12, top: 12, bottom: 27 };
    context.font = "9px monospace"; context.fillStyle = "#78877f"; context.strokeStyle = "#e3e9e1";
    for (let tick = 0; tick < 4; tick += 1) {
      const y = pad.top + tick * (height - pad.top - pad.bottom) / 3;
      context.beginPath(); context.moveTo(pad.left, y); context.lineTo(width - pad.right, y); context.stroke();
      context.fillText((high - tick * span / 3).toFixed(3), 2, y + 3);
    }
    const draw = (series, color, dashed) => {
      context.beginPath(); context.strokeStyle = color; context.lineWidth = 2; context.setLineDash(dashed ? [5, 4] : []);
      series.forEach((point, index) => {
        const x = pad.left + index * (width - pad.left - pad.right) / Math.max(1, series.length - 1);
        const y = pad.top + (high - point.triglyceride) / span * (height - pad.top - pad.bottom);
        if (index === 0) context.moveTo(x, y); else context.lineTo(x, y);
      }); context.stroke(); context.setLineDash([]);
    };
    draw(labOnly, "#567e69", true); draw(fused, "#d29c3b", false);
    context.fillStyle = "#718078"; context.fillText("arbitrary model time · synthetic TG proxy", pad.left, height - 7);
  }

  window.addEventListener("resize", () => {
    const demo = store.getState().demo;
    if (demo && !document.querySelector("#two-stream-dashboard").hidden) {
      drawDemoTwinChart(demo.twin_update.laboratory_only_simulation.mean_trajectory, demo.twin_update.fused_simulation.mean_trajectory);
    }
  });

  function addFact(container, label, value) {
    const row = document.createElement("div"); row.className = "demo-fact";
    const name = document.createElement("span"); name.textContent = label;
    const content = document.createElement("b"); content.textContent = String(value);
    row.append(name, content); container.append(row);
  }

  function addTable(container, headers, rows) {
    const table = document.createElement("table");
    const head = document.createElement("thead"), headRow = document.createElement("tr");
    headers.forEach((label) => { const th = document.createElement("th"); th.textContent = label; headRow.append(th); });
    head.append(headRow); table.append(head);
    const body = document.createElement("tbody");
    rows.forEach((values) => { const tr = document.createElement("tr"); values.forEach((value) => { const td = document.createElement("td"); td.textContent = String(value); tr.append(td); }); body.append(tr); });
    table.append(body); container.append(table);
  }

  function readInput() {
    const data = {};
    for (const field of form.querySelectorAll("input[type=number]")) {
      if (field.value.trim() === "") continue;
      const value = Number(field.value), low = Number(field.min), high = Number(field.max);
      if (!Number.isFinite(value) || value < low || value > high) {
        const label = field.labels?.[0]?.childNodes?.[0]?.textContent?.trim() || field.name;
        throw new Error(`${label} must be between ${low} and ${high}.`);
      }
      data[field.name] = value;
    }
    for (const field of form.querySelectorAll("input[type=checkbox]:not(#genomic-consent)")) if (field.checked) data[field.name] = true;
    if (consent.checked) {
      for (const select of genotypeFields.querySelectorAll("select")) if (select.value) data[select.name] = select.value;
      if (!Object.keys(data).some((key) => key.endsWith("_genotype"))) throw new Error("Choose at least one genotype value, or switch off the optional genotype section.");
      data.genomic_consent = true;
    }
    return data;
  }

  async function checkBackend() {
    const status = document.querySelector("#run-status");
    try {
      const health = await requestHealth();
      status.textContent = health.ok ? "BACKEND READY · SYNTHETIC MODEL" : "MODEL NOT READY";
      if (!health.ok) throw new Error(health.error?.message || "Train the synthetic model first.");
      status.classList.add("ready");
    } catch (error) {
      status.textContent = "BACKEND OFFLINE";
      showError(error.message || "Cannot reach the local model server. Start it with `python src/server.py`, then reload this page.");
    }
  }

  async function runModel() {
    if (form.getAttribute("aria-busy") === "true") return;
    const runId = store.getState().currentRun + 1;
    store.setState({ currentRun: runId, scenarioCache: {}, result: null });
    errorBox.hidden = true;
    [runButton, topRunButton].forEach((button) => { button.disabled = true; });
    form.setAttribute("aria-busy", "true");
    runButton.querySelector("span").textContent = "Running local model…";
    topRunButton.querySelector("span").textContent = "Running…";
    try {
      const data = readInput();
      const result = await requestModel(data);
      store.setState({ result, scenarioCache: { selected: result } });
      render(result);
      liverSelect.value = "selected";
      liverSelect.disabled = false;
      [zoneSelect, comparisonSelect, timeInput, playButton].forEach((control) => { control.disabled = false; });
      timeInput.max = String(result.mechanistic_simulation.mean_trajectory.length - 1);
      // Show the final model state immediately so the selected scenario's computed
      // differences are visible before the user starts time-step playback.
      timeInput.value = timeInput.max;
      showLiverScenario("selected");
      loadScenarioPreviews(data, runId);
      document.querySelector("#result-content").hidden = false;
      document.querySelector("#run-status").textContent = "SYNTHETIC MODEL RUN";
      requestAnimationFrame(() => drawChartResult(result));
    } catch (error) {
      showError(error instanceof TypeError
        ? `The browser could not complete this local run: ${error.message}`
        : error.message || "The local model run could not be completed.");
    } finally {
      if (runId === store.getState().currentRun) {
        runButton.disabled = false;
        runButton.firstElementChild.textContent = "Run synthetic model";
        topRunButton.disabled = false;
        topRunButton.firstElementChild.textContent = "Run model";
        form.removeAttribute("aria-busy");
      }
    }
  }

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
    errorBox.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  async function importReport() {
    reportReview.replaceChildren();
    reportReview.hidden = true;
    const file = reportFile.files?.[0];
    if (!file) return;
    reportStatus.textContent = `Reading ${file.name} in this browser…`;
    try {
      const matches = await extractReport(file);
      const imported = [], skipped = [];
      for (const match of matches) {
        const input = form.elements.namedItem(match.name);
        if (!input) continue;
        const value = Number(match.value), min = Number(input.min), max = Number(input.max);
        const label = input.labels?.[0]?.childNodes[0]?.textContent.trim() || match.name;
        if (!Number.isFinite(value) || value < min || value > max) {
          skipped.push({ label, source: match.source, reason: "Outside this field's allowed input range" });
          continue;
        }
        input.value = String(Number(value.toPrecision(8)));
        input.dispatchEvent(new Event("input", { bubbles: true }));
        imported.push({ label, value: input.value, source: match.source });
      }
      renderReportReview(imported, skipped);
      if (!imported.length && !skipped.length) reportStatus.textContent = "No supported fields were recognized. You can enter values manually.";
      else reportStatus.textContent = `${imported.length} field${imported.length === 1 ? "" : "s"} filled${skipped.length ? `; ${skipped.length} value${skipped.length === 1 ? "" : "s"} skipped for review` : ""}. Check the source text and units before running.`;
    } catch (error) {
      reportStatus.textContent = error.message || "Could not read this report. Try a plain text, CSV, or JSON export.";
    } finally {
      reportFile.value = "";
    }
  }

  function renderReportReview(imported, skipped) {
    const heading = document.createElement("strong");
    heading.textContent = "Values found in report — review before running";
    reportReview.append(heading);
    for (const item of imported) {
      const row = document.createElement("div"); row.className = "report-review-row";
      const label = document.createElement("span"); label.textContent = item.label;
      const value = document.createElement("b"); value.textContent = item.value;
      const source = document.createElement("small"); source.textContent = item.source;
      row.append(label, value, source); reportReview.append(row);
    }
    for (const item of skipped) {
      const row = document.createElement("div"); row.className = "report-review-row skipped";
      const label = document.createElement("span"); label.textContent = `${item.label} · skipped`;
      const source = document.createElement("small"); source.textContent = `${item.reason}: ${item.source}`;
      row.append(label, source); reportReview.append(row);
    }
    reportReview.hidden = false;
  }

  function drawChartResult(result) {
    const comparison = result.scenario_vs_unmodified_toy_baseline;
    drawComparisonChart(comparison.baseline_mean_trajectory, comparison.scenario_mean_trajectory,
      result.mechanistic_simulation.duration);
  }

  async function loadScenarioPreviews(input, runId) {
    const base = { ...input };
    for (const key of scenarioKeys) delete base[key];
    const requests = [{ key: "baseline", data: { ...base } }, ...scenarioKeys.map((key) => ({ key, data: { ...base, [key]: true } }))];
    await Promise.all(requests.map(async ({ key, data }) => {
      try {
        const result = await requestModel(data);
        if (runId !== store.getState().currentRun) return;
        store.setState((state) => ({ scenarioCache: { ...state.scenarioCache, [key]: result } }));
        if (liverSelect.value === key) showLiverScenario(key);
      } catch {
        if (runId !== store.getState().currentRun) return;
        if (liverSelect.value === key) document.querySelector("#liver-model-message").textContent = "This scenario could not be loaded from the local backend. Run the model again.";
      }
    }));
    if (runId === store.getState().currentRun) showLiverScenario(liverSelect.value);
  }

  function showLiverScenario(key) {
    const result = store.getState().scenarioCache[key];
    document.querySelector("#liver-scenario-name").textContent = scenarioLabels[key] || "Synthetic view";
    if (!result) {
      document.querySelector("#liver-model-message").textContent = "Calculating this scenario with the local synthetic model…";
      return;
    }
    const baselineEnd = result.scenario_vs_unmodified_toy_baseline.baseline_mean_trajectory.at(-1);
    const scenarioEnd = result.scenario_vs_unmodified_toy_baseline.scenario_mean_trajectory.at(-1);
    const deltas = ["triglyceride", "ros", "ecm"].map((name) => ({
      name,
      change: Math.abs(scenarioEnd[name] - baselineEnd[name]) / Math.max(1e-9, Math.abs(baselineEnd[name])),
    })).sort((a, b) => b.change - a.change);
    // If the currently displayed metric is unaffected by this assumption, select the
    // strongest changed proxy so the scenario's output is immediately visible.
    for (const selector of [trendMetric, zoneMetric]) {
      const selected = deltas.find((item) => item.name === selector.value);
      if ((selected?.change || 0) < 0.0005 && (deltas[0]?.change || 0) >= 0.0005) selector.value = deltas[0].name;
    }
    timeInput.max = String(result.mechanistic_simulation.mean_trajectory.length - 1);
    timeInput.value = String(Math.min(Number(timeInput.value), Number(timeInput.max)));
    zoneSelect.disabled = false; comparisonSelect.disabled = false; timeInput.disabled = false; playButton.disabled = false;
    updateLiverFrame();
  }

  function trajectoriesFor(result) {
    const comparison = result.scenario_vs_unmodified_toy_baseline;
    return { baseline: comparison.baseline_zonal_trajectories, scenario: result.mechanistic_simulation.zonal_trajectories };
  }

  function updateLiverFrame() {
    const result = store.getState().scenarioCache[liverSelect.value];
    if (!result) return;
    const histories = trajectoriesFor(result), zone = zoneSelect.value === "all" ? -1 : Number(zoneSelect.value);
    const count = result.mechanistic_simulation.mean_trajectory.length;
    const frame = Math.min(Math.max(0, Number(timeInput.value) || 0), count - 1);
    timeInput.max = String(count - 1);
    const timeLabel = document.querySelector("#liver-time-value");
    timeLabel.textContent = `${frame} / ${count - 1}`;
    document.querySelector("#liver-time-label").textContent = `MODEL STEP ${frame} · ARBITRARY TIME`;
    document.querySelector("#liver-selected-zone").textContent = zone < 0 ? "WHOLE-LIVER MEAN · SYNTHETIC PROXIES" : zone === 0 ? "ZONE 1 · PERIPORTAL · SYNTHETIC PROXIES" : zone === 4 ? "ZONE 5 · PERIVENOUS · SYNTHETIC PROXIES" : `ZONE ${zone + 1} · SYNTHETIC PROXIES`;
    const names = ["triglyceride", "ros", "ecm"];
    const baseAt = (index, step) => index < 0 ? result.scenario_vs_unmodified_toy_baseline.baseline_mean_trajectory[step] : histories.baseline[index].trajectory[step];
    const scenarioAt = (index, step) => index < 0 ? result.scenario_vs_unmodified_toy_baseline.scenario_mean_trajectory[step] : histories.scenario[index].trajectory[step];
    const selectedBase = zone < 0 ? result.scenario_vs_unmodified_toy_baseline.baseline_mean_trajectory[frame] : histories.baseline[zone].trajectory[frame];
    const selectedScenario = zone < 0 ? result.scenario_vs_unmodified_toy_baseline.scenario_mean_trajectory[frame] : histories.scenario[zone].trajectory[frame];
    const displayMode = comparisonSelect.value;
    const values = {};
    names.forEach((name) => {
      const base = selectedBase[name], scenario = selectedScenario[name];
      const current = displayMode === "baseline" ? base : displayMode === "difference" ? Math.abs(scenario - base) : scenario;
      values[name] = current;
      document.querySelector(`#liver-${name === "triglyceride" ? "tg" : name}-value`).textContent = current.toFixed(3);
      const change = base === 0 ? "n/a" : `${((scenario - base) / Math.abs(base) * 100) > 0 ? "+" : ""}${((scenario - base) / Math.abs(base) * 100).toFixed(1)}%`;
      document.querySelector(`#liver-${name === "triglyceride" ? "tg" : name}-compare`).textContent = `B ${base.toFixed(3)} → S ${scenario.toFixed(3)} · Δ ${change}`;
    });
    // Normalize each signal over the complete baseline/scenario time series for this selected run.
    const intensities = names.map((name) => {
      const series = [];
      for (let index = 0; index < count; index += 1) {
        series.push(baseAt(zone, index)[name], scenarioAt(zone, index)[name]);
      }
      const low = Math.min(...series), high = Math.max(...series);
      const val = displayMode === "baseline" ? selectedBase[name] : displayMode === "difference" ? Math.abs(selectedScenario[name] - selectedBase[name]) : selectedScenario[name];
      if (displayMode === "difference") {
        const maxDelta = Math.max(...Array.from({ length: count }, (_, step) => Math.abs(scenarioAt(zone, step)[name] - baseAt(zone, step)[name])));
        return maxDelta < 1e-9 ? 0.08 : Math.max(0.08, Math.abs(selectedScenario[name] - selectedBase[name]) / maxDelta);
      }
      return high - low < 1e-9 ? 0.5 : Math.max(0.08, Math.min(1, (val - low) / (high - low)));
    });
    const zoneIntensities = Array.from({ length: 5 }, (_, index) => {
      const b = histories.baseline[index].trajectory[frame], s = histories.scenario[index].trajectory[frame];
      return Math.max(...names.map((name) => {
        const all = [];
        for (let step = 0; step < count; step += 1) all.push(histories.baseline[index].trajectory[step][name], histories.scenario[index].trajectory[step][name]);
        const low = Math.min(...all), high = Math.max(...all);
        if (displayMode === "difference") {
          let maxDelta = 0;
          for (let step = 0; step < count; step += 1) maxDelta = Math.max(maxDelta, Math.abs(histories.scenario[index].trajectory[step][name] - histories.baseline[index].trajectory[step][name]));
          return maxDelta < 1e-9 ? 0.08 : Math.abs(s[name] - b[name]) / maxDelta;
        }
        const value = displayMode === "baseline" ? b[name] : s[name];
        return high - low < 1e-9 ? 0.5 : (value - low) / (high - low);
      }));
    });
    // These are normalized over the available histories, so the tint follows model output
    // without implying clinical severity or progression.
    liverRenderer.setSignals(Object.fromEntries(names.map((name, index) => [name === "triglyceride" ? "triglyceride" : name, intensities[index]])));
    liverRenderer.setZoneValues(zoneIntensities);
    renderSimulationAnalysis(result, frame, displayMode, zoneMetric.value, trendMetric.value, zone);
    renderExplainability(result, frame, displayMode, explainabilityMetric.value, zone);
    const domainCheck = result.mechanistic_simulation.surrogate_domain_check;
    const domainNotice = domainCheck?.status === "outside_synthetic_training_range"
      ? " Some internal features exceed synthetic training ranges; treat this run as extrapolation."
      : "";
    document.querySelector("#liver-model-message").textContent = `Selected-zone values and trajectory use that zone’s baseline/scenario histories. Color and hotspot intensity are smoothed, run-normalized synthetic proxies; they do not encode clinical severity or geometry changes.${domainNotice}`;
  }

  function togglePlayback() {
    if (playbackTimer) {
      clearInterval(playbackTimer); playbackTimer = null;
      playButton.textContent = "▶ Play"; playButton.setAttribute("aria-pressed", "false"); return;
    }
    if (Number(timeInput.value) >= Number(timeInput.max)) timeInput.value = "0";
    playButton.textContent = "Ⅱ Pause"; playButton.setAttribute("aria-pressed", "true");
    playbackTimer = setInterval(() => {
      const next = Number(timeInput.value) + 1;
      if (next > Number(timeInput.max)) { togglePlayback(); return; }
      timeInput.value = String(next); updateLiverFrame();
    }, 130);
  }

  document.addEventListener("visibilitychange", () => { if (document.hidden && playbackTimer) togglePlayback(); });

  function render(result) {
    const data = readInput(), summary = result.marker_summary, sim = result.mechanistic_simulation;
    document.querySelector("#bmi-value").textContent = Number.isFinite(summary.bmi_kg_m2) ? summary.bmi_kg_m2.toFixed(1) : "—";
    document.querySelector("#bmi-band").textContent = summary.indian_bmi_band_from_blueprint || "Height + weight needed";
    document.querySelector("#fib4-value").textContent = Number.isFinite(summary.fib4_arithmetic_only) ? summary.fib4_arithmetic_only.toFixed(2) : "—";
    document.querySelector("#scenario-count").textContent = String(sim.active_perturbations.length);
    renderCriteria(summary);
    renderComparison(result.scenario_vs_unmodified_toy_baseline.zonal_state_deltas);
    renderOxygen(sim.oxygen_pde_profile_mmhg);
    document.querySelector("#model-version").textContent = `${sim.model_name} · v${sim.model_version}`;
    document.querySelector("#model-training-note").textContent = result.physics_informed_ml.surrogate_training.training_data;
    document.querySelector("#genetics-note").textContent = "";
    renderAssumptions(sim.assumptions_changed);
    renderSensitivity(result.parameter_sensitivity);
    if (data.pnpla3_genotype || data.tm6sf2_genotype) {
      document.querySelector("#genetics-note").textContent = "Genotype values were processed by the local model in memory and are not echoed or stored.";
    }
    document.querySelector("#trajectory-chart").dataset.result = JSON.stringify(result);
  }

  function renderAssumptions(changes) {
    const list = document.querySelector("#assumption-list"); list.replaceChildren();
    if (!changes.length) {
      const row = document.createElement("p"); row.className = "footnote";
      row.textContent = "No parameter perturbations selected; all displayed factors equal the synthetic baseline.";
      list.append(row); return;
    }
    for (const item of changes) {
      const row = document.createElement("div"); row.className = "comparison-row";
      const name = document.createElement("span"); name.textContent = item.parameter.replaceAll("_", " ");
      const values = document.createElement("strong"); values.textContent = `${item.baseline_factor.toFixed(2)} → ${item.scenario_factor.toFixed(2)} ×`;
      const source = document.createElement("em"); source.textContent = "synthetic assumption";
      row.append(name, values, source); list.append(row);
    }
  }

  function renderSensitivity(summary) {
    const list = document.querySelector("#sensitivity-list"); list.replaceChildren();
    document.querySelector("#sensitivity-note").textContent = summary.meaning;
    for (const item of summary.results) {
      const row = document.createElement("div"); row.className = "comparison-row";
      const name = document.createElement("span"); name.textContent = `${item.parameter.replaceAll("_", " ")} (${item.range[0]}–${item.range[1]})`;
      const values = document.createElement("strong");
      values.textContent = Object.entries(item.final_state_range).map(([key, range]) => `${key}: ${range[0]}–${range[1]}`).join(" · ");
      row.append(name, values); list.append(row);
    }
  }

  function downloadResults(format) {
    const result = store.getState().result;
    if (!result) return;
    const payload = { marker_summary: result.marker_summary, model: result.mechanistic_simulation,
      baseline_vs_scenario: result.scenario_vs_unmodified_toy_baseline,
      parameter_sensitivity: result.parameter_sensitivity, limitations: result.mechanistic_simulation.limitations };
    const json = JSON.stringify(payload, null, 2);
    const rows = [["section", "name", "value"]];
    const flatten = (section, value, name = "") => {
      if (Array.isArray(value)) value.forEach((item, index) => flatten(section, item, `${name}[${index}]`));
      else if (value && typeof value === "object") Object.entries(value).forEach(([key, item]) => flatten(section, item, name ? `${name}.${key}` : key));
      else rows.push([section, name, value]);
    };
    Object.entries(payload).forEach(([section, value]) => flatten(section, value));
    const csv = rows.map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(",")).join("\r\n");
    const download = (content, type, suffix) => {
      const url = URL.createObjectURL(new Blob([content], { type }));
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = `masld-synthetic-run.${suffix}`;
      anchor.click(); URL.revokeObjectURL(url);
    };
    if (format === "csv") download(csv, "text/csv", "csv");
    else download(json, "application/json", "json");
  }

  function renderCriteria(summary) {
    const list = document.querySelector("#criteria-list"); list.replaceChildren();
    const flags = summary.criterion_matches || [];
    if (!flags.length) {
      const empty = document.createElement("p"); empty.className = "footnote";
      empty.textContent = "Add CAP, LSM, BIA, or platelet values to see independent criterion flags."; list.append(empty);
    }
    for (const flag of flags) {
      const item = document.createElement("div"); item.className = "criterion";
      const text = document.createElement("span"); text.textContent = flag.criterion;
      const state = document.createElement("b"); state.className = flag.observed ? "match" : ""; state.textContent = flag.observed ? "MATCH" : "—";
      item.append(text, state); list.append(item);
    }
    const observations = summary.observations || [];
    document.querySelector("#marker-note").textContent = observations.length
      ? observations.join(" ") + " Clinical stage remains intentionally unassigned."
      : "Blueprint flags are unvalidated and are not a diagnosis or a rule-out.";
  }

  function renderComparison(zones) {
    const list = document.querySelector("#comparison-list"); list.replaceChildren();
    for (const name of Object.keys(titles)) {
      const values = zones.map((zone) => zone[name]);
      const base = values.reduce((sum, point) => sum + point.baseline, 0) / values.length;
      const scenario = values.reduce((sum, point) => sum + point.scenario, 0) / values.length;
      const delta = base === 0 ? null : 100 * (scenario - base) / base;
      const row = document.createElement("div"); row.className = "comparison-row";
      const label = document.createElement("span"); label.textContent = titles[name];
      const amounts = document.createElement("strong"); amounts.textContent = `${base.toFixed(3)} → ${scenario.toFixed(3)}`;
      const change = document.createElement("em"); change.textContent = delta === null ? "n/a" : `${delta > 0 ? "+" : ""}${delta.toFixed(1)}%`;
      row.append(label, amounts, change); list.append(row);
    }
  }

  function renderOxygen(values) {
    const strip = document.querySelector("#oxygen-strip"); strip.replaceChildren();
    values.forEach((value, index) => {
      const cell = document.createElement("div"); cell.className = "oxygen-cell";
      cell.setAttribute("title", `Position ${index + 1}: ${value.toFixed(1)} mmHg`);
      if (index % 5 === 0 || index === values.length - 1) cell.textContent = value.toFixed(0);
      strip.append(cell);
    });
  }



  window.addEventListener("resize", () => {
    // Existing result is already on screen; resize chart without resubmitting data.
    const canvas = document.querySelector("#trajectory-chart");
    if (!document.querySelector("#result-content").hidden && canvas.dataset.result) drawChartResult(JSON.parse(canvas.dataset.result));
    resizeAnalysisChart();
    resizeExplainabilityChart();
  });
})();
