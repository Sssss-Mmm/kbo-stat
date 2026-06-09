const DATA_ROOTS = ["../data/raw/kbo_official", "/data/raw/kbo_official", "./data/raw/kbo_official"];
const PROCESSED_ROOTS = ["../data/processed", "/data/processed", "./data/processed"];
const YEARS = Array.from({ length: 45 }, (_, index) => 2026 - index);
const TEAM_COLORS = {
  LG: "#0b7f74",
  KT: "#2e65b8",
  "\uc0bc\uc131": "#356bc6",
  KIA: "#d05240",
  "\ud55c\ud654": "#e0872c",
  "\ub450\uc0b0": "#243b6b",
  SSG: "#c73845",
  NC: "#315f8d",
  "\ub86f\ub370": "#8a5a28",
  "\ud0a4\uc6c0": "#7a3f76",
};

const COL = {
  rank: "\uc21c\uc704",
  team: "\ud300\uba85",
  games: "\uacbd\uae30",
  wins: "\uc2b9",
  losses: "\ud328",
  draws: "\ubb34",
  winRate: "\uc2b9\ub960",
  gb: "\uac8c\uc784\ucc28",
  recent: "\ucd5c\uadfc10\uacbd\uae30",
  streak: "\uc5f0\uc18d",
  home: "\ud648",
  away: "\ubc29\ubb38",
  player: "\uc120\uc218\uba85",
};

const state = {
  season: 2026,
  team: "all",
  standings: [],
  hitters: [],
  schedule: [],
  rankHistory: [],
  teamGames: [],
  teamMonthly: [],
  selectedPlayer: null,
};

const $ = (id) => document.getElementById(id);

init();

async function init() {
  setupControls();
  await loadSeason();
  render();
}

function setupControls() {
  $("seasonSelect").innerHTML = YEARS.map((year) => `<option value="${year}">${year}</option>`).join("");
  $("seasonSelect").value = state.season;

  $("seasonSelect").addEventListener("change", async (event) => {
    state.season = Number(event.target.value);
    state.team = "all";
    state.selectedPlayer = null;
    await loadSeason();
    render();
  });

  $("teamSelect").addEventListener("change", (event) => {
    state.team = event.target.value;
    renderTeamSections();
  });

  $("playerSearch").addEventListener("input", () => {
    state.selectedPlayer = findPlayer($("playerSearch").value.trim());
    renderPlayerSections();
  });

  $("compareA").addEventListener("change", renderCompare);
  $("compareB").addEventListener("change", renderCompare);

  document.querySelectorAll("[data-scroll-target]").forEach((button) => {
    button.addEventListener("click", () => {
      document.getElementById(button.dataset.scrollTarget).scrollIntoView({ behavior: "smooth", block: "start" });
      document.querySelectorAll(".nav-button").forEach((nav) => nav.classList.toggle("active", nav === button));
    });
  });
}

async function loadSeason() {
  const [standingsText, hittersText, scheduleText, rankHistoryText, teamGamesText, teamMonthlyText] = await Promise.all([
    fetchDataFile(`kbo_team_rank_${state.season}.csv`, DATA_ROOTS),
    fetchDataFile(`kbo_${state.season}.csv`, DATA_ROOTS),
    fetchDataFile(`kbo_schedule_${state.season}.csv`, DATA_ROOTS),
    fetchDataFile(`kbo_team_rank_history_${state.season}.csv`, DATA_ROOTS),
    fetchDataFile(`kbo_team_games_${state.season}.csv`, PROCESSED_ROOTS),
    fetchDataFile(`kbo_team_monthly_${state.season}.csv`, PROCESSED_ROOTS),
  ]);

  state.standings = standingsText ? parseCsv(standingsText).map(normalizeRow) : [];
  state.hitters = hittersText ? parseCsv(hittersText).map(normalizeRow) : [];
  state.schedule = scheduleText ? parseCsv(scheduleText).map(normalizeRow) : [];
  state.rankHistory = rankHistoryText ? parseCsv(rankHistoryText).map(normalizeRow) : [];
  state.teamGames = teamGamesText ? parseCsv(teamGamesText).map(normalizeRow) : [];
  state.teamMonthly = teamMonthlyText ? parseCsv(teamMonthlyText).map(normalizeRow) : [];
  state.selectedPlayer = state.hitters[0] || null;
}

