"use strict";

/* Browser implementation of the rank-based calculations in refint/core.py.
   All sample data stays on this device; no network service is used. */
const Z_BY_CI = { "0.8": 1.2816, "0.9": 1.6449, "0.95": 1.96, "0.99": 2.5758 };
const MIN_N = 120;
const MAX_FILE_BYTES = 5 * 1024 * 1024;
const MAX_ROWS = 50000;

function finiteValues(values, label = "values") {
  if (!Array.isArray(values) || !values.length ||
      values.some(x => typeof x !== "number" || !Number.isFinite(x))) {
    throw new Error(label + " must contain finite numeric observations.");
  }
  return values;
}
function quantile(sorted, p) {
  const rank = (sorted.length - 1) * p;
  const lo = Math.floor(rank), hi = Math.ceil(rank);
  return sorted[lo] + (rank - lo) * (sorted[hi] - sorted[lo]);
}
function rankValue(sorted, rank) {
  if (rank <= 1) return sorted[0];
  if (rank >= sorted.length) return sorted[sorted.length - 1];
  const lo = Math.floor(rank), hi = Math.ceil(rank);
  return sorted[lo - 1] + (rank - lo) * (sorted[hi - 1] - sorted[lo - 1]);
}
function roundHalfEven(value) {
  const base = Math.floor(value);
  const frac = value - base;
  if (frac < 0.5) return base;
  if (frac > 0.5) return base + 1;
  return base % 2 === 0 ? base : base + 1;
}
function ciRanks(n, p, z) {
  const se = Math.sqrt(n * p * (1 - p));
  const lo = Math.max(1, roundHalfEven(n * p - z * se));
  const hi = Math.min(n, roundHalfEven(n * p + z * se) + 1);
  return [lo, Math.max(lo, hi)];
}
function interval(values, label = "overall", ci = 0.9, excludeOutliers = true) {
  finiteValues(values, label);
  if (values.length < 2) throw new Error(label + ": at least 2 observations required.");
  if (!Object.hasOwn(Z_BY_CI, String(ci))) throw new Error("Unsupported CI level.");
  const original = [...values].sort((a, b) => a - b);
  const q1 = quantile(original, 0.25), q3 = quantile(original, 0.75);
  const iqr = q3 - q1;
  const lowFence = q1 - 1.5 * iqr, highFence = q3 + 1.5 * iqr;
  const used = excludeOutliers ? original.filter(x => x >= lowFence && x <= highFence) : original;
  const outliers = excludeOutliers ? original.filter(x => x < lowFence || x > highFence) : [];
  if (used.length < 2) throw new Error(label + ": fewer than 2 observations remain after exclusion.");
  const n = used.length, z = Z_BY_CI[String(ci)];
  const lowerRanks = ciRanks(n, 0.025, z), upperRanks = ciRanks(n, 0.975, z);
  return {
    label, nTotal: original.length, nUsed: n, nOutliers: outliers.length, outliers,
    lower: rankValue(used, 0.025 * (n + 1)),
    upper: rankValue(used, 0.975 * (n + 1)),
    lowerCI: lowerRanks.map(r => used[r - 1]),
    upperCI: upperRanks.map(r => used[r - 1]),
    ci, belowMin: n < MIN_N,
  };
}
function sampleVariance(values) {
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  return values.reduce((a, b) => a + (b - mean) ** 2, 0) / (values.length - 1);
}
function harrisBoyd(a, b, labelA, labelB) {
  finiteValues(a, labelA); finiteValues(b, labelB);
  if (a.length < 2 || b.length < 2) throw new Error("Partition groups need at least 2 observations.");
  const meanA = a.reduce((x, y) => x + y, 0) / a.length;
  const meanB = b.reduce((x, y) => x + y, 0) / b.length;
  const se = Math.sqrt(sampleVariance(a) / a.length + sampleVariance(b) / b.length);
  const z = se > 0 ? Math.abs(meanA - meanB) / se : (meanA === meanB ? 0 : Infinity);
  const nStar = Math.min(a.length, b.length);
  let critical = 3.10;
  for (const [n, threshold] of [[25,2.5],[50,2.6],[75,2.7],[100,2.8],[150,2.9],[200,3.0]]) {
    if (nStar <= n) { critical = threshold; break; }
  }
  return { labelA, labelB, nStar, z, critical, partition: z > critical };
}
function analyze(groups, ci = 0.9, excludeOutliers = true) {
  const entries = Object.entries(groups);
  if (!entries.length) throw new Error("No usable observations found.");
  const all = entries.flatMap(([, values]) => values);
  const overall = interval(all, "overall", ci, excludeOutliers);
  const subgroups = entries.map(([name, values]) => interval(values, name, ci, excludeOutliers));
  const pairs = [];
  for (let i = 0; i < entries.length; i++) {
    for (let j = i + 1; j < entries.length; j++) {
      pairs.push(harrisBoyd(entries[i][1], entries[j][1], entries[i][0], entries[j][0]));
    }
  }
  return { overall, subgroups, pairs };
}
function parseCSV(input) {
  if (typeof input !== "string" || input.length > MAX_FILE_BYTES) throw new Error("CSV is too large.");
  const text = input.replace(/^\uFEFF/, "");
  const rows = [];
  let row = [], field = "", quoted = false, atEndQuote = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else { quoted = false; atEndQuote = true; }
      } else field += ch;
    } else if (ch === '"' && field === "" && !atEndQuote) quoted = true;
    else if (ch === ",") { row.push(field); field = ""; atEndQuote = false; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      if (row.some(v => v.trim() !== "")) rows.push(row);
      row = []; field = ""; atEndQuote = false;
      if (rows.length > MAX_ROWS + 1) throw new Error("CSV has too many rows.");
    } else if (atEndQuote && ch !== " " && ch !== "\t") {
      throw new Error("Malformed quoted CSV field.");
    } else if (!atEndQuote) field += ch;
  }
  if (quoted) throw new Error("Unterminated CSV quoted field.");
  row.push(field);
  if (row.some(v => v.trim() !== "")) rows.push(row);
  const headers = rows.shift()?.map(x => x.trim());
  if (!headers?.length || headers.some(x => !x) || new Set(headers).size !== headers.length) {
    throw new Error("CSV requires unique, nonempty column headings.");
  }
  if (rows.some(r => r.length !== headers.length)) throw new Error("Inconsistent CSV column count.");
  if (rows.length > MAX_ROWS) throw new Error("CSV has too many rows.");
  return { headers, rows };
}
function valuesFromCSV(table, valueColumn, groupColumn) {
  const vi = table.headers.indexOf(valueColumn);
  const gi = groupColumn ? table.headers.indexOf(groupColumn) : -1;
  if (vi === -1 || (groupColumn && gi === -1)) throw new Error("Select a valid column.");
  const groups = Object.create(null);
  let skipped = 0;
  for (const row of table.rows) {
    const raw = row[vi].trim(), val = raw ? Number(raw) : NaN;
    if (!Number.isFinite(val)) { skipped++; continue; }
    const label = gi < 0 ? "overall" : (row[gi].trim() || "(unlabelled)");
    if (!Object.hasOwn(groups, label)) groups[label] = [];
    groups[label].push(val);
  }
  return { groups, skipped };
}
function valuesFromManual(text) {
  const fields = text.trim().split(/[\s,;]+/).filter(Boolean);
  if (fields.length > MAX_ROWS) throw new Error("Too many observations.");
  if (fields.some(v => !Number.isFinite(Number(v)))) throw new Error("Manual data must contain only finite numbers.");
  return { groups: { overall: fields.map(Number) }, skipped: 0 };
}
function csvEscape(s) {
  const text = String(s);
  return /[",\r\n]/.test(text) ? '"' + text.replaceAll('"', '""') + '"' : text;
}
function safeSpreadsheetLabel(label) {
  // Stop untrusted group labels from becoming formulas in spreadsheet software.
  return /^[=+\\-@\\t\\r]/.test(label) ? "'" + label : label;
}
function exportCSV(analysis) {
  const head = ["group","n_total","n_used","n_outliers_excluded","lower_limit","upper_limit",
    "ci_level","lower_ci_low","lower_ci_high","upper_ci_low","upper_ci_high","below_clsi_min_n"];
  const rows = [head, ...[analysis.overall, ...analysis.subgroups].map(ri =>
    [safeSpreadsheetLabel(ri.label),ri.nTotal,ri.nUsed,ri.nOutliers,ri.lower.toFixed(4),ri.upper.toFixed(4),ri.ci,
     ri.lowerCI[0].toFixed(4),ri.lowerCI[1].toFixed(4),ri.upperCI[0].toFixed(4),
     ri.upperCI[1].toFixed(4),ri.belowMin])];
  return rows.map(r => r.map(csvEscape).join(",")).join("\r\n") + "\r\n";
}

function init() {
  const $ = id => document.getElementById(id);
  let table = null, last = null;
  const result = $("results"), error = $("error");
  const resetResult = () => { result.replaceChildren(); error.textContent = ""; $("download").disabled = true; last = null; };
  const info = (text, parent, tag = "p", className = "") => {
    const el = document.createElement(tag);
    el.textContent = text;
    if (className) el.className = className;
    parent.append(el);
    return el;
  };
  const setOptions = (select, values) => {
    select.replaceChildren();
    values.forEach(([value, label]) => {
      const item = document.createElement("option");
      item.value = value; item.textContent = label; select.add(item);
    });
  };
  $("file").addEventListener("change", async () => {
    resetResult();
    table = null; $("csvControls").hidden = true;
    const file = $("file").files?.[0];
    $("fileMeta").textContent = "";
    if (!file) return;
    try {
      if (file.size > MAX_FILE_BYTES) throw new Error("File exceeds the 5 MB limit.");
      table = parseCSV(await file.text());
      setOptions($("valueColumn"), table.headers.map(h => [h, h]));
      setOptions($("groupColumn"), [["", "No partition"], ...table.headers.map(h => [h, h])]);
      $("csvControls").hidden = false;
      $("fileMeta").textContent = table.rows.length + " data rows loaded locally.";
    } catch (e) { error.textContent = e.message; }
  });
  $("run").addEventListener("click", () => {
    resetResult();
    try {
      const raw = table
        ? valuesFromCSV(table, $("valueColumn").value, $("groupColumn").value)
        : valuesFromManual($("manual").value);
      const ci = Number($("ci").value);
      const data = analyze(raw.groups, ci, $("exclude").checked);
      last = data;
      info("Calculated reference intervals", result, "h2");
      if (raw.skipped) info(raw.skipped + " missing or nonnumeric rows skipped.", result, "p", "warning");
      const tableEl = document.createElement("table");
      const tHead = document.createElement("thead"), tBody = document.createElement("tbody");
      const header = document.createElement("tr");
      ["Group","Used / total","Excluded","Lower limit","Upper limit","Lower CI","Upper CI"].forEach(h => info(h, header, "th"));
      tHead.append(header);
      [data.overall, ...(data.subgroups.length > 1 ? data.subgroups : [])].forEach(ri => {
        const row = document.createElement("tr");
        const fmt = n => n.toFixed(3);
        [ri.label, ri.nUsed + " / " + ri.nTotal, ri.nOutliers,
          fmt(ri.lower), fmt(ri.upper), ri.lowerCI.map(fmt).join(" – "),
          ri.upperCI.map(fmt).join(" – ")].forEach(v => info(String(v), row, "td"));
        tBody.append(row);
        if (ri.belowMin) info(ri.label + ": n=" + ri.nUsed + " is below the CLSI-recommended 120; provisional estimate only.", result, "p", "warning");
      });
      tableEl.append(tHead, tBody); result.append(tableEl);
      if (data.pairs.length) {
        info("Pairwise Harris–Boyd comparisons (screening only)", result, "h3");
        for (const pair of data.pairs) {
          info(pair.labelA + " vs " + pair.labelB + ": z=" + pair.z.toFixed(3) +
            ", critical=" + pair.critical.toFixed(2) + " — " +
            (pair.partition ? "consider partitioning" : "no partition suggested"), result);
        }
      }
      info("The sample must represent a suitably selected reference population. Outliers and partitioning decisions require clinical/laboratory review; results are not automatically validated clinical limits.", result, "p", "note");
      $("download").disabled = false;
    } catch (e) { error.textContent = e.message; }
  });
  $("download").addEventListener("click", () => {
    if (!last) return;
    const url = URL.createObjectURL(new Blob([exportCSV(last)], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url; a.download = "reference-interval-results.csv"; document.body.append(a);
    a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  });
  $("demo").addEventListener("click", () => {
    resetResult();
    table = null; $("file").value = ""; $("fileMeta").textContent = "";
    $("csvControls").hidden = true;
    $("manual").value = Array.from({length: 150}, (_, i) =>
      (80 + 0.15 * i + 3 * Math.sin(i * 2.4)).toFixed(2)).join(", ");
  });
}
if (typeof window !== "undefined") window.addEventListener("DOMContentLoaded", init);
if (typeof module !== "undefined" && module.exports) {
  module.exports = { interval, harrisBoyd, analyze, parseCSV, valuesFromCSV, valuesFromManual, exportCSV };
}
