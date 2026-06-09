const RAW_ROOTS = [
  "../data/raw/kbo_official",
  "/data/raw/kbo_official",
  "/web/data/raw/kbo_official",
  "./data/raw/kbo_official",
];
const PROCESSED_ROOTS = [
  "../data/processed",
  "/data/processed",
  "/web/data/processed",
  "./data/processed",
];
const VB_YEARS = Array.from({ length: 45 }, (_, index) => 2026 - index);

async function fetchDataFile(fileName, roots = RAW_ROOTS) {
  const flatRoot = roots === RAW_ROOTS || roots.includes("/data/raw/kbo_official") ? "/web" : null;
  const candidates = flatRoot ? [...roots, flatRoot] : roots;
  for (const root of candidates) {
    try {
      const response = await fetch(`${root}/${fileName}`);
      if (response.ok) return response.text();
    } catch {
      // Try next root.
    }
  }
  return null;
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < text.length; index++) {
    const char = text[index];
    const next = text[index + 1];
    if (char === '"' && quoted && next === '"') {
      cell += '"';
      index++;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (char === "," && !quoted) {
      row.push(cell);
      cell = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && next === "\n") index++;
      row.push(cell);
      if (row.some(Boolean)) rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += char;
    }
  }
  if (cell || row.length) {
    row.push(cell);
    rows.push(row);
  }
  const headers = (rows.shift() || []).map((header) => header.replace(/^\uFEFF/, ""));
  return rows.map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])));
}

function normalizeRow(row) {
  const normalized = { ...row };
  Object.entries(normalized).forEach(([key, value]) => {
    const number = Number(String(value).replace(/,/g, ""));
    if (value !== "" && Number.isFinite(number)) normalized[key] = number;
  });
  return normalized;
}

function fmtRate(value) {
  return Number.isFinite(value) ? value.toFixed(3).replace(/^0/, "") : "-";
}

function fmtNumber(value, digits = 0) {
  return Number.isFinite(value) ? value.toLocaleString("ko-KR", { maximumFractionDigits: digits }) : "-";
}

function renderSeasonSelect(select, selected, onChange) {
  select.innerHTML = VB_YEARS.map((year) => `<option value="${year}">${year}시즌</option>`).join("");
  select.value = selected;
  select.addEventListener("change", () => onChange(Number(select.value)));
}

function seasonFromHash(fallback = 2026) {
  const value = Number(String(location.hash || "").replace("#", ""));
  return Number.isFinite(value) && value >= 1982 ? value : fallback;
}

function setActiveNav(page) {
  document.querySelectorAll("[data-page]").forEach((link) => {
    link.classList.toggle("active", link.dataset.page === page);
  });
}