async function fetchDataFile(fileName) {
  return apiFetchCsv(fileName);
}

function render() {
  renderTeamOptions();
  renderCompareOptions();
  renderToday();
  renderTeamSections();
  renderPlayerSections();
  renderCompare();
  $("dataNote").textContent = state.standings.length
    ? `${state.season} season, ${state.standings.length} teams loaded`
    : `${state.season} season team standings are not available yet`;
}

function renderToday() {
  const sorted = [...state.standings].sort((a, b) => a[COL.rank] - b[COL.rank]);
  const leader = sorted[0];
  const streak = [...state.standings].sort((a, b) => streakScore(b[COL.streak]) - streakScore(a[COL.streak]))[0];
  const recent = [...state.standings].sort((a, b) => recentWinRate(b[COL.recent]) - recentWinRate(a[COL.recent]))[0];
  const hot = [...state.hitters].sort((a, b) => playerWar(b) - playerWar(a))[0];
  const hr = [...state.hitters].sort((a, b) => (b.HR || 0) - (a.HR || 0))[0];

  $("leaderTeam").textContent = leader ? `${leader[COL.rank]}\uc704 ${leader[COL.team]}` : "-";
  $("leaderRecord").textContent = leader ? `${leader[COL.wins]}\uc2b9 ${leader[COL.losses]}\ud328 ${leader[COL.draws]}\ubb34, \uc2b9\ub960 ${fmtRate(leader[COL.winRate])}` : "-";
  $("streakTeam").textContent = streak ? streak[COL.team] : "-";
  $("streakText").textContent = streak ? streak[COL.streak] : "-";
  $("recentBest").textContent = recent ? recent[COL.team] : "-";
  $("hotPlayer").textContent = hot ? hot[COL.player] : "-";
  $("hotPlayerText").textContent = hot ? `${hot[COL.team]} · WAR proxy ${fmtOne(playerWar(hot))}` : "-";
  $("warRiser").textContent = hot ? hot[COL.player] : "\uae40\ub3c4\uc601";
  $("hrPace").textContent = hr ? `${hr[COL.player]} · ${hr.HR} HR` : "\ub178\uc2dc\ud658";
  renderTodayGames();
}

function renderTodayGames() {
  const today = new Date().toISOString().slice(0, 10);
  let label = "\uc624\ub298";
  let games = state.schedule.filter((game) => game.Date === today);

  if (!games.length) {
    games = [...state.schedule]
      .filter((game) => game.Date >= today)
      .sort((a, b) => `${a.Date} ${a.Time}`.localeCompare(`${b.Date} ${b.Time}`))
      .slice(0, 5);
    label = games[0] ? games[0].Date : "\uc608\uc815";
  }

  $("todayGame").textContent = games.length ? `${label} ${games.length}\uacbd\uae30` : "\uc77c\uc815 \uc900\ube44 \uc911";
  $("todayGameText").textContent = games.length
    ? "\uc2dc\uac04, \ub300\uc9c4, \uad6c\uc7a5\uc744 KBO \uc77c\uc815 CSV\uc5d0\uc11c \ud45c\uc2dc"
    : "KBO \uc77c\uc815 CSV\ub97c \ucd94\uac00\ud558\uba74 \ud45c\uc2dc\ub429\ub2c8\ub2e4.";
  $("todayGameList").innerHTML = games
    .map((game) => {
      const score = Number.isFinite(game.away_score) && Number.isFinite(game.home_score)
        ? `<strong>${fmtInt(game.away_score)}:${fmtInt(game.home_score)}</strong>`
        : `<strong>${game.Time || "-"}</strong>`;
      return `<div class="schedule-row"><span>${game.away_team} vs ${game.home_team}</span>${score}<small>${game.Ballpark || ""}</small></div>`;
    })
    .join("");
}

