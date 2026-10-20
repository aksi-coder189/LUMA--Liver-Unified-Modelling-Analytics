const metrics = [
  { key: "triglyceride", short: "TG", title: "Triglyceride proxy", color: "#58856d" },
  { key: "ros", short: "ROS", title: "Oxidative proxy", color: "#d78b70" },
  { key: "ecm", short: "ECM", title: "Matrix proxy", color: "#739eac" },
];
const safe = (value) => Number.isFinite(Number(value)) ? Number(value) : 0;
const fmt = (value) => safe(value).toFixed(3);

/** Render descriptive, run-relative summaries from the synthetic API response. */
export function renderSimulationAnalysis(result, frame = 0, displayMode = "scenario", zoneMetric = "triglyceride", trendMetric = "triglyceride", selectedZone = -1) {
  const root = document.querySelector("#analysis-dashboard");
  if (!root || !result?.scenario_vs_unmodified_toy_baseline || !result?.mechanistic_simulation) return;
  root.hidden = false;
  const comparison = result.scenario_vs_unmodified_toy_baseline;
  const baselineMean = comparison.baseline_mean_trajectory || [];
  const scenarioMean = comparison.scenario_mean_trajectory || [];
  const zones = result.mechanistic_simulation.zonal_trajectories || [];
  const baselineZones = comparison.baseline_zonal_trajectories || [];
  const zone = Number.isInteger(selectedZone) && selectedZone >= 0 ? selectedZone : -1;
  const baseline = zone >= 0 ? baselineZones[zone]?.trajectory || baselineMean : baselineMean;
  const scenario = zone >= 0 ? zones[zone]?.trajectory || scenarioMean : scenarioMean;
  const title = document.querySelector("#analysis-trend-title");
  if (title) title.textContent = zone === 0 ? "Zone 1 · periportal trajectory" : zone === 4 ? "Zone 5 · perivenous trajectory" : zone >= 0 ? `Zone ${zone + 1} trajectory` : "Whole-liver mean trajectory";
  const canvas = document.querySelector("#analysis-trend");
  if (canvas) canvas.setAttribute("aria-label", `Synthetic ${zone >= 0 ? `zone ${zone + 1}` : "whole-liver mean"} proxy over model time, baseline and selected scenario`);
  if (canvas) canvas.dataset.payload = JSON.stringify({ baseline, scenario, metric: trendMetric });
  const sim = result.mechanistic_simulation;
  const last = Math.max(0, Math.min(Number(frame) || 0, Math.min(baseline.length, scenario.length) - 1));
  const baselineState = baseline[last] || {};
  const scenarioState = scenario[last] || {};
  const modeState = displayMode === "baseline" ? baselineState : displayMode === "difference"
    ? Object.fromEntries(metrics.map(({ key }) => [key, Math.abs(safe(scenarioState[key]) - safe(baselineState[key]))])) : scenarioState;

  drawTrend(document.querySelector("#analysis-trend"), baseline, scenario, trendMetric);
  const bio = document.querySelector("#analysis-biomarkers");
  bio.replaceChildren();
  for (const metric of metrics) {
    const all = [...baseline, ...scenario].map((point) => safe(point[metric.key]));
    const min = Math.min(...all), max = Math.max(...all);
    const current = safe(modeState[metric.key]);
    const relative = displayMode === "difference"
      ? current / Math.max(1e-9, ...baseline.map((v, i) => Math.abs(safe(scenario[i]?.[metric.key]) - safe(v[metric.key]))))
      : (current - min) / Math.max(1e-9, max - min);
    const card = document.createElement("div"); card.className = "analysis-biomarker";
    card.style.setProperty("--signal", metric.color);
    const header = document.createElement("div"); header.className = "analysis-biomarker-head";
    const title = document.createElement("strong"); title.textContent = metric.title;
    const value = document.createElement("b"); value.textContent = fmt(current);
    header.append(title, value);
    const track = document.createElement("div"); track.className = "analysis-track"; track.setAttribute("role", "meter");
    track.setAttribute("aria-label", `${metric.title}, run-relative proxy`); track.setAttribute("aria-valuemin", "0"); track.setAttribute("aria-valuemax", "100");
    track.setAttribute("aria-valuenow", String(Math.round(Math.max(0, Math.min(1, relative)) * 100)));
    const fill = document.createElement("span"); fill.style.width = `${Math.max(0, Math.min(1, relative)) * 100}%`; track.append(fill);
    const detail = document.createElement("small"); detail.textContent = `Baseline ${fmt(baselineState[metric.key])}  ·  Scenario ${fmt(scenarioState[metric.key])}`;
    card.append(header, track, detail); bio.append(card);
  }
  renderZones(zones, baselineZones, last, zoneMetric);
  renderInsights(baselineMean, scenarioMean, zones, baselineZones, last, zoneMetric);
}

