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
};

const state = {
  season: 2026,
  view: "overall",
  standings: [],
  rankHistory: [],
  teamGames: [],
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
    await loadSeason();
    render();
  });

  $("viewSelect").addEventListener("change", (event) => {
    state.view = event.target.value;
    render();
  });
}

async function loadSeason() {
  const [standingsText, historyText, gamesText] = await Promise.all([
    fetchDataFile(`kbo_team_rank_${state.season}.csv`, DATA_ROOTS),
    fetchDataFile(`kbo_team_rank_history_${state.season}.csv`, DATA_ROOTS),
    fetchDataFile(`kbo_team_games_${state.season}.csv`, PROCESSED_ROOTS),
  ]);

  state.standings = standingsText ? parseCsv(standingsText).map(normalizeRow) : [];
  state.rankHistory = historyText ? parseCsv(historyText).map(normalizeRow) : [];
  state.teamGames = gamesText ? parseCsv(gamesText).map(normalizeRow) : [];
}

async function fetchDataFile(fileName, roots) {
  for (const root of roots) {
    try {
      const response = await fetch(`${root}/${fileName}`);
      if (response.ok) return response.text();
    } catch {
      // Try next root.
    }
  }
  return null;
}

function render() {
  const rows = standingsRows();
  renderSummary(rows);
  renderTable(rows);
  renderRankTrend();
  renderRecentForms(rows);
  $("standingsNote").textContent = state.standings.length
    ? `${state.season} season · ${state.standings.length} teams`
    : `${state.season} season standings are not available`;
}

function standingsRows() {
  const base = state.standings.map((row) => {
    const games = state.teamGames.filter((game) => game.Team === row[COL.team]);
    const totals = summarizeGames(games);
    return {
      ...row,
      RunsFor: totals.runsFor,
      RunsAgainst: totals.runsAgainst,
      RunDiff: totals.runDiff,
      RecentRate: recentWinRate(row[COL.recent]),
    };
  });

  if (state.view === "recent") {
    return [...base].sort((a, b) => b.RecentRate - a.RecentRate || a[COL.rank] - b[COL.rank]);
  }
  if (state.view === "home" || state.view === "away") {
    return [...base].sort((a, b) => {
      const ar = recordRate(parseRecord(a[state.view === "home" ? COL.home : COL.away]));
      const br = recordRate(parseRecord(b[state.view === "home" ? COL.home : COL.away]));
      return br - ar || a[COL.rank] - b[COL.rank];
    });
  }
  return [...base].sort((a, b) => a[COL.rank] - b[COL.rank]);
}

function renderSummary(rows) {
  const leader = [...state.standings].sort((a, b) => a[COL.rank] - b[COL.rank])[0];
  const recent = [...rows].sort((a, b) => b.RecentRate - a.RecentRate)[0];
  const diff = [...rows].sort((a, b) => b.RunDiff - a.RunDiff)[0];

  $("leaderTeam").textContent = leader ? `${leader[COL.rank]}\uc704 ${leader[COL.team]}` : "-";
  $("leaderText").textContent = leader ? `${leader[COL.wins]}\uc2b9 ${leader[COL.losses]}\ud328 · ${fmtRate(leader[COL.winRate])}` : "-";
  $("recentTeam").textContent = recent ? recent[COL.team] : "-";
  $("recentText").textContent = recent ? `${recent[COL.recent]} · ${fmtRate(recent.RecentRate)}` : "-";
  $("runDiffTeam").textContent = diff ? diff[COL.team] : "-";
  $("runDiffText").textContent = diff ? `${fmtSigned(diff.RunDiff)} runs` : "-";
}

function renderTable(rows) {
  $("standingsBody").innerHTML = rows
    .map((row, index) => `
      <tr>
        <td><span class="rank-badge">${state.view === "overall" ? row[COL.rank] : index + 1}</span></td>
        <td>
          <div class="team-cell">
            <span class="team-rail" style="background:${teamColor(row[COL.team])}"></span>
            <div>
              <strong>${row[COL.team]}</strong>
              <small>${row[COL.games]}\uacbd\uae30 · GB ${row[COL.gb]}</small>
            </div>
          </div>
        </td>
        <td>${row[COL.games]}</td>
        <td>${row[COL.wins]}</td>
        <td>${row[COL.losses]}</td>
        <td>${row[COL.draws]}</td>
        <td><span class="rate-pill">${fmtRate(row[COL.winRate])}</span></td>
        <td>${row[COL.gb]}</td>
        <td>${fmtInt(row.RunsFor)}</td>
        <td>${fmtInt(row.RunsAgainst)}</td>
        <td><span class="diff-pill ${row.RunDiff >= 0 ? "positive" : "negative"}">${fmtSigned(row.RunDiff)}</span></td>
        <td><span class="streak-pill ${String(row[COL.streak]).includes("\uc2b9") ? "win-streak" : "loss-streak"}">${row[COL.streak]}</span></td>
        <td><div class="mini-form">${recentTokens(row[COL.recent]).map((token) => `<span class="mini-token ${tokenClass(token)}">${token}</span>`).join("")}</div></td>
      </tr>
    `)
    .join("");
}

