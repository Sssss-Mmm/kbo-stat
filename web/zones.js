const zoneState = {
  season: seasonFromHash(),
  role: "batter", // batter | pitcher
  team: "all",
  metric: "hit", // hit | swing
  selectedId: null,
  rows: [],
};

// Diverging scale endpoints: blue (low) -> neutral -> red (high).
const COLOR_LOW = [59, 111, 212];
const COLOR_MID = [242, 244, 246];
const COLOR_HIGH = [216, 64, 58];
// Spread (in rate points) that maps to a full-saturation cell either side of avg.
const METRIC_SPREAD = { hit: 0.25, swing: 0.3 };
// Minimum sample for a cell to be colored (else shown grey).
const MIN_SAMPLE = { hit: 2, swing: 3 };

initZones();

function initZones() {
  setActiveNav("zones");
  renderSeasonSelect(document.getElementById("seasonSelect"), zoneState.season, async (season) => {
    zoneState.season = season;
    zoneState.selectedId = null;
    await loadZones();
    renderAll();
  });

  document.getElementById("roleToggle").addEventListener("click", async (event) => {
    const role = event.target.dataset.role;
    if (!role || role === zoneState.role) return;
    setToggle("roleToggle", "role", role);
    zoneState.role = role;
    zoneState.team = "all";
    zoneState.selectedId = null;
    await loadZones();
    renderAll();
  });

  document.getElementById("metricToggle").addEventListener("click", (event) => {
    const metric = event.target.dataset.metric;
    if (!metric || metric === zoneState.metric) return;
    setToggle("metricToggle", "metric", metric);
    zoneState.metric = metric;
    renderAll();
  });

  document.getElementById("teamSelect").addEventListener("change", (event) => {
    zoneState.team = event.target.value;
    zoneState.selectedId = null;
    renderPlayerList();
    renderHeat();
  });

  loadZones().then(renderAll);
}

function setToggle(groupId, attr, value) {
  document.querySelectorAll(`#${groupId} button`).forEach((button) => {
    button.classList.toggle("active", button.dataset[attr] === value);
  });
}

async function loadZones() {
  const file = zoneState.role === "batter"
    ? `kbo_batter_zones_${zoneState.season}.csv`
    : `kbo_pitcher_zones_${zoneState.season}.csv`;
  const text = await fetchDataFile(file, PROCESSED_ROOTS);
  zoneState.rows = text ? parseCsv(text).map(normalizeRow) : [];
}

// One aggregate per player across all zone cells.
function playerAggregates() {
  const byPlayer = new Map();
  for (const row of zoneState.rows) {
    const id = row.PlayerId;
    if (!byPlayer.has(id)) {
      byPlayer.set(id, { id, name: row.Player, team: row.Team, pitches: 0, inPlay: 0, hits: 0, swings: 0 });
    }
    const agg = byPlayer.get(id);
    agg.pitches += row.Pitches || 0;
    agg.inPlay += row.InPlay || 0;
    agg.hits += row.Hits || 0;
    agg.swings += row.Swings || 0;
  }
  return [...byPlayer.values()];
}

function overallMetric(agg) {
  if (zoneState.metric === "swing") return agg.pitches ? agg.swings / agg.pitches : null;
  return agg.inPlay ? agg.hits / agg.inPlay : null;
}

// League average of the active metric, used as the heatmap midpoint.
function leagueAverage() {
  let num = 0;
  let den = 0;
  for (const row of zoneState.rows) {
    if (zoneState.metric === "swing") {
      num += row.Swings || 0;
      den += row.Pitches || 0;
    } else {
      num += row.Hits || 0;
      den += row.InPlay || 0;
    }
  }
  return den ? num / den : 0;
}

function renderAll() {
  renderTeamSelect();
  renderLabels();
  renderPlayerList();
  renderHeat();
}

function renderLabels() {
  const isBatter = zoneState.role === "batter";
  const metricLabel = zoneState.metric === "swing" ? "스윙률" : (isBatter ? "타율" : "피안타율");
  document.getElementById("listTitle").textContent = isBatter ? "타자" : "투수";
  document.getElementById("listMetricHead").textContent = metricLabel;
  document.getElementById("legendAvg").textContent = `리그 평균 ${fmtRate(leagueAverage())}`;
}

function renderTeamSelect() {
  const teams = [...new Set(zoneState.rows.map((row) => row.Team).filter(Boolean))].sort((a, b) => a.localeCompare(b, "ko"));
  const select = document.getElementById("teamSelect");
  if (!teams.includes(zoneState.team)) zoneState.team = "all";
  select.innerHTML = `<option value="all">전체 구단</option>` + teams.map((team) => `<option value="${team}">${team}</option>`).join("");
  select.value = zoneState.team;
}

