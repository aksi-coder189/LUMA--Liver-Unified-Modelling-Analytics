const COLORS = ["#205c50", "#d8755d", "#739eac", "#d0a142", "#8675ad", "#82938a"];
const METRICS = {
  triglyceride: { label: "TG proxy", unit: "arbitrary state units" },
  ros: { label: "ROS proxy", unit: "arbitrary state units" },
  ecm: { label: "ECM proxy", unit: "arbitrary state units" },
};
const safe = (value) => Number.isFinite(Number(value)) ? Number(value) : 0;
const fmt = (value) => `${safe(value) > 0 ? "+" : ""}${safe(value).toFixed(4)}`;

/** Show term-level explanations emitted by the same synthetic simulation response. */
export function renderExplainability(result, frame = 0, displayMode = "scenario", metricKey = "triglyceride", selectedZone = -1) {
  const root = document.querySelector("#explainability-dashboard");
  const simExplainability = result?.mechanistic_simulation?.explainability;
  const baselineExplainability = result?.scenario_vs_unmodified_toy_baseline?.baseline_explainability;
  if (!root || !simExplainability || !baselineExplainability) return;
  root.hidden = false;

  const metric = METRICS[metricKey] ? metricKey : "triglyceride";
  const mode = ["baseline", "difference"].includes(displayMode) ? displayMode : "scenario";
  const base = explanationSeries(baselineExplainability, metric, selectedZone);
  const scenario = explanationSeries(simExplainability, metric, selectedZone);
  const count = Math.min(base.length, scenario.length);
  if (!count) return;

  const featureLabels = simExplainability.feature_labels || {};
  const points = Array.from({ length: count }, (_, index) => {
    const baselinePoint = base[index];
    const scenarioPoint = scenario[index];
    const baselineTerms = baselinePoint.cumulative_contributions || {};
    const scenarioTerms = scenarioPoint.cumulative_contributions || {};
    const keys = [...new Set([...Object.keys(baselineTerms), ...Object.keys(scenarioTerms)])];
    const terms = Object.fromEntries(keys.map((key) => [key,
      mode === "baseline" ? safe(baselineTerms[key])
        : mode === "difference" ? safe(scenarioTerms[key]) - safe(baselineTerms[key])
          : safe(scenarioTerms[key]),
    ]));
    const net = mode === "baseline" ? safe(baselinePoint.net_state_change)
      : mode === "difference" ? safe(scenarioPoint.net_state_change) - safe(baselinePoint.net_state_change)
        : safe(scenarioPoint.net_state_change);
    const clamp = mode === "baseline" ? safe(baselinePoint.clipping_adjustment)
      : mode === "difference" ? safe(scenarioPoint.clipping_adjustment) - safe(baselinePoint.clipping_adjustment)
        : safe(scenarioPoint.clipping_adjustment);
    return { step: scenarioPoint.step, time: scenarioPoint.time, terms, net, clamp };
  });

  const currentIndex = Math.min(Math.max(0, Number(frame) || 0), count - 1);
  const current = points[currentIndex];
  const ranked = Object.keys(current.terms)
    .map((key) => ({ key, amount: current.terms[key] }))
    .sort((a, b) => Math.abs(b.amount) - Math.abs(a.amount));
  const topKeys = ranked.slice(0, 5).map(({ key }) => key);
  const series = topKeys.map((key, index) => ({
    key,
    label: featureLabels[key] || key.replaceAll("_", " "),
    color: COLORS[index],
    values: points.map((point) => point.terms[key] || 0),
  }));
  const otherKeys = Object.keys(current.terms).filter((key) => !topKeys.includes(key));
  if (otherKeys.length) {
    series.push({
      key: "other",
      label: "Other surrogate terms",
      color: COLORS[5],
      values: points.map((point) => otherKeys.reduce((sum, key) => sum + safe(point.terms[key]), 0)),
    });
  }

  const canvas = document.querySelector("#explainability-chart");
  if (canvas) {
    canvas.dataset.payload = JSON.stringify({ points, series, metric, mode, currentIndex });
    drawContributionChart(canvas, points, series, metric, currentIndex);
  }
  const legend = document.querySelector("#explainability-legend");
  legend.replaceChildren();
  for (const item of series) {
    const entry = document.createElement("span");
    const swatch = document.createElement("i"); swatch.style.background = item.color;
    const label = document.createElement("span"); label.textContent = item.label;
    entry.append(swatch, label); legend.append(entry);
  }

  const label = METRICS[metric].label;
  const modeLabel = mode === "difference" ? "Scenario minus baseline" : mode === "baseline" ? "Baseline" : "Selected scenario";
  const title = document.querySelector("#explainability-title");
  const areaLabel = selectedZone >= 0 ? `Zone ${selectedZone + 1}` : "Whole-liver mean";
  title.textContent = `${label} · ${modeLabel} · ${areaLabel}`;
  const table = document.querySelector("#explainability-terms");
  table.replaceChildren();
  for (const item of ranked.slice(0, 6)) {
    const row = document.createElement("div"); row.className = "explanation-term";
    const name = document.createElement("span"); name.textContent = featureLabels[item.key] || item.key.replaceAll("_", " ");
    const value = document.createElement("strong"); value.textContent = fmt(item.amount);
    const direction = document.createElement("small"); direction.textContent = item.amount > 0 ? "adds to change" : item.amount < 0 ? "subtracts from change" : "no net contribution";
    row.append(name, value, direction); table.append(row);
  }

  const termSum = Object.values(current.terms).reduce((sum, value) => sum + safe(value), 0);
  const reconstructed = termSum + current.clamp;
  const error = reconstructed - current.net;
  const tolerance = 1e-7;
  const reconciliation = document.querySelector("#explainability-reconciliation");
  reconciliation.textContent = `At model step ${current.step}: net ${fmt(current.net)} = feature terms ${fmt(termSum)} + non-negative clamp ${fmt(current.clamp)}. ${Math.abs(error) <= tolerance ? "Reconciles within numerical tolerance." : `Residual ${fmt(error)}.`}`;
  reconciliation.classList.toggle("is-reconciled", Math.abs(error) <= tolerance);
  reconciliation.classList.toggle("is-unreconciled", Math.abs(error) > tolerance);

  const dominant = ranked[0];
  document.querySelector("#explainability-dominant").textContent = !dominant
    ? "No contribution terms are available for this point."
    : Math.abs(dominant.amount) < 1e-10
      ? "No cumulative contribution has accrued at the initial time point."
      : `Largest absolute term at this step: ${featureLabels[dominant.key] || dominant.key.replaceAll("_", " ")} (${fmt(dominant.amount)}).`;
}