function renderTeamOptions() {
  const teams = state.standings.map((row) => row[COL.team]).filter(Boolean);
  const options = [`<option value="all">\uc804\uccb4</option>`, ...teams.map((team) => `<option value="${team}">${team}</option>`)];
  $("teamSelect").innerHTML = options.join("");
  $("teamSelect").value = teams.includes(state.team) ? state.team : "all";
  if (!teams.includes(state.team)) state.team = "all";

  $("quickTeams").innerHTML = teams
    .slice(0, 6)
    .map((team) => `<button class="${team === state.team ? "active" : ""}" data-team="${team}">${team}</button>`)
    .join("");
  document.querySelectorAll("[data-team]").forEach((button) => {
    button.addEventListener("click", () => {
      state.team = button.dataset.team;
      $("teamSelect").value = state.team;
      renderTeamSections();
      renderTeamOptions();
    });
  });
}

function renderTeamSections() {
  renderRankTrend();
  renderMonthlyWinRate();
  renderRunDiff();
  renderHomeAway();
}

function renderRankTrend() {
  const svg = $("rankTrendSvg");
  const width = svg.clientWidth || 900;
  const height = 360;
  const pad = { top: 26, right: 42, bottom: 42, left: 44 };
  if (renderRankHistoryTrend(svg, width, height, pad)) return;

  const rows = filteredStandings();
  const months = ["4M", "5M", "6M", "7M"];
  const maxRank = Math.max(10, ...state.standings.map((row) => row[COL.rank] || 0));
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  if (!rows.length) {
    svg.innerHTML = emptyText(width, height, "No standings data");
    return;
  }

  const x = scale([0, months.length - 1], [pad.left, width - pad.right]);
  const y = scale([1, maxRank], [pad.top, height - pad.bottom]);
  const ticks = Array.from({ length: Math.min(maxRank, 10) }, (_, index) => index + 1);

  svg.innerHTML = `
    ${ticks.map((rank) => `<line class="grid-line" x1="${pad.left}" x2="${width - pad.right}" y1="${y(rank)}" y2="${y(rank)}"></line><text class="tick-label" x="16" y="${y(rank) + 4}">${rank}</text>`).join("")}
    ${months.map((month, index) => `<text class="tick-label" x="${x(index)}" y="${height - 15}" text-anchor="middle">${month}</text>`).join("")}
    ${rows.map((row) => {
      const ranks = makeRankHistory(row, maxRank);
      const path = ranks.map((rank, index) => `${index ? "L" : "M"}${x(index)},${y(rank)}`).join(" ");
      return `<path class="rank-line" d="${path}" stroke="${teamColor(row[COL.team])}"></path>${ranks.map((rank, index) => `<circle cx="${x(index)}" cy="${y(rank)}" r="4.5" fill="${teamColor(row[COL.team])}"></circle>`).join("")}<text class="tick-label" x="${width - pad.right + 5}" y="${y(ranks.at(-1)) + 4}">${row[COL.team]}</text>`;
    }).join("")}
  `;
  $("selectedTeamPill").textContent = state.team === "all" ? "\uc804\uccb4" : state.team;
}

