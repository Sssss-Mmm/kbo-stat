const state = {
  season: 2026,
  sort: "WARProxy",
  query: "",
  players: [],
  statRows: [],
  selected: null,
};
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
  const [registeredText, metricsText, rawHitterText] = await Promise.all([
    fetchDataFile("kbo_registered_players_latest.csv"),
    fetchDataFile(`kbo_hitter_metrics_${state.season}.csv`),
    fetchDataFile(`kbo_${state.season}.csv`),
  ]);
  const registered = registeredText ? parseCsv(registeredText).map(normalizeRow) : [];
  const metrics = metricsText ? parseCsv(metricsText).map(normalizeRow) : [];
  const rawHitters = rawHitterText ? parseCsv(rawHitterText).map(normalizeRow) : [];
  state.statRows = metrics.length ? metrics : normalizeRawHitters(rawHitters);

  const statByNameTeam = new Map(
    state.statRows.map((row) => [`${row.Player || row["선수명"]}|${row.Team || row["팀명"]}`, row])
  );
  state.players = registered.length
    ? registered.map((player) => mergePlayerStats(player, statByNameTeam))
    : state.statRows.map((row) => ({
        PlayerName: row.Player || row["선수명"],
        Team: row.Team || row["팀명"],
        Position: "타자",
        RecordType: "hitter",
        ...row,
      }));
  state.selected = state.players.find((player) => hasMetric(player, state.sort)) || state.players[0] || null;
}

async function fetchDataFile(fileName) {
  return apiFetchCsv(fileName);
}

function normalizeRawHitters(rows) {
  return rows.map((row) => ({
    ...row,
    Player: row.Player || row["선수명"],
    Team: row.Team || row["팀명"],
    WARProxy: Number.isFinite(row.XR) ? row.XR / 8 : undefined,
  }));
}

function mergePlayerStats(player, statByNameTeam) {
  const stat = statByNameTeam.get(`${player.PlayerName}|${player.Team}`) || {};
  return {
    ...player,
    ...stat,
    PlayerName: player.PlayerName,
    Player: player.PlayerName,
    Team: player.Team,
    Position: player.Position,
    RecordType: player.RecordType,
  };
}

function render() {
  const rows = filteredRows();
  state.selected = rows.includes(state.selected) ? state.selected : rows[0] || state.players[0] || null;
  renderCard();
  renderTable(rows);
  renderLeaderBars("hrBars", "HR", 8);
  renderLeaderBars("opsBars", "OPS", 8);
  const metricCount = state.players.filter((player) => hasAnyMetric(player)).length;
  $("playerNote").textContent = `${state.players.length}명 등록 · 지표 보유 ${metricCount}명 · ${state.sort} 기준`;
}

function filteredRows() {
  const query = state.query;
  return state.players
    .filter((player) => {
      if (!query) return true;
      return [player.PlayerName, player.Team, player.Position, player.BackNo, player.PlayerId]
        .some((value) => String(value || "").includes(query));
    })
    .sort(comparePlayers);
}

function comparePlayers(a, b) {
  const av = metricValue(a, state.sort);
  const bv = metricValue(b, state.sort);
  if (Number.isFinite(av) && Number.isFinite(bv)) return bv - av;
  if (Number.isFinite(av)) return -1;
  if (Number.isFinite(bv)) return 1;
  return String(a.Team).localeCompare(String(b.Team), "ko") || String(a.Position).localeCompare(String(b.Position), "ko") || String(a.PlayerName).localeCompare(String(b.PlayerName), "ko");
}

function renderCard() {
  const p = state.selected;
  if (!p) {
    $("playerTitle").textContent = "-";
    $("playerCard").innerHTML = `<p class="muted">No player data.</p>`;
    $("metricBars").innerHTML = "";
    return;
  }
  $("playerTitle").textContent = p.PlayerName;
  $("playerCard").innerHTML = `
    <p class="eyebrow">Selected Player</p>
    <h3>${p.PlayerName}</h3>
    <p class="muted">${p.Team} · ${p.Position} · ${p.BackNo ? `${p.BackNo}번` : "-"} · ${p.PitchBat || ""}</p>
    <div class="stat-grid">
      <div class="stat-box"><span>WARProxy</span><strong>${fmtOne(metricValue(p, "WARProxy"))}</strong></div>
      <div class="stat-box"><span>OPS</span><strong>${fmtRate(metricValue(p, "OPS"))}</strong></div>
      <div class="stat-box"><span>HR</span><strong>${fmtInt(metricValue(p, "HR"))}</strong></div>
      <div class="stat-box"><span>RBI</span><strong>${fmtInt(metricValue(p, "RBI"))}</strong></div>
    </div>
  `;
  const max = { AVG: 0.4, OBP: 0.5, SLG: 0.7, OPS: 1.1, WARProxy: 7 };
  $("metricBars").innerHTML = ["AVG", "OBP", "SLG", "OPS", "WARProxy"]
    .map((metric) => {
      const value = metricValue(p, metric);
      const width = Number.isFinite(value) ? Math.max(3, Math.min(100, (value / max[metric]) * 100)) : 0;
      return `<div class="metric-row"><span>${metric}</span><strong>${metric === "WARProxy" ? fmtOne(value) : fmtRate(value)}</strong><i><b style="width:${width}%"></b></i></div>`;
    })
    .join("");
}