function renderRankTrend() {
  const svg = $("rankTrendSvg");
  const width = svg.clientWidth || 560;
  const height = 340;
  const pad = { top: 26, right: 42, bottom: 42, left: 44 };
  const history = state.rankHistory;
  const dates = [...new Set(history.map((row) => row.Date).filter(Boolean))].sort();
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  if (dates.length < 2) {
    svg.innerHTML = emptyText(width, height, "Two or more daily snapshots are needed");
    return;
  }

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

  svg.innerHTML = `
    ${ticks.map((rank) => `<line class="grid-line" x1="${pad.left}" x2="${width - pad.right}" y1="${y(rank)}" y2="${y(rank)}"></line><text class="tick-label" x="16" y="${y(rank) + 4}">${rank}</text>`).join("")}
    ${dates.map((date, index) => `<text class="tick-label" x="${x(index)}" y="${height - 15}" text-anchor="middle">${date.slice(5)}</text>`).join("")}
    ${[...rowsByTeam.entries()].map(([team, rows]) => {
      const sorted = [...rows].sort((a, b) => String(a.Date).localeCompare(String(b.Date)));
      const path = sorted.map((row, index) => `${index ? "L" : "M"}${x(dateIndex.get(row.Date))},${y(row[COL.rank])}`).join(" ");
      const last = sorted.at(-1);
      return `<path class="rank-line" d="${path}" stroke="${teamColor(team)}"></path>${sorted.map((row) => `<circle cx="${x(dateIndex.get(row.Date))}" cy="${y(row[COL.rank])}" r="4" fill="${teamColor(team)}"></circle>`).join("")}<text class="tick-label" x="${width - pad.right + 5}" y="${y(last[COL.rank]) + 4}">${team}</text>`;
    }).join("")}
  `;
}

function renderRecentForms(rows) {
  $("recentFormList").innerHTML = rows
    .map((row) => {
      const tokens = recentTokens(row[COL.recent]);
      return `<div class="form-card"><div class="form-head"><strong>${row[COL.team]}</strong><span>${row[COL.recent]}</span></div><div class="tokens">${tokens.map((token) => `<span class="token ${tokenClass(token)}">${token}</span>`).join("")}</div></div>`;
    })
    .join("");
}

function summarizeGames(games) {
  return {
    runsFor: sum(games.map((game) => game.RunsFor)),
    runsAgainst: sum(games.map((game) => game.RunsAgainst)),
    runDiff: sum(games.map((game) => game.RunDiff)),
  };
}

function parseRecent(value) {
  const text = String(value || "");
  return {
    wins: Number(text.match(/(\d+)\uc2b9/)?.[1] || 0),
    draws: Number(text.match(/(\d+)\ubb34/)?.[1] || 0),
    losses: Number(text.match(/(\d+)\ud328/)?.[1] || 0),
  };
}

function recentWinRate(value) {
  const record = parseRecent(value);
  const games = record.wins + record.losses;
  return games ? record.wins / games : 0;
}

function recentTokens(value) {
  const record = parseRecent(value);
  return [...Array(record.wins).fill("W"), ...Array(record.draws).fill("D"), ...Array(record.losses).fill("L")].slice(0, 10);
}

function parseRecord(value) {
  const [wins, draws, losses] = String(value || "0-0-0").split("-").map(Number);
  return { wins: wins || 0, draws: draws || 0, losses: losses || 0 };
}

function recordRate(record) {
  const games = record.wins + record.losses;
  return games ? record.wins / games : 0;
}

function tokenClass(token) {
  return token === "W" ? "win" : token === "L" ? "loss" : "draw";
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

function scale(domain, range) {
  return (value) => range[0] + ((value - domain[0]) / (domain[1] - domain[0] || 1)) * (range[1] - range[0]);
}

function sum(values) {
  return values.filter(Number.isFinite).reduce((total, value) => total + value, 0);
}

function teamColor(team) {
  return TEAM_COLORS[team] || "#53636f";
}

function fmtRate(value) {
  return Number.isFinite(value) ? value.toFixed(3).replace(/^0/, "") : "-";
}

function fmtInt(value) {
  return Number.isFinite(value) ? Math.round(value).toLocaleString("ko-KR") : "-";
}

function fmtSigned(value) {
  if (!Number.isFinite(value)) return "-";
  return value > 0 ? `+${fmtInt(value)}` : fmtInt(value);
}

function emptyText(width, height, text) {
  return `<text class="tick-label" x="${width / 2}" y="${height / 2}" text-anchor="middle">${text}</text>`;
}