function renderRankHistoryTrend(svg, width, height, pad) {
  const history = state.rankHistory.filter((row) => state.team === "all" || row[COL.team] === state.team);
  const dates = [...new Set(history.map((row) => row.Date).filter(Boolean))].sort();
  if (dates.length < 2) return false;

  const rowsByTeam = new Map();
  history.forEach((row) => {
    if (!rowsByTeam.has(row[COL.team])) rowsByTeam.set(row[COL.team], []);
    rowsByTeam.get(row[COL.team]).push(row);
  });

  const maxRank = Math.max(10, ...history.map((row) => row[COL.rank] || 0));
  const x = scale([0, dates.length - 1], [pad.left, width - pad.right]);
  const y = scale([1, maxRank], [pad.top, height - pad.bottom]);
  const dateIndex = new Map(dates.map((date, index) => [date, index]));
  const ticks = Array.from({ length: Math.min(maxRank, 10) }, (_, index) => index + 1);

  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.innerHTML = `
    ${ticks.map((rank) => `<line class="grid-line" x1="${pad.left}" x2="${width - pad.right}" y1="${y(rank)}" y2="${y(rank)}"></line><text class="tick-label" x="16" y="${y(rank) + 4}">${rank}</text>`).join("")}
    ${dates.map((date, index) => `<text class="tick-label" x="${x(index)}" y="${height - 15}" text-anchor="middle">${date.slice(5)}</text>`).join("")}
    ${[...rowsByTeam.entries()].map(([team, rows]) => {
      const sorted = [...rows].sort((a, b) => String(a.Date).localeCompare(String(b.Date)));
      const path = sorted.map((row, index) => `${index ? "L" : "M"}${x(dateIndex.get(row.Date))},${y(row[COL.rank])}`).join(" ");
      const last = sorted.at(-1);
      return `<path class="rank-line" d="${path}" stroke="${teamColor(team)}"></path>${sorted.map((row) => `<circle cx="${x(dateIndex.get(row.Date))}" cy="${y(row[COL.rank])}" r="4.5" fill="${teamColor(team)}"></circle>`).join("")}<text class="tick-label" x="${width - pad.right + 5}" y="${y(last[COL.rank]) + 4}">${team}</text>`;
    }).join("")}
  `;
  $("selectedTeamPill").textContent = state.team === "all" ? "\uc804\uccb4" : state.team;
  return true;
}

function renderMonthlyWinRate() {
  const svg = $("monthlyWinSvg");
  const width = svg.clientWidth || 440;
  const height = 320;
  const pad = { top: 28, right: 20, bottom: 36, left: 42 };
  const row = teamRow();
  const monthlyRows = teamMonthlyRows();
  const values = monthlyRows.length ? monthlyRows.map((item) => item.WinRate || 0) : row ? makeMonthlyWinRate(row) : [];
  const labels = monthlyRows.length ? monthlyRows.map((item) => `${item.Month}M`) : ["4M", "5M", "6M", "7M"];
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  if (!row) {
    svg.innerHTML = emptyText(width, height, "Select a team");
    return;
  }
  const xStep = (width - pad.left - pad.right) / values.length;
  const y = scale([0, 0.75], [height - pad.bottom, pad.top]);
  svg.innerHTML = values
    .map((value, index) => {
      const barHeight = height - pad.bottom - y(value);
      const x = pad.left + index * xStep + 12;
      return `<rect x="${x}" y="${y(value)}" width="${Math.max(24, xStep - 24)}" height="${barHeight}" rx="5" fill="${teamColor(row[COL.team])}"></rect><text class="tick-label" x="${x + (xStep - 24) / 2}" y="${height - 14}" text-anchor="middle">${labels[index]}</text><text class="tick-label" x="${x + (xStep - 24) / 2}" y="${y(value) - 8}" text-anchor="middle">${fmtRate(value)}</text>`;
    })
    .join("");
}

function renderRunDiff() {
  const svg = $("runDiffSvg");
  const width = svg.clientWidth || 440;
  const height = 320;
  const row = teamRow();
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  if (!row) {
    svg.innerHTML = emptyText(width, height, "Select a team");
    return;
  }
  const games = teamGameRows();
  const scored = games.length
    ? sum(games.map((game) => game.RunsFor))
    : Math.round((row[COL.wins] * 5.2 + row[COL.losses] * 3.4 + row[COL.draws] * 4.1));
  const allowed = games.length
    ? sum(games.map((game) => game.RunsAgainst))
    : Math.round((row[COL.losses] * 5.0 + row[COL.wins] * 3.6 + row[COL.draws] * 4.1));
  const max = Math.max(scored, allowed, 1);
  svg.innerHTML = `
    ${metricBarSvg("RS", scored, max, 70, "#0b7f74", width)}
    ${metricBarSvg("RA", allowed, max, 160, "#d05240", width)}
    <text class="big-number" x="28" y="250">+${scored - allowed}</text>
    <text class="tick-label" x="28" y="272">${games.length ? "run differential from game results" : "run differential proxy"}</text>
  `;
}

