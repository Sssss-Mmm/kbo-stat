const DATA_ROOTS = ["../data/raw/kbo_official", "/data/raw/kbo_official", "./data/raw/kbo_official"];
const YEARS = Array.from({ length: 45 }, (_, i) => 2026 - i);
const TEAM_COLORS = [
  "#1f8a70",
  "#c7503a",
  "#2f5f9f",
  "#b58621",
  "#7b5cc7",
  "#2d9cdb",
  "#cc4b7a",
  "#5c7f36",
  "#de7c23",
  "#53636f",
];
const FALLBACK_STANDINGS = {
  2026: [
    { Season: 2026, "순위": 1, "팀명": "LG", "경기": 57, "승": 36, "패": 21, "무": 0, "승률": 0.632, "게임차": 0, "최근10경기": "8승0무2패", "연속": "2승", "홈": "19-0-10", "방문": "17-0-11" },
    { Season: 2026, "순위": 2, "팀명": "KT", "경기": 58, "승": 34, "패": 23, "무": 1, "승률": 0.596, "게임차": 2, "최근10경기": "6승0무4패", "연속": "1승", "홈": "16-0-13", "방문": "18-1-10" },
    { Season: 2026, "순위": 3, "팀명": "삼성", "경기": 56, "승": 32, "패": 23, "무": 1, "승률": 0.582, "게임차": 3, "최근10경기": "5승0무5패", "연속": "3패", "홈": "16-1-13", "방문": "16-0-10" },
    { Season: 2026, "순위": 4, "팀명": "KIA", "경기": 58, "승": 31, "패": 26, "무": 1, "승률": 0.544, "게임차": 5, "최근10경기": "6승0무4패", "연속": "2승", "홈": "18-1-10", "방문": "13-0-16" },
    { Season: 2026, "순위": 5, "팀명": "한화", "경기": 57, "승": 29, "패": 27, "무": 1, "승률": 0.518, "게임차": 6.5, "최근10경기": "6승1무3패", "연속": "2승", "홈": "12-0-16", "방문": "17-1-11" },
    { Season: 2026, "순위": 6, "팀명": "두산", "경기": 59, "승": 29, "패": 28, "무": 2, "승률": 0.509, "게임차": 7, "최근10경기": "7승1무2패", "연속": "4승", "홈": "18-1-11", "방문": "11-1-17" },
    { Season: 2026, "순위": 7, "팀명": "SSG", "경기": 58, "승": 25, "패": 32, "무": 1, "승률": 0.439, "게임차": 11, "최근10경기": "3승0무7패", "연속": "1패", "홈": "13-1-15", "방문": "12-0-17" },
    { Season: 2026, "순위": 8, "팀명": "NC", "경기": 56, "승": 24, "패": 31, "무": 1, "승률": 0.436, "게임차": 11, "최근10경기": "6승0무4패", "연속": "1패", "홈": "12-0-15", "방문": "12-1-16" },
    { Season: 2026, "순위": 9, "팀명": "롯데", "경기": 57, "승": 22, "패": 34, "무": 1, "승률": 0.393, "게임차": 13.5, "최근10경기": "3승0무7패", "연속": "3패", "홈": "8-0-19", "방문": "14-1-15" },
    { Season: 2026, "순위": 10, "팀명": "키움", "경기": 60, "승": 21, "패": 38, "무": 1, "승률": 0.356, "게임차": 16, "최근10경기": "1승0무9패", "연속": "4패", "홈": "13-1-16", "방문": "8-0-22" },
  ],
};

const state = {
  kind: "hitter",
  season: 2026,
  team: "all",
  query: "",
  metric: "AVG",
  data: new Map(),
  standings: new Map(),
  selected: null,
};

const $ = (id) => document.getElementById(id);

