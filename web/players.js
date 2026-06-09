const ROOTS = ["../data/processed", "/data/processed", "./data/processed"];
const state = { season: 2026, sort: "WARProxy", query: "", players: [], selected: null };
const $ = (id) => document.getElementById(id);

init();

async function init() {
  $("sortSelect").addEventListener("change", (event) => {
    state.sort = event.target.value;
    render();
  });
  $("playerSearch").addEventListener("input", (event) => {
    state.query = event.target.value.trim();
    state.selected = findPlayer(state.query);
    render();
  });
  await loadPlayers();
  render();
}

async function loadPlayers() {
  const text = await fetchDataFile(`kbo_hitter_metrics_${state.season}.csv`);
  state.players = text ? parseCsv(text).map(normalizeRow) : [];
  state.selected = state.players[0] || null;
}

async function fetchDataFile(fileName) {
  for (const root of ROOTS) {
    try {
      const response = await fetch(`${root}/${fileName}`);
      if (response.ok) return response.text();
    } catch {}
  }
  return null;
}

function render() {
  const rows = filteredRows();
  state.selected = rows.includes(state.selected) ? state.selected : rows[0] || state.players[0] || null;
  renderCard();
  renderTable(rows);
  renderLeaderBars("hrBars", "HR", 8);
  renderLeaderBars("opsBars", "OPS", 8);
  $("playerNote").textContent = `${state.players.length} players · sorted by ${state.sort}`;
}

function filteredRows() {
  return state.players
    .filter((player) => !state.query || String(player.Player).includes(state.query) || String(player.Team).includes(state.query))
    .sort((a, b) => (b[state.sort] || 0) - (a[state.sort] || 0));
}

function renderCard() {
  const p = state.selected;
  if (!p) {
    $("playerTitle").textContent = "-";
    $("playerCard").innerHTML = `<p class="muted">No player data.</p>`;
    $("metricBars").innerHTML = "";
    return;
  }
  $("playerTitle").textContent = p.Player;
  $("playerCard").innerHTML = `
    <p class="eyebrow">Selected Player</p>
    <h3>${p.Player}</h3>
    <p class="muted">${p.Team} · ${state.season}</p>
    <div class="stat-grid">
      <div class="stat-box"><span>WARProxy</span><strong>${fmtOne(p.WARProxy)}</strong></div>
      <div class="stat-box"><span>OPS</span><strong>${fmtRate(p.OPS)}</strong></div>
      <div class="stat-box"><span>HR</span><strong>${fmtInt(p.HR)}</strong></div>
      <div class="stat-box"><span>RBI</span><strong>${fmtInt(p.RBI)}</strong></div>
    </div>
  `;
  const max = { AVG: 0.4, OBP: 0.5, SLG: 0.7, OPS: 1.1, WARProxy: 7 };
  $("metricBars").innerHTML = ["AVG", "OBP", "SLG", "OPS", "WARProxy"]
    .map((metric) => `<div class="metric-row"><span>${metric}</span><strong>${metric === "WARProxy" ? fmtOne(p[metric]) : fmtRate(p[metric])}</strong><i><b style="width:${Math.max(3, Math.min(100, (p[metric] / max[metric]) * 100))}%"></b></i></div>`)
    .join("");
}

function renderTable(rows) {
  $("playerRows").innerHTML = rows.slice(0, 30).map((p, index) => `
    <tr data-player="${p.Player}">
      <td><span class="rank-badge">${index + 1}</span></td>
      <td><strong>${p.Player}</strong></td>
      <td>${p.Team}</td>
      <td>${fmtRate(p.AVG)}</td>
      <td>${fmtRate(p.OBP)}</td>
      <td>${fmtRate(p.SLG)}</td>
      <td><span class="rate-pill">${fmtRate(p.OPS)}</span></td>
      <td>${fmtInt(p.HR)}</td>
      <td>${fmtInt(p.RBI)}</td>
      <td><span class="diff-pill positive">${fmtOne(p.WARProxy)}</span></td>
    </tr>
  `).join("");
  document.querySelectorAll("[data-player]").forEach((row) => {
    row.addEventListener("click", () => {
      state.selected = state.players.find((player) => player.Player === row.dataset.player);
      renderCard();
    });
  });
}

function renderLeaderBars(id, metric, limit) {
  const leaders = [...state.players].sort((a, b) => (b[metric] || 0) - (a[metric] || 0)).slice(0, limit);
  const max = Math.max(...leaders.map((row) => row[metric] || 0), 1);
  $(id).innerHTML = leaders.map((p) => `<div class="bar-row"><strong>${p.Player}</strong><span class="bar-track"><span class="bar-fill" style="width:${((p[metric] || 0) / max) * 100}%"></span></span><span>${metric === "OPS" ? fmtRate(p[metric]) : fmtInt(p[metric])}</span><small>${p.Team}</small></div>`).join("");
}

function findPlayer(query) {
  if (!query) return state.players[0] || null;
  return state.players.find((player) => String(player.Player).includes(query)) || state.players[0] || null;
}

function parseCsv(text) { const rows = []; let row = []; let cell = ""; let quoted = false; for (let index = 0; index < text.length; index++) { const char = text[index]; const next = text[index + 1]; if (char === '"' && quoted && next === '"') { cell += '"'; index++; } else if (char === '"') { quoted = !quoted; } else if (char === "," && !quoted) { row.push(cell); cell = ""; } else if ((char === "\n" || char === "\r") && !quoted) { if (char === "\r" && next === "\n") index++; row.push(cell); if (row.some(Boolean)) rows.push(row); row = []; cell = ""; } else { cell += char; } } if (cell || row.length) { row.push(cell); rows.push(row); } const headers = (rows.shift() || []).map((header) => header.replace(/^\uFEFF/, "")); return rows.map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]))); }
function normalizeRow(row) { const normalized = { ...row }; Object.entries(normalized).forEach(([key, value]) => { const number = Number(String(value).replace(/,/g, "")); if (value !== "" && Number.isFinite(number)) normalized[key] = number; }); return normalized; }
function fmtRate(value) { return Number.isFinite(value) ? value.toFixed(3).replace(/^0/, "") : "-"; }
function fmtOne(value) { return Number.isFinite(value) ? value.toFixed(1) : "-"; }
function fmtInt(value) { return Number.isFinite(value) ? Math.round(value).toLocaleString("ko-KR") : "-"; }
