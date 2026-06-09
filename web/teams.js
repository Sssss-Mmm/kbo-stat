const DATA_ROOTS = ["../data/raw/kbo_official", "/data/raw/kbo_official", "./data/raw/kbo_official"];
const PROCESSED_ROOTS = ["../data/processed", "/data/processed", "./data/processed"];
const YEARS = Array.from({ length: 45 }, (_, index) => 2026 - index);
const TEAM_COLORS = { LG: "#0b7f74", KT: "#2e65b8", "\uc0bc\uc131": "#356bc6", KIA: "#d05240", "\ud55c\ud654": "#e0872c", "\ub450\uc0b0": "#243b6b", SSG: "#c73845", NC: "#315f8d", "\ub86f\ub370": "#8a5a28", "\ud0a4\uc6c0": "#7a3f76" };
const COL = { rank: "\uc21c\uc704", team: "\ud300\uba85", games: "\uacbd\uae30", wins: "\uc2b9", losses: "\ud328", draws: "\ubb34", winRate: "\uc2b9\ub960", gb: "\uac8c\uc784\ucc28", recent: "\ucd5c\uadfc10\uacbd\uae30", streak: "\uc5f0\uc18d" };
const state = { season: 2026, team: "", standings: [], games: [], monthly: [] };
const $ = (id) => document.getElementById(id);

init();

async function init() {
  $("seasonSelect").innerHTML = YEARS.map((year) => `<option value="${year}">${year}</option>`).join("");
  $("seasonSelect").value = state.season;
  $("seasonSelect").addEventListener("change", async (event) => {
    state.season = Number(event.target.value);
    await loadSeason();
    render();
  });
  $("teamSelect").addEventListener("change", (event) => {
    state.team = event.target.value;
    render();
  });
  await loadSeason();
  render();
}

async function loadSeason() {
  const [standingsText, gamesText, monthlyText] = await Promise.all([
    fetchDataFile(`kbo_team_rank_${state.season}.csv`, DATA_ROOTS),
    fetchDataFile(`kbo_team_games_${state.season}.csv`, PROCESSED_ROOTS),
    fetchDataFile(`kbo_team_monthly_${state.season}.csv`, PROCESSED_ROOTS),
  ]);
  state.standings = standingsText ? parseCsv(standingsText).map(normalizeRow) : [];
  state.games = gamesText ? parseCsv(gamesText).map(normalizeRow) : [];
  state.monthly = monthlyText ? parseCsv(monthlyText).map(normalizeRow) : [];
  const teams = state.standings.map((row) => row[COL.team]).filter(Boolean);
  state.team = teams.includes(state.team) ? state.team : teams[0] || "";
  $("teamSelect").innerHTML = teams.map((team) => `<option value="${team}">${team}</option>`).join("");
  $("teamSelect").value = state.team;
}

async function fetchDataFile(fileName, roots) {
  for (const root of roots) {
    try {
      const response = await fetch(`${root}/${fileName}`);
      if (response.ok) return response.text();
    } catch {}
  }
  return null;
}

function render() {
  const standing = state.standings.find((row) => row[COL.team] === state.team);
  const games = teamGames();
  const totals = summarize(games);
  $("teamTitle").textContent = state.team || "-";
  $("teamNote").textContent = `${state.season} season · ${games.length} final games loaded`;
  $("rankCard").textContent = standing ? `${standing[COL.rank]}\uc704` : "-";
  $("recordCard").textContent = standing ? `${standing[COL.wins]}\uc2b9 ${standing[COL.losses]}\ud328 ${standing[COL.draws]}\ubb34 · ${fmtRate(standing[COL.winRate])}` : "-";
  $("diffCard").textContent = fmtSigned(totals.diff);
  $("runsCard").textContent = `RF ${fmtInt(totals.for)} · RA ${fmtInt(totals.against)}`;
  $("recentCard").textContent = standing ? standing[COL.recent] : "-";
  $("streakCard").textContent = standing ? standing[COL.streak] : "-";
  renderMonthly();
  renderRuns(totals);
  renderHomeAway(games);
  renderGameLog(games);
}

function renderMonthly() {
  const rows = state.monthly.filter((row) => row.Team === state.team).sort((a, b) => String(a.Month).localeCompare(String(b.Month)));
  const svg = $("monthlySvg");
  const width = svg.clientWidth || 820;
  const height = 330;
  const pad = { top: 26, right: 24, bottom: 38, left: 42 };
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  if (!rows.length) {
    svg.innerHTML = emptyText(width, height, "No monthly data");
    return;
  }
  const step = (width - pad.left - pad.right) / rows.length;
  const y = scale([0, 1], [height - pad.bottom, pad.top]);
  svg.innerHTML = rows.map((row, index) => {
    const x = pad.left + index * step + 12;
    const h = height - pad.bottom - y(row.WinRate);
    return `<rect x="${x}" y="${y(row.WinRate)}" width="${Math.max(36, step - 24)}" height="${h}" rx="7" fill="${teamColor(state.team)}"></rect><text class="tick-label" x="${x + Math.max(36, step - 24) / 2}" y="${height - 14}" text-anchor="middle">${row.Month}M</text><text class="tick-label" x="${x + Math.max(36, step - 24) / 2}" y="${y(row.WinRate) - 8}" text-anchor="middle">${fmtRate(row.WinRate)}</text>`;
  }).join("");
}