const configs = {
  hitter: {
    file: (year) => `kbo_${year}.csv`,
    defaultMetric: "AVG",
    metrics: ["AVG", "HR", "RBI", "SB", "XBH", "ISOP", "GPA", "XR"],
    lowerIsBetter: [],
    scatter: { x: "AVG", y: "ISOP", size: "PA", title: "파워 vs 컨택", hint: "X축 AVG, Y축 ISOP, 크기 PA" },
    cards: [
      { label: "리그 AVG", metric: "AVG", agg: "avg", format: fmtRate },
      { label: "홈런 1위", metric: "HR", agg: "maxPlayer", format: fmtInt },
      { label: "최다 안타", metric: "H", agg: "maxPlayer", format: fmtInt },
      { label: "평균 P/PA", metric: "P/PA", agg: "avg", format: fmtOne },
    ],
    table: ["순위", "선수명", "팀명", "AVG", "HR", "RBI", "SB", "ISOP", "GPA"],
    trendMetric: "AVG",
  },
  pitcher: {
    file: (year) => `kbo_pitcher_${year}.csv`,
    defaultMetric: "ERA",
    metrics: ["ERA", "W", "SO", "SV", "HLD", "K/9", "BB/9", "K/BB", "OPS"],
    lowerIsBetter: ["ERA", "BB/9", "OPS"],
    scatter: { x: "K/9", y: "BB/9", size: "IP_num", title: "탈삼진 vs 볼넷", hint: "X축 K/9, Y축 BB/9, 크기 이닝" },
    cards: [
      { label: "리그 ERA", metric: "ERA", agg: "avg", format: fmtTwo },
      { label: "다승 1위", metric: "W", agg: "maxPlayer", format: fmtInt },
      { label: "탈삼진 1위", metric: "SO", agg: "maxPlayer", format: fmtInt },
      { label: "평균 K/BB", metric: "K/BB", agg: "avg", format: fmtTwo },
    ],
    table: ["순위", "선수명", "팀명", "ERA", "W", "SV", "HLD", "SO", "K/BB"],
    trendMetric: "ERA",
  },
};

init();

async function init() {
  setupControls();
  await loadSeason(state.kind, state.season);
  render();
}

function setupControls() {
  $("seasonSelect").innerHTML = YEARS.map((year) => `<option value="${year}">${year} 시즌</option>`).join("");
  $("seasonSelect").value = state.season;

  $("seasonSelect").addEventListener("change", async (event) => {
    state.season = Number(event.target.value);
    state.selected = null;
    await loadSeason(state.kind, state.season);
    render();
  });

  document.querySelectorAll("[data-kind]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.kind = button.dataset.kind;
      state.metric = configs[state.kind].defaultMetric;
      state.team = "all";
      state.query = "";
      state.selected = null;
      $("searchInput").value = "";
      document.querySelectorAll("[data-kind]").forEach((btn) => {
        btn.classList.toggle("active", btn === button);
        btn.setAttribute("aria-selected", btn === button ? "true" : "false");
      });
      await loadSeason(state.kind, state.season);
      render();
    });
  });

  $("teamSelect").addEventListener("change", (event) => {
    state.team = event.target.value;
    state.selected = null;
    render();
  });

  $("searchInput").addEventListener("input", (event) => {
    state.query = event.target.value.trim();
    render();
  });

  $("themeToggle").addEventListener("click", () => {
    document.documentElement.classList.toggle("dark");
    $("themeIcon").textContent = document.documentElement.classList.contains("dark") ? "☀" : "☾";
  });

  document.querySelectorAll("[data-scroll-target]").forEach((button) => {
    button.addEventListener("click", () => {
      document.getElementById(button.dataset.scrollTarget).scrollIntoView({ behavior: "smooth", block: "start" });
      document.querySelectorAll(".nav-button").forEach((btn) => btn.classList.toggle("active", btn === button));
    });
  });
}

async function loadSeason(kind, year) {
  const key = `${kind}:${year}`;
  if (state.data.has(key)) return state.data.get(key);

  const text = await fetchDataFile(configs[kind].file(year));
  if (!text) {
    showDataError(`${year} ${kind === "hitter" ? "타자" : "투수"} CSV를 불러오지 못했습니다.`);
    state.data.set(key, []);
    return [];
  }
  const rows = parseCsv(text).map(normalizeRow);
  state.data.set(key, rows);
  return rows;
}

async function fetchDataFile(fileName) {
  for (const root of DATA_ROOTS) {
    try {
      const response = await fetch(`${root}/${fileName}`);
      if (response.ok) return response.text();
    } catch {
      // Try the next candidate root.
    }
  }
  return null;
}

