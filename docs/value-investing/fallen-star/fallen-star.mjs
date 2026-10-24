import { DataTable } from "./table.mjs";

const monthSelect = document.getElementById("bounce-month");
const healthyOnly = document.getElementById("healthy-only");
const status = document.getElementById("results-status");
const context = document.getElementById("results-context");
const tableHost = document.getElementById("results-table-host");
const evidencePanel = document.getElementById("evidence-panel");
const evidenceTitle = document.getElementById("evidence-title");
const evidenceNote = document.getElementById("evidence-note");
const evidenceHost = document.getElementById("evidence-table-host");
const dataNote = document.getElementById("data-note");

const percent = new Intl.NumberFormat(undefined, { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
const number = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const fullMonth = new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric", timeZone: "UTC" });
const friendlyDate = new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });

let manifest = null;
let currentData = null;
let requestNumber = 0;
let resultTable = null;
let evidenceTable = null;
let selectedCandidate = null;

function monthName(iso) {
  return fullMonth.format(new Date(`${iso}-01T00:00:00Z`));
}

function displayDate(iso) {
  if (!iso) return "—";
  return friendlyDate.format(new Date(`${iso}T00:00:00Z`));
}

function futureMonths(count) {
  const now = new Date();
  const list = [];
  for (let step = 1; step <= count; step++) {
    const value = new Date(Date.UTC(now.getFullYear(), now.getMonth() + step, 1));
    list.push(`${value.getUTCFullYear()}-${String(value.getUTCMonth() + 1).padStart(2, "0")}`);
  }
  return list;
}

function setupMonths() {
  for (const value of futureMonths(12)) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = monthName(value);
    monthSelect.append(option);
  }
}

function showStatus(message) {
  status.textContent = message;
  status.hidden = false;
}

function hideEvidence() {
  evidencePanel.hidden = true;
  evidenceHost.hidden = true;
  selectedCandidate = null;
}

function clearResults() {
  currentData = null;
  healthyOnly.disabled = true;
  tableHost.hidden = true;
  dataNote.hidden = true;
  hideEvidence();
}

function exportMetadata(tableName) {
  return {
    "Table": tableName,
    "Selected bounce month": monthSelect.value,
    "Data as-of date": currentData?.as_of || "",
    "Model version": currentData?.model_version || "",
    "Data version": currentData?.data_version || "",
    "Financially healthy only": healthyOnly.checked ? "Yes" : "No",
  };
}

function healthStatus(candidate) {
  return candidate.health?.status || "Unknown";
}

function healthBadge(candidate) {
  const badge = document.createElement("span");
  const value = healthStatus(candidate);
  badge.className = `health-badge health-${value.toLowerCase()}`;
  badge.textContent = value;
  return badge;
}

function resultColumns() {
  return [
    { key: "name", label: "Company", width: 34 },
    { key: "ticker", label: "Ticker", width: 15 },
    { key: "exchange", label: "Exchange", width: 18 },
    { key: "drop_date", label: "Drop date", type: "date", width: 18, render: item => displayDate(item.drop_date) },
    { key: "drop_pct", label: "Drop", type: "percent", width: 13, render: item => percent.format(item.drop_pct) },
    { key: "predicted_month", label: "Predicted onset", type: "month", width: 20,
      render: item => monthName(item.predicted_month) },
    { key: "probability", label: "Month probability", type: "percent", width: 22,
      render: item => percent.format(item.probability) },
    { key: "elapsed_months", label: "Months from drop", type: "integer", width: 19 },
    { key: "health", label: "Growth check", width: 18, render: healthBadge,
      exportValue: item => healthStatus(item), sortValue: item => healthStatus(item) },
    { key: "growth_pct", label: "Revenue growth", type: "percent", width: 20,
      render: item => item.health?.growth_pct === undefined ? "—" : percent.format(item.health.growth_pct / 100),
      exportValue: item => item.health?.growth_pct === undefined ? "" : item.health.growth_pct / 100,
      sortValue: item => item.health?.growth_pct },
    { key: "details", label: "Evidence", exportable: false, sortable: false, render: item => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "table-detail-button";
      button.textContent = "View details";
      button.setAttribute("aria-label", `View revenue evidence for ${item.name}`);
      button.addEventListener("click", () => showEvidence(item));
      return button;
    } },
  ];
}

function evidenceColumns() {
  return [
    { key: "fiscal_start", label: "Fiscal start", type: "date", width: 18, render: item => displayDate(item.fiscal_start) },
    { key: "fiscal_end", label: "Fiscal end", type: "date", width: 18, render: item => displayDate(item.fiscal_end) },
    { key: "filed_on", label: "Filed on", type: "date", width: 18, render: item => displayDate(item.filed_on) },
    { key: "revenue", label: "Revenue", type: "decimal", width: 25, render: item => number.format(item.revenue) },
    { key: "currency", label: "Currency", width: 15 },
    { key: "source", label: "Source", width: 36 },
  ];
}

