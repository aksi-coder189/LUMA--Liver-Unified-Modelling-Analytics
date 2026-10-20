const palette = { triglyceride: "#58856d", ros: "#d78b70", ecm: "#739eac" };
const labels = { triglyceride: "TG", ros: "ROS", ecm: "ECM" };

export function drawComparisonChart(baseline, selected, duration) {
  const canvas = document.querySelector("#trajectory-chart"), rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height || !Array.isArray(baseline) || !Array.isArray(selected)) return;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * dpr); canvas.height = Math.round(rect.height * dpr);
  const context = canvas.getContext("2d"); context.scale(dpr, dpr);
  const width = rect.width, height = rect.height, pad = { left: 48, right: 14, top: 14, bottom: 30 };
  const plotW = width - pad.left - pad.right, plotH = height - pad.top - pad.bottom;
  const names = Object.keys(palette);
  const max = Math.max(...[...baseline, ...selected].flatMap((point) => names.map((name) => point[name] || 0)), 0.001);
  context.clearRect(0, 0, width, height); context.font = "10px monospace";
  context.fillStyle = "#78857d"; context.strokeStyle = "#e9eee8";
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + plotH * i / 4, value = max * (1 - i / 4);
    context.beginPath(); context.moveTo(pad.left, y); context.lineTo(width - pad.right, y); context.stroke();
    context.fillText(value.toFixed(2), 2, y + 3);
  }
  context.fillText("0", pad.left, height - 8);
  context.fillText(`${Number(duration).toFixed(0)} arbitrary time`, width - 116, height - 8);
  for (const name of names) {
    for (const [series, dashed] of [[selected, false], [baseline, true]]) {
      context.beginPath(); context.strokeStyle = palette[name]; context.lineWidth = dashed ? 1.5 : 2;
      context.setLineDash(dashed ? [4, 3] : []);
      series.forEach((point, index) => {
        const x = pad.left + plotW * index / (series.length - 1);
        const y = pad.top + plotH * (1 - (point[name] || 0) / max);
        if (!index) context.moveTo(x, y); else context.lineTo(x, y);
      });
      context.stroke();
    }
  }
  context.setLineDash([]);
}