function renderHomeAway() {
  const row = teamRow();
  if (!row) {
    $("homeAwayBars").innerHTML = `<p class="muted">Select one team to compare home and away records.</p>`;
    return;
  }
  const games = teamGameRows();
  const home = games.length ? summarizeGameRecord(games.filter((game) => game.HomeAway === "home")) : parseRecord(row[COL.home]);
  const away = games.length ? summarizeGameRecord(games.filter((game) => game.HomeAway === "away")) : parseRecord(row[COL.away]);
  const homeRate = recordRate(home);
  const awayRate = recordRate(away);
  const max = Math.max(homeRate, awayRate, 1);
  $("homeAwayBars").innerHTML = [
    { label: "Home", value: homeRate, record: formatRecord(home), color: "#0b7f74" },
    { label: "Away", value: awayRate, record: formatRecord(away), color: "#2e65b8" },
  ]
    .map((item) => `<div class="bar-row"><strong>${item.label}</strong><span class="bar-track"><span class="bar-fill" style="width:${(item.value / max) * 100}%; background:${item.color}"></span></span><span>${fmtRate(item.value)}</span><small>${item.record}</small></div>`)
    .join("");
}

function renderPlayerSections() {
  const player = state.selectedPlayer || state.hitters[0];
  if (!player) {
    $("playerCard").innerHTML = `<p class="muted">No player data.</p>`;
    $("playerMetricBars").innerHTML = "";
    return;
  }
  const metrics = playerMetrics(player);
  $("playerCard").innerHTML = `
    <p class="eyebrow">Player Card</p>
    <h3>${player[COL.player]}</h3>
    <p class="muted">${player[COL.team]} · ${state.season}</p>
    <div class="stat-grid">
      <div class="stat-box"><span>WAR</span><strong>${fmtOne(metrics.war)}</strong></div>
      <div class="stat-box"><span>OPS</span><strong>${fmtRate(metrics.ops)}</strong></div>
      <div class="stat-box"><span>AVG</span><strong>${fmtRate(metrics.avg)}</strong></div>
      <div class="stat-box"><span>OBP</span><strong>${fmtRate(metrics.obp)}</strong></div>
      <div class="stat-box"><span>SLG</span><strong>${fmtRate(metrics.slg)}</strong></div>
    </div>
  `;
  const maxValues = { war: 8, ops: 1.1, avg: 0.4, obp: 0.5, slg: 0.7 };
  $("playerMetricBars").innerHTML = [
    ["WAR", metrics.war, maxValues.war, fmtOne],
    ["OPS", metrics.ops, maxValues.ops, fmtRate],
    ["AVG", metrics.avg, maxValues.avg, fmtRate],
    ["OBP", metrics.obp, maxValues.obp, fmtRate],
    ["SLG", metrics.slg, maxValues.slg, fmtRate],
  ].map(([label, value, max, formatter]) => `<div class="metric-row"><span>${label}</span><strong>${formatter(value)}</strong><i><b style="width:${clamp((value / max) * 100, 2, 100)}%"></b></i></div>`).join("");
}

function renderCompareOptions() {
  const top = [...state.hitters].sort((a, b) => playerWar(b) - playerWar(a)).slice(0, 40);
  const options = top.map((player) => `<option value="${player[COL.player]}">${player[COL.player]} · ${player[COL.team]}</option>`).join("");
  $("compareA").innerHTML = options;
  $("compareB").innerHTML = options;
  if (top[0]) $("compareA").value = top[0][COL.player];
  if (top[1]) $("compareB").value = top[1][COL.player];
}

function renderCompare() {
  const a = findExactPlayer($("compareA").value) || state.hitters[0];
  const b = findExactPlayer($("compareB").value) || state.hitters[1] || a;
  renderRadar(a, b);
  if (!a || !b) return;
  const am = playerMetrics(a);
  const bm = playerMetrics(b);
  $("compareSummary").innerHTML = `
    <h3>${a[COL.player]} vs ${b[COL.player]}</h3>
    ${compareLine("WAR", am.war, bm.war, fmtOne)}
    ${compareLine("OPS", am.ops, bm.ops, fmtRate)}
    ${compareLine("HR", a.HR || 0, b.HR || 0, fmtInt)}
    ${compareLine("RBI", a.RBI || 0, b.RBI || 0, fmtInt)}
  `;
}