function showDataError(message) {
  const note = $("dataNote");
  if (note) note.textContent = `${message} 서버를 레포 루트에서 실행해 주세요.`;
}

async function loadTrendData() {
  const years = YEARS.filter((year) => year <= state.season).slice(0, 12).reverse();
  const rows = [];
  for (const year of years) {
    try {
      const seasonRows = await loadSeason(state.kind, year);
      const metric = configs[state.kind].trendMetric;
      rows.push({ year, value: average(seasonRows.map((row) => row[metric])) });
    } catch {
      rows.push({ year, value: null });
    }
  }
  return rows.filter((row) => Number.isFinite(row.value));
}

async function loadStandings(year) {
  if (state.standings.has(year)) return state.standings.get(year);

  try {
    const text = await fetchDataFile(`kbo_team_rank_${year}.csv`);
    if (!text) throw new Error("missing standings");
    const rows = parseCsv(text).map(normalizeRow);
    state.standings.set(year, rows);
    return rows;
  } catch {
    const fallback = FALLBACK_STANDINGS[year] || [];
    state.standings.set(year, fallback);
    return fallback;
  }
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    const next = text[i + 1];
    if (char === '"' && quoted && next === '"') {
      cell += '"';
      i++;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (char === "," && !quoted) {
      row.push(cell);
      cell = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && next === "\n") i++;
      row.push(cell);
      if (row.some((value) => value !== "")) rows.push(row);
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
  const out = { ...row };
  for (const [key, value] of Object.entries(out)) {
    if (key === "선수명" || key === "팀명" || value === "-" || value === "") continue;
    const num = Number(String(value).replace(/,/g, ""));
    if (Number.isFinite(num)) out[key] = num;
  }
  if (typeof out.IP === "string") out.IP_num = parseInnings(out.IP);
  return out;
}

function parseInnings(value) {
  const [whole, fraction] = String(value).split(" ");
  const base = Number(whole) || 0;
  if (!fraction) return base;
  const [num, den] = fraction.split("/").map(Number);
  return base + (den ? num / den : 0);
}

function rowsForView() {
  const rows = state.data.get(`${state.kind}:${state.season}`) || [];
  return rows.filter((row) => {
    const teamOk = state.team === "all" || row["팀명"] === state.team;
    const queryOk = !state.query || String(row["선수명"]).includes(state.query);
    return teamOk && queryOk;
  });
}

function render() {
  const rows = rowsForView();
  renderTeamOptions();
  renderMetricPicker();
  renderOverview(rows);
  renderStandings();
  renderLeaders(rows);
  renderScatter(rows);
  renderTrend();
  renderTeams(rows);
}

function renderTeamOptions() {
  const allRows = state.data.get(`${state.kind}:${state.season}`) || [];
  const teams = [...new Set(allRows.map((row) => row["팀명"]))].sort();
  const current = state.team;
  $("teamSelect").innerHTML = `<option value="all">전체</option>${teams
    .map((team) => `<option value="${team}">${team}</option>`)
    .join("")}`;
  $("teamSelect").value = teams.includes(current) ? current : "all";
}

function renderMetricPicker() {
  const config = configs[state.kind];
  $("metricPicker").innerHTML = config.metrics
    .map((metric) => `<button class="${metric === state.metric ? "active" : ""}" data-metric="${metric}">${metric}</button>`)
    .join("");
  document.querySelectorAll("[data-metric]").forEach((button) => {
    button.addEventListener("click", () => {
      state.metric = button.dataset.metric;
      renderLeaders(rowsForView());
      renderMetricPicker();
    });
  });
}

function renderOverview(rows) {
  const config = configs[state.kind];
  $("snapshotTitle").textContent = `${state.season} ${state.kind === "hitter" ? "타자" : "투수"} 시즌 한눈에`;
  $("dataNote").textContent = `${rows.length.toLocaleString("ko-KR")}명 표시 중`;
  $("scatterTitle").textContent = config.scatter.title;
  $("scatterHint").textContent = config.scatter.hint;

  $("metricGrid").innerHTML = config.cards
    .map((card) => {
      const result = summarizeCard(rows, card);
      return `<article class="metric-card">
        <p class="label">${card.label}</p>
        <p class="value">${result.value}</p>
        <p class="sub">${result.sub}</p>
      </article>`;
    })
    .join("");
}

async function renderStandings() {
  const rows = await loadStandings(state.season);
  const columns = ["순위", "팀명", "경기", "승", "패", "무", "승률", "게임차", "연속"];

  $("standingsHead").innerHTML = `<tr>${columns.map((col) => `<th>${col}</th>`).join("")}</tr>`;

  if (!rows.length) {
    $("standingsNote").textContent = `${state.season} 구단 순위 CSV가 아직 없습니다.`;
    $("standingsBars").innerHTML = `<p class="muted">data/raw/kbo_official/kbo_team_rank_${state.season}.csv 파일을 추가하면 표시됩니다.</p>`;
    $("standingsBody").innerHTML = "";
    return;
  }

  const sorted = [...rows].sort((a, b) => Number(a["순위"]) - Number(b["순위"]));
  const maxWins = Math.max(...sorted.map((row) => row["승"]).filter(Number.isFinite), 1);
  $("standingsNote").textContent = `${sorted.length}개 구단 · 공식 순위표 기준`;
  $("standingsBars").innerHTML = sorted
    .map((row) => `<div class="bar-row">
      <strong>${row["팀명"]}</strong>
      <span class="bar-track"><span class="bar-fill" style="width:${((row["승"] || 0) / maxWins) * 100}%"></span></span>
      <span>${formatCell("승률", row["승률"])}</span>
    </div>`)
    .join("");
  $("standingsBody").innerHTML = sorted
    .map((row) => `<tr>${columns.map((col) => `<td>${formatCell(col, row[col])}</td>`).join("")}</tr>`)
    .join("");
}

function summarizeCard(rows, card) {
  const valid = rows.filter((row) => Number.isFinite(row[card.metric]));
  if (!valid.length) return { value: "-", sub: "데이터 없음" };
  if (card.agg === "avg") {
    return { value: card.format(average(valid.map((row) => row[card.metric]))), sub: `${valid.length}명 평균` };
  }
  const lower = configs[state.kind].lowerIsBetter.includes(card.metric);
  const sorted = [...valid].sort((a, b) => (lower ? a[card.metric] - b[card.metric] : b[card.metric] - a[card.metric]));
  const top = sorted[0];
  return { value: card.format(top[card.metric]), sub: `${top["선수명"]} · ${top["팀명"]}` };
}

function renderLeaders(rows) {
  const config = configs[state.kind];
  const metric = state.metric;
  const lower = config.lowerIsBetter.includes(metric);
  const leaders = rows
    .filter((row) => Number.isFinite(row[metric]))
    .sort((a, b) => (lower ? a[metric] - b[metric] : b[metric] - a[metric]))
    .slice(0, 10);
  const values = leaders.map((row) => row[metric]);
  const max = Math.max(...values.map(Math.abs), 1);

  $("leaderBars").innerHTML = leaders
    .map((row) => {
      const width = Math.max(4, (Math.abs(row[metric]) / max) * 100);
      return `<div class="bar-row">
        <strong>${row["선수명"]}</strong>
        <span class="bar-track"><span class="bar-fill" style="width:${width}%"></span></span>
        <span>${formatMetric(metric, row[metric])}</span>
      </div>`;
    })
    .join("");

  $("leaderHead").innerHTML = `<tr>${config.table.map((col) => `<th>${col}</th>`).join("")}</tr>`;
  $("leaderBody").innerHTML = rows
    .slice()
    .sort((a, b) => (lower ? a[metric] - b[metric] : b[metric] - a[metric]))
    .slice(0, 30)
    .map((row) => `<tr>${config.table.map((col) => `<td>${formatCell(col, row[col])}</td>`).join("")}</tr>`)
    .join("");
}

function renderScatter(rows) {
  const svg = $("scatterSvg");
  const { x, y, size } = configs[state.kind].scatter;
  const points = rows.filter((row) => Number.isFinite(row[x]) && Number.isFinite(row[y]));
  const width = svg.clientWidth || 820;
  const height = 460;
  const pad = { top: 24, right: 28, bottom: 48, left: 58 };
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  if (!points.length) {
    svg.innerHTML = `<text x="${width / 2}" y="${height / 2}" text-anchor="middle" class="tick-label">표시할 데이터가 없습니다</text>`;
    return;
  }

  const xScale = scale(extent(points, x), [pad.left, width - pad.right]);
  const yScale = scale(extent(points, y), [height - pad.bottom, pad.top]);
  const sizeExtent = extent(points.filter((row) => Number.isFinite(row[size])), size);

  const xTicks = ticks(xScale.domain, 5);
  const yTicks = ticks(yScale.domain, 5);
  const teamColor = colorByTeam(points);

  svg.innerHTML = `
    ${xTicks.map((tick) => `<line class="grid-line" x1="${xScale(tick)}" x2="${xScale(tick)}" y1="${pad.top}" y2="${height - pad.bottom}"></line><text class="tick-label" x="${xScale(tick)}" y="${height - 18}" text-anchor="middle">${formatMetric(x, tick)}</text>`).join("")}
    ${yTicks.map((tick) => `<line class="grid-line" x1="${pad.left}" x2="${width - pad.right}" y1="${yScale(tick)}" y2="${yScale(tick)}"></line><text class="tick-label" x="14" y="${yScale(tick) + 4}">${formatMetric(y, tick)}</text>`).join("")}
    <text class="tick-label" x="${width / 2}" y="${height - 4}" text-anchor="middle">${x}</text>
    <text class="tick-label" transform="translate(12 ${height / 2}) rotate(-90)" text-anchor="middle">${y}</text>
    ${points
      .map((row, index) => {
        const radius = Number.isFinite(row[size]) ? 4 + normalize(row[size], sizeExtent) * 8 : 5;
        const selected = state.selected === row;
        return `<circle class="player-dot" data-index="${index}" cx="${xScale(row[x])}" cy="${yScale(row[y])}" r="${selected ? radius + 2 : radius}" fill="${teamColor(row["팀명"])}" opacity="${selected ? 1 : 0.74}"></circle>`;
      })
      .join("")}
  `;

  svg.querySelectorAll(".player-dot").forEach((dot) => {
    const row = points[Number(dot.dataset.index)];
    dot.addEventListener("mousemove", (event) => showTooltip(event, row));
    dot.addEventListener("mouseleave", hideTooltip);
    dot.addEventListener("click", () => {
      state.selected = row;
      renderDetail(row);
      renderScatter(rowsForView());
    });
  });

  renderDetail(state.selected && rows.includes(state.selected) ? state.selected : points[0]);
}

async function renderTrend() {
  const rows = await loadTrendData();
  const svg = $("trendSvg");
  const width = svg.clientWidth || 780;
  const height = 360;
  const pad = { top: 28, right: 28, bottom: 44, left: 58 };
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  if (!rows.length) return;
  const yScale = scale([Math.min(...rows.map((row) => row.value)), Math.max(...rows.map((row) => row.value))], [height - pad.bottom, pad.top]);
  const xScale = scale([0, Math.max(rows.length - 1, 1)], [pad.left, width - pad.right]);
  const path = rows.map((row, index) => `${index ? "L" : "M"}${xScale(index)},${yScale(row.value)}`).join(" ");
  const metric = configs[state.kind].trendMetric;

  svg.innerHTML = `
    ${ticks(yScale.domain, 5).map((tick) => `<line class="grid-line" x1="${pad.left}" x2="${width - pad.right}" y1="${yScale(tick)}" y2="${yScale(tick)}"></line><text class="tick-label" x="12" y="${yScale(tick) + 4}">${formatMetric(metric, tick)}</text>`).join("")}
    <path d="${path}" fill="none" stroke="var(--accent-3)" stroke-width="3"></path>
    ${rows.map((row, index) => `<circle cx="${xScale(index)}" cy="${yScale(row.value)}" r="5" fill="var(--accent-2)"></circle><text class="tick-label" x="${xScale(index)}" y="${height - 16}" text-anchor="middle">${row.year}</text>`).join("")}
  `;
}

function renderTeams(rows) {
  const totals = [...rows.reduce((map, row) => map.set(row["팀명"], (map.get(row["팀명"]) || 0) + 1), new Map())]
    .sort((a, b) => b[1] - a[1]);
  const max = Math.max(...totals.map(([, count]) => count), 1);
  $("teamList").innerHTML = `<p class="eyebrow">Team Mix</p>${totals
    .map(([team, count], index) => `<div class="team-row">
      <span>${team}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${(count / max) * 100}%; background:${TEAM_COLORS[index % TEAM_COLORS.length]}"></span></span>
      <span>${count}명</span>
    </div>`)
    .join("")}`;
}

function renderDetail(row) {
  if (!row) return;
  const fields = state.kind === "hitter"
    ? ["팀명", "AVG", "HR", "RBI", "SB", "ISOP", "GPA", "XR"]
    : ["팀명", "ERA", "W", "SO", "SV", "HLD", "K/9", "BB/9", "K/BB"];
  $("detailPanel").innerHTML = `
    <p class="eyebrow">선수 상세</p>
    <h3>${row["선수명"]}</h3>
    ${fields.map((field) => `<div class="detail-stat"><span>${field}</span><strong>${formatCell(field, row[field])}</strong></div>`).join("")}
  `;
}

function showTooltip(event, row) {
  const tooltip = $("tooltip");
  tooltip.hidden = false;
  tooltip.innerHTML = `<strong>${row["선수명"]}</strong> · ${row["팀명"]}<br>${state.metric}: ${formatCell(state.metric, row[state.metric])}`;
  tooltip.style.left = `${event.clientX + 14}px`;
  tooltip.style.top = `${event.clientY + 14}px`;
}

function hideTooltip() {
  $("tooltip").hidden = true;
}

function colorByTeam(rows) {
  const teams = [...new Set(rows.map((row) => row["팀명"]))].sort();
  const map = new Map(teams.map((team, index) => [team, TEAM_COLORS[index % TEAM_COLORS.length]]));
  return (team) => map.get(team) || TEAM_COLORS[0];
}

function extent(rows, key) {
  const values = rows.map((row) => row[key]).filter(Number.isFinite);
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const pad = (max - min) * 0.08;
  return [min - pad, max + pad];
}

function scale(domain, range) {
  const fn = (value) => range[0] + ((value - domain[0]) / (domain[1] - domain[0] || 1)) * (range[1] - range[0]);
  fn.domain = domain;
  return fn;
}

function ticks(domain, count) {
  const step = (domain[1] - domain[0]) / Math.max(count - 1, 1);
  return Array.from({ length: count }, (_, index) => domain[0] + step * index);
}

function normalize(value, [min, max]) {
  return (value - min) / (max - min || 1);
}

function average(values) {
  const valid = values.filter(Number.isFinite);
  return valid.reduce((sum, value) => sum + value, 0) / valid.length;
}

function fmtRate(value) {
  return Number.isFinite(value) ? value.toFixed(3).replace(/^0/, "") : "-";
}

function fmtTwo(value) {
  return Number.isFinite(value) ? value.toFixed(2) : "-";
}

function fmtOne(value) {
  return Number.isFinite(value) ? value.toFixed(1) : "-";
}

function fmtInt(value) {
  return Number.isFinite(value) ? Math.round(value).toLocaleString("ko-KR") : "-";
}

function formatMetric(metric, value) {
  if (!Number.isFinite(value)) return "-";
  if (["AVG", "ISOP", "GPA", "OBP", "SLG", "OPS", "BABIP", "WPCT", "승률"].includes(metric)) return fmtRate(value);
  if (["ERA", "K/9", "BB/9", "K/BB", "P/G", "P/IP", "GO/AO"].includes(metric)) return fmtTwo(value);
  if (["XR"].includes(metric)) return fmtOne(value);
  return fmtInt(value);
}

function formatCell(column, value) {
  if (value === undefined || value === "") return "-";
  if (typeof value === "number") return formatMetric(column, value);
  return value;
}