function renderRuns(totals) {
  const svg = $("runsSvg");
  const width = svg.clientWidth || 440;
  const height = 320;
  const max = Math.max(totals.for, totals.against, 1);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.innerHTML = `${barSvg("RF", totals.for, max, 74, "#0b7f74", width)}${barSvg("RA", totals.against, max, 154, "#d05240", width)}<text class="big-number" x="28" y="252">${fmtSigned(totals.diff)}</text><text class="tick-label" x="28" y="274">run differential</text>`;
}

function renderHomeAway(games) {
  const home = record(games.filter((game) => game.HomeAway === "home"));
  const away = record(games.filter((game) => game.HomeAway === "away"));
  const max = Math.max(rate(home), rate(away), 1);
  $("homeAwayBars").innerHTML = [
    ["Home", home, "#0b7f74"],
    ["Away", away, "#2e65b8"],
  ].map(([label, rec, color]) => `<div class="bar-row"><strong>${label}</strong><span class="bar-track"><span class="bar-fill" style="width:${(rate(rec) / max) * 100}%; background:${color}"></span></span><span>${fmtRate(rate(rec))}</span><small>${rec.w}-${rec.d}-${rec.l}</small></div>`).join("");
}

function renderGameLog(games) {
  $("gameLog").innerHTML = [...games].sort((a, b) => String(b.Date).localeCompare(String(a.Date))).slice(0, 12).map((game) => `<div class="game-row"><strong class="${game.Result === "W" ? "positive" : game.Result === "L" ? "negative" : ""}">${game.Result}</strong><span>${game.Date}</span><span>${game.Team} ${game.RunsFor} : ${game.RunsAgainst} ${game.Opponent}</span><small>${game.HomeAway} · ${game.Ballpark}</small></div>`).join("");
}

function teamGames() { return state.games.filter((game) => game.Team === state.team); }
function summarize(rows) { return { for: sum(rows.map((row) => row.RunsFor)), against: sum(rows.map((row) => row.RunsAgainst)), diff: sum(rows.map((row) => row.RunDiff)) }; }
function record(rows) { return { w: sum(rows.map((row) => row.Win)), l: sum(rows.map((row) => row.Loss)), d: sum(rows.map((row) => row.Draw)) }; }
function rate(rec) { return rec.w + rec.l ? rec.w / (rec.w + rec.l) : 0; }
function parseCsv(text) { const rows = []; let row = []; let cell = ""; let quoted = false; for (let index = 0; index < text.length; index++) { const char = text[index]; const next = text[index + 1]; if (char === '"' && quoted && next === '"') { cell += '"'; index++; } else if (char === '"') { quoted = !quoted; } else if (char === "," && !quoted) { row.push(cell); cell = ""; } else if ((char === "\n" || char === "\r") && !quoted) { if (char === "\r" && next === "\n") index++; row.push(cell); if (row.some(Boolean)) rows.push(row); row = []; cell = ""; } else { cell += char; } } if (cell || row.length) { row.push(cell); rows.push(row); } const headers = (rows.shift() || []).map((header) => header.replace(/^\uFEFF/, "")); return rows.map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]))); }
function normalizeRow(row) { const normalized = { ...row }; Object.entries(normalized).forEach(([key, value]) => { const number = Number(String(value).replace(/,/g, "")); if (value !== "" && Number.isFinite(number)) normalized[key] = number; }); return normalized; }
function barSvg(label, value, max, y, color, width) { const barWidth = ((width - 150) * value) / max; return `<text class="tick-label" x="28" y="${y + 18}">${label}</text><rect x="70" y="${y}" width="${barWidth}" height="34" rx="7" fill="${color}"></rect><text class="tick-label" x="${80 + barWidth}" y="${y + 22}">${fmtInt(value)}</text>`; }
function scale(domain, range) { return (value) => range[0] + ((value - domain[0]) / (domain[1] - domain[0] || 1)) * (range[1] - range[0]); }
function sum(values) { return values.filter(Number.isFinite).reduce((total, value) => total + value, 0); }
function teamColor(team) { return TEAM_COLORS[team] || "#53636f"; }
function fmtRate(value) { return Number.isFinite(value) ? value.toFixed(3).replace(/^0/, "") : "-"; }
function fmtInt(value) { return Number.isFinite(value) ? Math.round(value).toLocaleString("ko-KR") : "-"; }
function fmtSigned(value) { if (!Number.isFinite(value)) return "-"; return value > 0 ? `+${fmtInt(value)}` : fmtInt(value); }
function emptyText(width, height, text) { return `<text class="tick-label" x="${width / 2}" y="${height / 2}" text-anchor="middle">${text}</text>`; }