function showEvidence(candidate) {
  selectedCandidate = candidate;
  evidencePanel.hidden = false;
  evidenceTitle.textContent = `Revenue history · ${candidate.name}`;
  const health = candidate.health || {};
  const records = Array.isArray(health.evidence) ? health.evidence : [];
  if (!records.length) {
    evidenceNote.textContent = health.reason || "No complete pre-drop revenue history is available for this company.";
    evidenceHost.hidden = true;
  } else {
    evidenceNote.textContent = `${healthStatus(candidate)} · ${health.increases} of 5 annual increases · ${number.format(health.growth_pct)}% overall revenue growth. These reports were filed before the drop.`;
    if (!evidenceTable) {
      evidenceTable = new DataTable(evidenceHost, {
        title: "Annual revenue evidence", columns: evidenceColumns(),
        filename: meta => `fallen-star-revenue-${meta.Ticker}-${meta["Selected bounce month"]}.xlsx`,
        initialSort: { key: "fiscal_end", direction: "asc" },
      });
    }
    evidenceTable.setRows(records, { ...exportMetadata("Annual revenue evidence"),
      "Company": candidate.name, "Ticker": candidate.ticker, "Drop date": candidate.drop_date });
    evidenceHost.hidden = false;
  }
  evidencePanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderResults() {
  if (!currentData) return;
  const all = currentData.candidates;
  const rows = healthyOnly.checked ? all.filter(item => healthStatus(item) === "Pass") : all;
  const label = monthName(monthSelect.value);
  context.textContent = `${label} · ${all.length.toLocaleString()} timing ${all.length === 1 ? "match" : "matches"}` +
    (healthyOnly.checked ? ` · ${rows.length.toLocaleString()} ${rows.length === 1 ? "finalist" : "finalists"}` : "");
  if (!resultTable) {
    resultTable = new DataTable(tableHost, {
      title: "Candidate results", columns: resultColumns(),
      filename: meta => `fallen-star-${meta["Selected bounce month"]}${meta["Financially healthy only"] === "Yes" ? "-healthy" : ""}.xlsx`,
      initialSort: { key: "probability", direction: "desc" },
    });
  }
  resultTable.setRows(rows, exportMetadata("Candidate results"));
  tableHost.hidden = false;
  if (selectedCandidate && !rows.includes(selectedCandidate)) hideEvidence();
  if (!rows.length) {
    showStatus(healthyOnly.checked && all.length ?
      `No ${label} timing matches pass the pre-drop growth check.` :
      `No stocks are currently predicted to begin bouncing in ${label}.`);
  } else {
    status.hidden = true;
  }
  const warnings = Array.isArray(currentData.data_quality_warnings) ? currentData.data_quality_warnings : [];
  dataNote.textContent = `Data as of ${displayDate(currentData.as_of)} · Model ${currentData.model_version}` +
    (warnings.length ? ` · Data note: ${warnings.join("; ")}` : "");
  dataNote.hidden = false;
}

async function loadMonth() {
  const request = ++requestNumber;
  clearResults();
  const selected = monthSelect.value;
  const label = monthName(selected);
  context.textContent = label;
  if (!manifest || manifest.status !== "ready") {
    showStatus("Forecast results are not available yet. Historical price and filing data must be loaded and evaluated before candidates can be published.");
    return;
  }
  if (!Array.isArray(manifest.months) || !manifest.months.includes(selected)) {
    showStatus(`There is no supported published forecast for ${label}. Choose another month when results become available.`);
    return;
  }
  showStatus(`Loading ${label} forecasts…`);
  try {
    const response = await fetch(`data/${selected}.json`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (request !== requestNumber) return;
    if (data.target_month !== selected || !Array.isArray(data.candidates) || !data.as_of || !data.model_version ||
        (manifest.as_of && data.as_of !== manifest.as_of) ||
        (manifest.model_version && data.model_version !== manifest.model_version)) {
      throw new Error("Invalid forecast data");
    }
    currentData = data;
    healthyOnly.disabled = false;
    renderResults();
  } catch (_) {
    if (request !== requestNumber) return;
    showStatus("This month's forecast could not be loaded. Please refresh the page or try another month.");
  }
}

setupMonths();
monthSelect.addEventListener("change", loadMonth);
healthyOnly.addEventListener("change", renderResults);
document.getElementById("close-evidence").addEventListener("click", hideEvidence);

try {
  const response = await fetch("data/manifest.json", { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  manifest = await response.json();
} catch (_) {
  manifest = null;
}
loadMonth();
