const RAW_ROOTS = ["../data/raw/kbo_official", "/data/raw/kbo_official", "./data/raw/kbo_official"];
const PROCESSED_ROOTS = ["../data/processed", "/data/processed", "./data/processed"];
const RAG_APIS = [
  `http://${window.location.hostname}:8001/api/rag/ask`,
  "http://127.0.0.1:8001/api/rag/ask",
  "http://localhost:8001/api/rag/ask",
];
const COL = { rank: "\uc21c\uc704", team: "\ud300\uba85", wins: "\uc2b9", losses: "\ud328", draws: "\ubb34", winRate: "\uc2b9\ub960", recent: "\ucd5c\uadfc10\uacbd\uae30", streak: "\uc5f0\uc18d" };
const state = { season: 2026, standings: [], games: [], hitters: [] };
const $ = (id) => document.getElementById(id);

init();

async function init() {
  $("askButton").addEventListener("click", answerQuestion);
  document.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => {
      const map = {
        "why-team": "\uc65c LG\uac00 \uac15\ud558\uc9c0?",
        mvp: "\uc62c\ud574 MVP \ud6c4\ubcf4\ub294?",
        hot: "\uc9c0\uae08 \uac00\uc7a5 \ub728\uac70\uc6b4 \ud300\uc740?",
      };
      $("questionInput").value = map[button.dataset.question];
      answerQuestion();
    });
  });
  await loadData();
  $("questionInput").value = "\uc65c LG\uac00 \uac15\ud558\uc9c0?";
  answerQuestion();
}

async function loadData() {
  const [standingsText, gamesText, hittersText] = await Promise.all([
    fetchDataFile(`kbo_team_rank_${state.season}.csv`, RAW_ROOTS),
    fetchDataFile(`kbo_team_games_${state.season}.csv`, PROCESSED_ROOTS),
    fetchDataFile(`kbo_hitter_metrics_${state.season}.csv`, PROCESSED_ROOTS),
  ]);
  state.standings = standingsText ? parseCsv(standingsText).map(normalizeRow) : [];
  state.games = gamesText ? parseCsv(gamesText).map(normalizeRow) : [];
  state.hitters = hittersText ? parseCsv(hittersText).map(normalizeRow) : [];
  $("labNote").textContent = `${state.standings.length} teams · ${state.games.length} team-game rows · ${state.hitters.length} hitters`;
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

async function answerQuestion() {
  const question = $("questionInput").value.trim();
  if (await answerWithBackend(question)) return;
  if (question.includes("MVP") || question.includes("mvp")) return answerMvp();
  if (question.includes("\ub728\uac70\uc6b4") || question.includes("hot")) return answerHotTeam();
  return answerTeam(question);
}

async function answerWithBackend(question) {
  if (!question) return false;
  for (const url of RAG_APIS) {
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, season: state.season }),
      });
      if (!response.ok) continue;
      const data = await response.json();
      if (data.status !== "success") continue;
      $("answerTitle").textContent = data.answer.title || "-";
      $("answerBody").textContent = data.answer.summary || "-";
      const evidence = [
        ...(data.answer.bullets || []).map((item, index) => [`Answer ${index + 1}`, item]),
        ...(data.evidence || []).slice(0, 5).map((item) => [item.title, item.body]),
      ];
      renderEvidence(evidence);
      $("labNote").textContent = `RAG backend connected · ${Object.entries(data.data_sources || {}).map(([key, value]) => `${key}:${value}`).join(" · ")}`;
      return true;
    } catch {}
  }
  return false;
}

function answerTeam(question) {
  const team = state.standings.find((row) => question.includes(row[COL.team]))?.[COL.team] || state.standings[0]?.[COL.team];
  const standing = state.standings.find((row) => row[COL.team] === team);
  const games = state.games.filter((game) => game.Team === team);
  const runsFor = sum(games.map((game) => game.RunsFor));
  const runsAgainst = sum(games.map((game) => game.RunsAgainst));
  const diff = runsFor - runsAgainst;
  $("answerTitle").textContent = `${team}\ub294 \ud604\uc7ac ${standing?.[COL.rank] || "-"}\uc704, \ub4dd\uc2e4\ucc28 ${fmtSigned(diff)}\uc785\ub2c8\ub2e4.`;
  $("answerBody").textContent = `\uc2b9\ub960 ${fmtRate(standing?.[COL.winRate])}, ${standing?.[COL.recent] || "-"} \ud750\ub984\uc744 \uac19\uace0 \uc788\uc2b5\ub2c8\ub2e4. \ud604\uc7ac \ub370\ubaa8\uc5d0\uc11c\ub294 \ud300 \uc21c\uc704, \uacbd\uae30\ubcc4 \ub4dd\uc2e4, \ucd5c\uadfc 10\uacbd\uae30\ub97c \uadfc\uac70\ub85c \uc0ac\uc6a9\ud569\ub2c8\ub2e4.`;
  renderEvidence([
    ["Rank", `${standing?.[COL.rank] || "-"}\uc704`],
    ["Record", `${standing?.[COL.wins] || 0}-${standing?.[COL.draws] || 0}-${standing?.[COL.losses] || 0}`],
    ["Win rate", fmtRate(standing?.[COL.winRate])],
    ["Runs", `RF ${runsFor} / RA ${runsAgainst}`],
    ["Run diff", fmtSigned(diff)],
    ["Recent 10", standing?.[COL.recent] || "-"],
  ]);
}