function renderPlayerList() {
  const metricLabel = zoneState.metric === "swing" ? "스윙률" : (zoneState.role === "batter" ? "타율" : "피안타율");
  let players = playerAggregates();
  if (zoneState.team !== "all") players = players.filter((agg) => agg.team === zoneState.team);
  players.sort((a, b) => (overallMetric(b) ?? -1) - (overallMetric(a) ?? -1) || b.pitches - a.pitches);

  document.getElementById("listNote").textContent = `${players.length}명 · ${metricLabel} 내림차순`;
  document.getElementById("playerRows").innerHTML = players.map((agg, index) => `
    <tr data-id="${agg.id}" class="${agg.id === zoneState.selectedId ? "selected" : ""}">
      <td>${index + 1}</td>
      <td><strong>${agg.name || "-"}</strong></td>
      <td>${agg.team || "-"}</td>
      <td>${fmtNumber(agg.pitches)}</td>
      <td>${fmtRate(overallMetric(agg))}</td>
    </tr>
  `).join("") || `<tr><td colspan="5" class="zone-note">데이터가 없습니다.</td></tr>`;

  document.querySelectorAll("#playerRows tr[data-id]").forEach((tr) => {
    tr.addEventListener("click", () => {
      zoneState.selectedId = Number(tr.dataset.id);
      renderPlayerList();
      renderHeat();
    });
  });

  if (zoneState.selectedId === null && players.length) {
    zoneState.selectedId = players[0].id;
    renderHeat();
    const first = document.querySelector(`#playerRows tr[data-id="${zoneState.selectedId}"]`);
    if (first) first.classList.add("selected");
  }
}

function lerp(a, b, t) {
  return a.map((channel, index) => Math.round(channel + (b[index] - channel) * t));
}

function cellColor(value, avg) {
  if (value === null) return null;
  const spread = METRIC_SPREAD[zoneState.metric];
  const t = Math.max(-1, Math.min(1, (value - avg) / spread));
  const rgb = t >= 0 ? lerp(COLOR_MID, COLOR_HIGH, t) : lerp(COLOR_MID, COLOR_LOW, -t);
  return `rgb(${rgb.join(",")})`;
}

function renderHeat() {
  const grid = document.getElementById("heatGrid");
  if (zoneState.selectedId === null) {
    grid.innerHTML = "";
    return;
  }
  const rows = zoneState.rows.filter((row) => row.PlayerId === zoneState.selectedId);
  const agg = rows[0];
  const cells = new Map(rows.map((row) => [row.Zone, row]));
  const avg = leagueAverage();
  const minSample = MIN_SAMPLE[zoneState.metric];

  const html = [3, 2, 1].flatMap((r) => [1, 2, 3].map((c) => {
    const cell = cells.get(`${r}-${c}`);
    const pitches = cell ? cell.Pitches || 0 : 0;
    const inPlay = cell ? cell.InPlay || 0 : 0;
    const swings = cell ? cell.Swings || 0 : 0;
    const hits = cell ? cell.Hits || 0 : 0;
    let value = null;
    let sample;
    if (zoneState.metric === "swing") {
      sample = `${swings}/${pitches}`;
      if (pitches >= minSample) value = pitches ? swings / pitches : null;
    } else {
      sample = `${hits}/${inPlay}`;
      if (inPlay >= minSample) value = inPlay ? hits / inPlay : null;
    }
    const color = cellColor(value, avg);
    if (value === null) {
      return `<div class="heat-cell empty"><span class="cell-val">—</span><span class="cell-sub">${pitches}구</span></div>`;
    }
    return `<div class="heat-cell" style="background:${color}"><span class="cell-val">${fmtRate(value)}</span><span class="cell-sub">${sample}</span></div>`;
  })).join("");
  grid.innerHTML = html;

  const metricLabel = zoneState.metric === "swing" ? "스윙률" : (zoneState.role === "batter" ? "타율(인플레이)" : "피안타율(인플레이)");
  document.getElementById("heatTitle").textContent = `${agg.Player} · ${agg.Team}${agg.Side ? ` · ${agg.Side}타` : ""}`;
  document.getElementById("heatNote").textContent = `${metricLabel} · 투수 시점 기준 · 표본 ${minSample}${zoneState.metric === "swing" ? "구" : "타구"} 미만은 회색`;
}