function renderRadar(a, b) {
  const svg = $("radarSvg");
  const width = svg.clientWidth || 560;
  const height = 360;
  const center = { x: width / 2, y: height / 2 + 10 };
  const radius = Math.min(width, height) * 0.33;
  const axes = ["WAR", "OPS", "HR", "RBI"];
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  if (!a || !b) {
    svg.innerHTML = emptyText(width, height, "No compare data");
    return;
  }
  const max = {
    war: Math.max(playerWar(a), playerWar(b), 1),
    ops: Math.max(playerMetrics(a).ops, playerMetrics(b).ops, 1),
    hr: Math.max(a.HR || 0, b.HR || 0, 1),
    rbi: Math.max(a.RBI || 0, b.RBI || 0, 1),
  };
  const valuesA = [playerWar(a) / max.war, playerMetrics(a).ops / max.ops, (a.HR || 0) / max.hr, (a.RBI || 0) / max.rbi];
  const valuesB = [playerWar(b) / max.war, playerMetrics(b).ops / max.ops, (b.HR || 0) / max.hr, (b.RBI || 0) / max.rbi];
  const points = (values) => values.map((value, index) => radarPoint(index, axes.length, radius * value, center)).join(" ");
  svg.innerHTML = `
    ${[0.33, 0.66, 1].map((ratio) => `<polygon points="${points([ratio, ratio, ratio, ratio])}" fill="none" stroke="var(--line)"></polygon>`).join("")}
    ${axes.map((axis, index) => {
      const [x, y] = radarPoint(index, axes.length, radius + 18, center).split(",");
      return `<text class="tick-label" x="${x}" y="${Number(y) + 4}" text-anchor="middle">${axis}</text>`;
    }).join("")}
    <polygon points="${points(valuesA)}" fill="rgba(11,127,116,0.24)" stroke="#0b7f74" stroke-width="3"></polygon>
    <polygon points="${points(valuesB)}" fill="rgba(208,82,64,0.18)" stroke="#d05240" stroke-width="3"></polygon>
    <text class="legend" x="18" y="26" fill="#0b7f74">${a[COL.player]}</text>
    <text class="legend" x="18" y="48" fill="#d05240">${b[COL.player]}</text>
  `;
}

function compareLine(label, a, b, formatter) {
  return `<div class="compare-line"><span>${label}</span><strong>${formatter(a)}</strong><i>${formatter(b)}</i></div>`;
}

function filteredStandings() {
  return state.team === "all" ? state.standings : state.standings.filter((row) => row[COL.team] === state.team);
}

function teamRow() {
  if (state.team !== "all") return state.standings.find((row) => row[COL.team] === state.team);
  return [...state.standings].sort((a, b) => a[COL.rank] - b[COL.rank])[0];
}

function activeTeam() {
  const row = teamRow();
  return row ? row[COL.team] : "";
}

function teamGameRows() {
  const team = activeTeam();
  return state.teamGames.filter((row) => row.Team === team);
}

function teamMonthlyRows() {
  const team = activeTeam();
  return state.teamMonthly
    .filter((row) => row.Team === team)
    .sort((a, b) => String(a.Month).localeCompare(String(b.Month)));
}

function summarizeGameRecord(rows) {
  return {
    wins: sum(rows.map((row) => row.Win)),
    losses: sum(rows.map((row) => row.Loss)),
    draws: sum(rows.map((row) => row.Draw)),
  };
}

function formatRecord(record) {
  return `${record.wins}-${record.draws}-${record.losses}`;
}

function findPlayer(query) {
  if (!query) return state.hitters[0] || null;
  return state.hitters.find((row) => row[COL.player] && row[COL.player].includes(query)) || state.hitters[0] || null;
}

function findExactPlayer(name) {
  return state.hitters.find((row) => row[COL.player] === name);
}

function makeRankHistory(row, maxRank) {
  const finalRank = row[COL.rank];
  const seed = stringSeed(row[COL.team]);
  const openingRank = clamp(finalRank + ((seed % 5) - 2), 1, maxRank);
  const mayRank = clamp(Math.round(openingRank * 0.62 + finalRank * 0.38 + ((seed % 3) - 1)), 1, maxRank);
  const juneRank = clamp(Math.round(openingRank * 0.25 + finalRank * 0.75 - (String(row[COL.streak]).includes("\uc2b9") ? 1 : 0)), 1, maxRank);
  return [openingRank, mayRank, juneRank, finalRank];
}