function answerMvp() {
  const top = [...state.hitters].sort((a, b) => (b.WARProxy || 0) - (a.WARProxy || 0)).slice(0, 5);
  const leader = top[0];
  $("answerTitle").textContent = leader ? `${leader.Player}\uc774 \uac00\uc7a5 \uac15\ud55c MVP \ud6c4\ubcf4\uc785\ub2c8\ub2e4.` : "-";
  $("answerBody").textContent = leader ? `WARProxy ${fmtOne(leader.WARProxy)}, OPS ${fmtRate(leader.OPS)}, HR ${fmtInt(leader.HR)}, RBI ${fmtInt(leader.RBI)}\ub85c \ud0c0\uc790 \ud575\uc2ec \uc9c0\ud45c\uc5d0\uc11c \uc0c1\uc704\uad8c\uc785\ub2c8\ub2e4.` : "-";
  renderEvidence(top.map((player, index) => [`#${index + 1} ${player.Player}`, `${player.Team} · WARProxy ${fmtOne(player.WARProxy)} · OPS ${fmtRate(player.OPS)}`]));
}

function answerHotTeam() {
  const ranked = state.standings.map((row) => ({ team: row[COL.team], rate: recentWinRate(row[COL.recent]), recent: row[COL.recent], streak: row[COL.streak] })).sort((a, b) => b.rate - a.rate);
  const top = ranked[0];
  $("answerTitle").textContent = top ? `${top.team}\uc774 \ucd5c\uadfc \uac00\uc7a5 \ub728\uac81\uc2b5\ub2c8\ub2e4.` : "-";
  $("answerBody").textContent = top ? `\ucd5c\uadfc 10\uacbd\uae30 ${top.recent}, \uc2b9\ub960 ${fmtRate(top.rate)}, \uc5f0\uc18d ${top.streak}\uc785\ub2c8\ub2e4.` : "-";
  renderEvidence(ranked.slice(0, 5).map((row, index) => [`#${index + 1} ${row.team}`, `${row.recent} · ${fmtRate(row.rate)} · ${row.streak}`]));
}

function renderEvidence(items) {
  $("evidenceList").innerHTML = items.map(([label, value]) => `<div class="evidence-row"><span>${label}</span><strong>${value}</strong></div>`).join("");
}

function parseRecent(value) { const text = String(value || ""); return { wins: Number(text.match(/(\d+)\uc2b9/)?.[1] || 0), losses: Number(text.match(/(\d+)\ud328/)?.[1] || 0) }; }
function recentWinRate(value) { const record = parseRecent(value); const games = record.wins + record.losses; return games ? record.wins / games : 0; }
function parseCsv(text) { const rows = []; let row = []; let cell = ""; let quoted = false; for (let index = 0; index < text.length; index++) { const char = text[index]; const next = text[index + 1]; if (char === '"' && quoted && next === '"') { cell += '"'; index++; } else if (char === '"') { quoted = !quoted; } else if (char === "," && !quoted) { row.push(cell); cell = ""; } else if ((char === "\n" || char === "\r") && !quoted) { if (char === "\r" && next === "\n") index++; row.push(cell); if (row.some(Boolean)) rows.push(row); row = []; cell = ""; } else { cell += char; } } if (cell || row.length) { row.push(cell); rows.push(row); } const headers = (rows.shift() || []).map((header) => header.replace(/^\uFEFF/, "")); return rows.map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]))); }
function normalizeRow(row) { const normalized = { ...row }; Object.entries(normalized).forEach(([key, value]) => { const number = Number(String(value).replace(/,/g, "")); if (value !== "" && Number.isFinite(number)) normalized[key] = number; }); return normalized; }
function sum(values) { return values.filter(Number.isFinite).reduce((total, value) => total + value, 0); }
function fmtRate(value) { return Number.isFinite(value) ? value.toFixed(3).replace(/^0/, "") : "-"; }
function fmtOne(value) { return Number.isFinite(value) ? value.toFixed(1) : "-"; }
function fmtInt(value) { return Number.isFinite(value) ? Math.round(value).toLocaleString("ko-KR") : "-"; }
function fmtSigned(value) { if (!Number.isFinite(value)) return "-"; return value > 0 ? `+${fmtInt(value)}` : fmtInt(value); }