function explanationSeries(explainability, metric, zone) {
  const trajectory = Number.isInteger(zone) && zone >= 0
    ? explainability.zones?.[zone]?.trajectories?.[metric]
    : explainability.mean_trajectory?.[metric];
  return Array.isArray(trajectory) ? trajectory : [];
}

function drawContributionChart(canvas, points, series, metric, currentIndex) {
  const box = canvas.getBoundingClientRect();
  if (!box.width || !box.height || !points.length) return;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(box.width * ratio); canvas.height = Math.round(box.height * ratio);
  const ctx = canvas.getContext("2d"); ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  const width = box.width, height = box.height, pad = { left: 55, right: 14, top: 16, bottom: 30 };
  const plotWidth = width - pad.left - pad.right, plotHeight = height - pad.top - pad.bottom;
  const allValues = series.flatMap((item) => item.values);
  const magnitude = Math.max(1e-6, ...allValues.map((value) => Math.abs(safe(value)))) * 1.12;
  ctx.clearRect(0, 0, width, height); ctx.font = "9px monospace"; ctx.fillStyle = "#78877f";
  for (let index = 0; index <= 4; index += 1) {
    const fraction = index / 4, value = magnitude - 2 * magnitude * fraction;
    const y = pad.top + plotHeight * fraction;
    ctx.beginPath(); ctx.strokeStyle = Math.abs(value) < magnitude / 100 ? "#a9b8ad" : "#e3e9e1";
    ctx.lineWidth = Math.abs(value) < magnitude / 100 ? 1.4 : 1; ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
    ctx.fillText(value.toFixed(3), 2, y + 3);
  }
  for (const item of series) {
    ctx.beginPath(); ctx.strokeStyle = item.color; ctx.lineWidth = 1.7;
    item.values.forEach((value, index) => {
      const x = pad.left + plotWidth * index / Math.max(1, points.length - 1);
      const y = pad.top + plotHeight * (magnitude - safe(value)) / (2 * magnitude);
      index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.stroke();
  }
  const markerX = pad.left + plotWidth * currentIndex / Math.max(1, points.length - 1);
  ctx.beginPath(); ctx.strokeStyle = "#344b42"; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
  ctx.moveTo(markerX, pad.top); ctx.lineTo(markerX, pad.top + plotHeight); ctx.stroke(); ctx.setLineDash([]);
  ctx.fillStyle = "#78877f"; ctx.fillText("0", pad.left, height - 8);
  ctx.fillText(`Model step ${points.at(-1).step} · arbitrary`, Math.max(pad.left + 5, width - 190), height - 8);
  canvas.setAttribute("aria-label", `Cumulative synthetic surrogate feature contributions to ${METRICS[metric].label}, positive and negative, over model time. Vertical marker shows the selected time step.`);
}

export function resizeExplainabilityChart() {
  const canvas = document.querySelector("#explainability-chart");
  if (!canvas?.dataset.payload || document.querySelector("#explainability-dashboard")?.hidden) return;
  const { points, series, metric, currentIndex } = JSON.parse(canvas.dataset.payload);
  drawContributionChart(canvas, points, series, metric, currentIndex);
}