function makeMonthlyWinRate(row) {
  const base = row[COL.winRate] || 0;
  const seed = stringSeed(row[COL.team]);
  return [base - 0.06 + (seed % 3) * 0.012, base - 0.02, base + 0.015, base].map((value) => clamp(value, 0.2, 0.75));
}

function parseRecent(value) {
  const text = String(value || "");
  const wins = Number(text.match(/(\d+)\uc2b9/)?.[1] || 0);
  const draws = Number(text.match(/(\d+)\ubb34/)?.[1] || 0);
  const losses = Number(text.match(/(\d+)\ud328/)?.[1] || 0);
  return { wins, draws, losses };
}

function recentWinRate(value) {
  const record = parseRecent(value);
  const games = record.wins + record.losses;
  return games ? record.wins / games : 0;
}

function streakScore(value) {
  const text = String(value || "");
  const count = Number(text.match(/\d+/)?.[0] || 0);
  return text.includes("\uc2b9") ? count : -count;
}

function parseRecord(value) {
  const [wins, draws, losses] = String(value || "0-0-0").split("-").map(Number);
  return { wins: wins || 0, draws: draws || 0, losses: losses || 0 };
}

function recordRate(record) {
  const games = record.wins + record.losses;
  return games ? record.wins / games : 0;
}

function sum(values) {
  return values.filter(Number.isFinite).reduce((total, value) => total + value, 0);
}

function playerMetrics(player) {
  const obp = estimateObp(player);
  const slg = estimateSlg(player);
  return {
    war: playerWar(player),
    ops: obp + slg,
    avg: player.AVG || 0,
    obp,
    slg,
  };
}

function playerWar(player) {
  return Number.isFinite(player.XR) ? player.XR / 8 : 0;
}

function estimateObp(player) {
  const numerator = (player.H || 0) + (player.BB || 0) + (player.HBP || 0);
  const denominator = (player.AB || 0) + (player.BB || 0) + (player.HBP || 0);
  return denominator ? numerator / denominator : 0;
}

function estimateSlg(player) {
  const singles = (player.H || 0) - (player["2B"] || 0) - (player["3B"] || 0) - (player.HR || 0);
  const totalBases = singles + (player["2B"] || 0) * 2 + (player["3B"] || 0) * 3 + (player.HR || 0) * 4;
  return player.AB ? totalBases / player.AB : 0;
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

function metricBarSvg(label, value, max, y, color, width) {
  const barWidth = ((width - 150) * value) / max;
  return `<text class="tick-label" x="28" y="${y + 18}">${label}</text><rect x="70" y="${y}" width="${barWidth}" height="34" rx="7" fill="${color}"></rect><text class="tick-label" x="${80 + barWidth}" y="${y + 22}">${value}</text>`;
}

function scale(domain, range) {
  return (value) => range[0] + ((value - domain[0]) / (domain[1] - domain[0] || 1)) * (range[1] - range[0]);
}

function radarPoint(index, total, radius, center) {
  const angle = -Math.PI / 2 + (Math.PI * 2 * index) / total;
  return `${center.x + Math.cos(angle) * radius},${center.y + Math.sin(angle) * radius}`;
}

function stringSeed(value) {
  return String(value).split("").reduce((sum, char) => sum + char.charCodeAt(0), 0);
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function teamColor(team) {
  return TEAM_COLORS[team] || "#53636f";
}

function fmtRate(value) {
  return Number.isFinite(value) ? value.toFixed(3).replace(/^0/, "") : "-";
}

function fmtOne(value) {
  return Number.isFinite(value) ? value.toFixed(1) : "-";
}

function fmtInt(value) {
  return Number.isFinite(value) ? Math.round(value).toLocaleString("ko-KR") : "-";
}

function emptyText(width, height, text) {
  return `<text class="tick-label" x="${width / 2}" y="${height / 2}" text-anchor="middle">${text}</text>`;
}