function drawTrend(canvas, baseline, scenario, key) {
  if (!canvas || !baseline.length || !scenario.length) return;
  const box = canvas.getBoundingClientRect(); if (!box.width || !box.height) return;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(box.width * ratio); canvas.height = Math.round(box.height * ratio);
  const ctx = canvas.getContext("2d"); ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  const w = box.width, h = box.height, p = { l: 42, r: 10, t: 12, b: 26 }, pw = w - p.l - p.r, ph = h - p.t - p.b;
  const max = Math.max(0.001, ...baseline.map((v) => safe(v[key])), ...scenario.map((v) => safe(v[key]))) * 1.08;
  ctx.clearRect(0, 0, w, h); ctx.font = "9px monospace"; ctx.fillStyle = "#78877f"; ctx.strokeStyle = "#e3e9e1"; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) { const y = p.t + ph * i / 4; ctx.beginPath(); ctx.moveTo(p.l, y); ctx.lineTo(w - p.r, y); ctx.stroke(); ctx.fillText((max * (1 - i / 4)).toFixed(2), 2, y + 3); }
  for (const [series, color, dash] of [[baseline, "#9aada2", [5, 4]], [scenario, "#205c50", []]]) {
    ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.setLineDash(dash);
    series.forEach((point, i) => { const x = p.l + pw * i / Math.max(1, series.length - 1), y = p.t + ph * (1 - safe(point[key]) / max); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke();
  }
  ctx.setLineDash([]); ctx.fillStyle = "#78877f"; ctx.fillText("0", p.l, h - 7); ctx.fillText("Model steps · arbitrary", Math.max(p.l + 6, w - 145), h - 7);
}

function renderZones(zones, baselineZones, frame, metricKey) {
  const root = document.querySelector("#analysis-zones"); root.replaceChildren();
  const metric = metrics.find((item) => item.key === metricKey) || metrics[0];
  const values = zones.flatMap((zone, index) => [safe(baselineZones[index]?.trajectory?.[frame]?.[metric.key]), safe(zone.trajectory?.[frame]?.[metric.key])]);
  const max = Math.max(1e-9, ...values);
  zones.forEach((zone, index) => {
    const row = document.createElement("div"); row.className = "zone-bar-group";
    const label = document.createElement("span"); label.textContent = `Z${index + 1}`;
    const pair = document.createElement("div"); pair.className = "zone-bars";
    for (const [name, value, color] of [["Baseline", values[index * 2], "#9aada2"], ["Scenario", values[index * 2 + 1], "#205c50"]]) {
      const bar = document.createElement("i"); bar.style.height = `${Math.max(3, value / max * 100)}%`; bar.style.background = color; bar.title = `${name}: ${fmt(value)} arbitrary units`;
      bar.setAttribute("aria-label", `${name}: ${fmt(value)} arbitrary units`); pair.append(bar);
    }
    row.append(label, pair); root.append(row);
  });
  root.setAttribute("aria-label", `${metric.title} by liver zone at selected step; run-relative arbitrary units`);
}

function renderInsights(baseline, scenario, zones, baselineZones, frame, metricKey) {
  const list = document.querySelector("#analysis-insights"); list.replaceChildren();
  const end = Math.min(baseline.length, scenario.length) - 1;
  if (end < 0) return;
  const deltaText = metrics.map(({ key, short }) => {
    const base = safe(baseline[end]?.[key]), scenarioValue = safe(scenario[end]?.[key]);
    const rawDelta = base ? (scenarioValue - base) / Math.abs(base) * 100 : 0;
    const delta = Math.abs(rawDelta) < 0.05 ? 0 : rawDelta;
    return `${short} ${delta > 0 ? "+" : ""}${delta.toFixed(1)}%`;
  }).join(" · ");
  const metric = metrics.find((item) => item.key === metricKey) || metrics[0];
  const largest = zones.map((zone, index) => ({ index, amount: Math.abs(safe(zone.trajectory?.[frame]?.[metric.key]) - safe(baselineZones[index]?.trajectory?.[frame]?.[metric.key])) }))
    .sort((a, b) => b.amount - a.amount)[0];
  const points = [
    `Final step vs mathematical toy baseline: ${deltaText}.`,
    largest ? `Largest absolute ${metric.short} difference at selected step: Zone ${largest.index + 1} (${largest.amount.toFixed(3)} arbitrary units).` : "Zone-level comparison is unavailable for this run.",
    `${baseline.length} time points · ${zones.length} zones · current step ${frame}.`,
  ];
  points.forEach((text) => { const item = document.createElement("li"); item.textContent = text; list.append(item); });
}

export function resizeAnalysisChart() {
  const canvas = document.querySelector("#analysis-trend");
  if (!canvas || document.querySelector("#analysis-dashboard").hidden || !canvas.dataset.payload) return;
  const { baseline, scenario, metric } = JSON.parse(canvas.dataset.payload); drawTrend(canvas, baseline, scenario, metric || "triglyceride");
}