function renderTable(rows) {
  $("playerRows").innerHTML = rows.slice(0, 120).map((p, index) => `
    <tr data-player="${p.PlayerId || p.PlayerName}">
      <td><span class="rank-badge">${index + 1}</span></td>
      <td><strong>${p.PlayerName}</strong><small>${p.Position || ""} ${p.BackNo ? `· ${p.BackNo}번` : ""}</small></td>
      <td>${p.Team || "-"}</td>
      <td>${fmtRate(metricValue(p, "AVG"))}</td>
      <td>${fmtRate(metricValue(p, "OBP"))}</td>
      <td>${fmtRate(metricValue(p, "SLG"))}</td>
      <td><span class="rate-pill">${fmtRate(metricValue(p, "OPS"))}</span></td>
      <td>${fmtInt(metricValue(p, "HR"))}</td>
      <td>${fmtInt(metricValue(p, "RBI"))}</td>
      <td><span class="diff-pill positive">${fmtOne(metricValue(p, "WARProxy"))}</span></td>
    </tr>
  `).join("");
  document.querySelectorAll("[data-player]").forEach((row) => {
    row.addEventListener("click", () => {
      state.selected = state.players.find((player) => String(player.PlayerId || player.PlayerName) === row.dataset.player);
      renderCard();
    });
  });
}

function renderLeaderBars(id, metric, limit) {
  const leaders = state.players.filter((row) => hasMetric(row, metric)).sort((a, b) => metricValue(b, metric) - metricValue(a, metric)).slice(0, limit);
  const max = Math.max(...leaders.map((row) => metricValue(row, metric) || 0), 1);
  $(id).innerHTML = leaders.map((p) => `<div class="bar-row"><strong>${p.PlayerName}</strong><span class="bar-track"><span class="bar-fill" style="width:${((metricValue(p, metric) || 0) / max) * 100}%"></span></span><span>${metric === "OPS" ? fmtRate(metricValue(p, metric)) : fmtInt(metricValue(p, metric))}</span><small>${p.Team}</small></div>`).join("");
}

function findPlayer(query) {
  if (!query) return state.players.find((player) => hasMetric(player, state.sort)) || state.players[0] || null;
  return state.players.find((player) => String(player.PlayerName).includes(query)) || state.players[0] || null;
}

function metricValue(player, metric) {
  const value = player?.[metric];
  return Number.isFinite(value) ? value : undefined;
}

function hasMetric(player, metric) {
  return Number.isFinite(metricValue(player, metric));
}

function hasAnyMetric(player) {
  return ["AVG", "OBP", "SLG", "OPS", "HR", "RBI", "WARProxy"].some((metric) => hasMetric(player, metric));
}

function parseCsv(text) { const rows = []; let row = []; let cell = ""; let quoted = false; for (let index = 0; index < text.length; index++) { const char = text[index]; const next = text[index + 1]; if (char === '"' && quoted && next === '"') { cell += '"'; index++; } else if (char === '"') { quoted = !quoted; } else if (char === "," && !quoted) { row.push(cell); cell = ""; } else if ((char === "\n" || char === "\r") && !quoted) { if (char === "\r" && next === "\n") index++; row.push(cell); if (row.some(Boolean)) rows.push(row); row = []; cell = ""; } else { cell += char; } } if (cell || row.length) { row.push(cell); rows.push(row); } const headers = (rows.shift() || []).map((header) => header.replace(/^\uFEFF/, "")); return rows.map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]))); }
function normalizeRow(row) { const normalized = { ...row }; Object.entries(normalized).forEach(([key, value]) => { const number = Number(String(value).replace(/,/g, "")); if (value !== "" && Number.isFinite(number)) normalized[key] = number; }); return normalized; }
function fmtRate(value) { return Number.isFinite(value) ? value.toFixed(3).replace(/^0/, "") : "-"; }
function fmtOne(value) { return Number.isFinite(value) ? value.toFixed(1) : "-"; }
function fmtInt(value) { return Number.isFinite(value) ? Math.round(value).toLocaleString("ko-KR") : "-"; }
