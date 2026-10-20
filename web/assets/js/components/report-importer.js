const fields = [
  { name: "age_years", aliases: ["age", "age years", "patient age"] },
  { name: "height_m", aliases: ["height", "height m", "height cm", "stature"] },
  { name: "weight_kg", aliases: ["weight", "weight kg", "body weight"] },
  { name: "alt_u_l", aliases: ["alt", "sgpt", "alanine aminotransferase", "alanine transaminase"] },
  { name: "ast_u_l", aliases: ["ast", "sgot", "aspartate aminotransferase", "aspartate transaminase"] },
  { name: "platelets_10e9_l", aliases: ["platelets", "platelet count", "platelet count 10^9/l", "platelet count x10^9/l"] },
  { name: "cap_db_m", aliases: ["cap", "controlled attenuation parameter"] },
  { name: "lsm_kpa", aliases: ["lsm", "liver stiffness", "liver stiffness measurement", "stiffness kpa"] },
  { name: "bia_phase_angle_deg", aliases: ["bia phase angle", "phase angle", "phase angle degrees"] },
  { name: "hscrp_mg_l", aliases: ["hscrp", "hs-crp", "high sensitivity crp", "high-sensitivity crp", "c reactive protein high sensitivity"] },
  { name: "ferritin_ug_l", aliases: ["ferritin", "ferritin ug/l", "ferritin ng/ml"] },
  { name: "fasting_glucose_mmol_l", aliases: ["fasting glucose", "glucose fasting", "fasting blood glucose", "fpg"] }
];

const normalize = (value) => String(value).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const numberPattern = /(?:^|[:=,\t]\s*|\s)(-?\d+(?:,\d{3})*(?:\.\d+)?)(?=\s|$|[,;])/;

function convert(value, field, line) {
  const unit = line.toLowerCase().replace(/μ/g, "µ");
  if (field === "height_m" && /\bcm\b/.test(unit)) value /= 100;
  if (field === "fasting_glucose_mmol_l" && /mg\s*\/\s*dl/.test(unit)) value /= 18.0182;
  if (field === "hscrp_mg_l" && /mg\s*\/\s*dl/.test(unit)) value *= 10;
  // ng/mL and µg/L are numerically equivalent for ferritin.
  return value;
}

function findField(line) {
  const text = normalize(line);
  return fields.find((field) => field.aliases.some((alias) => {
    const candidate = normalize(alias);
    return text === candidate || text.startsWith(`${candidate} `) || text.includes(` ${candidate} `) || text.endsWith(` ${candidate}`);
  }));
}

function jsonLines(value, path = "") {
  if (Array.isArray(value)) return value.flatMap((item, i) => jsonLines(item, `${path} ${i}`));
  if (value && typeof value === "object") return Object.entries(value).flatMap(([key, item]) => jsonLines(item, `${path} ${key}`));
  return path && (typeof value === "number" || typeof value === "string") ? [`${path}: ${value}`] : [];
}

export async function extractReport(file) {
  if (!file) throw new Error("Choose a report file first.");
  if (file.size > 2 * 1024 * 1024) throw new Error("Report files must be 2 MB or smaller.");
  const extension = file.name.split(".").pop().toLowerCase();
  if (!["txt", "csv", "json"].includes(extension)) throw new Error("Use a text, CSV, or JSON report. Scanned PDFs need OCR and are not supported.");
  const source = await file.text();
  if (source.includes("\0")) throw new Error("This file does not look like a readable text report.");
  let lines;
  if (extension === "json") {
    let parsed;
    try { parsed = JSON.parse(source); } catch { throw new Error("The JSON report is malformed."); }
    lines = jsonLines(parsed);
  } else {
    lines = source.split(/\r?\n/).map((line) => line.replace(/["']/g, "").trim()).filter(Boolean);
  }

  const extracted = new Map();
  for (const line of lines) {
    const field = findField(line);
    if (!field || extracted.has(field.name)) continue;
    const match = line.match(numberPattern);
    if (!match) continue;
    const value = convert(Number(match[1].replaceAll(",", "")), field.name, line);
    if (Number.isFinite(value)) extracted.set(field.name, { value, source: line.slice(0, 180) });
  }
  return [...extracted.entries()].map(([name, item]) => ({ name, ...item }));
}
