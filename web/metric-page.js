const metricState = {
  season: seasonFromHash(),
  games: [],
  attendance: [],
  gameTimeTeam: [],
  gameTimeYearly: [],
};
const pageName = location.pathname.includes("attendance")
  ? "attendance"
  : location.pathname.includes("gametime")
    ? "gametime"
    : "distance";

initMetricPage();

async function initMetricPage() {
  setActiveNav(pageName);
  renderSeasonSelect(document.getElementById("seasonSelect"), metricState.season, async (season) => {
    metricState.season = season;
    await loadMetricGames();
    renderMetricRows();
  });
  await loadMetricGames();
  renderMetricRows();
}

async function loadMetricGames() {
  const scheduleText = await fetchDataFile(`kbo_schedule_${metricState.season}.csv`);
  metricState.games = scheduleText ? parseCsv(scheduleText).map(normalizeRow) : [];

  if (pageName === "attendance") {
    const attendanceText = await fetchDataFile(`kbo_attendance_${metricState.season}.csv`);
    metricState.attendance = attendanceText ? parseCsv(attendanceText).map(normalizeRow) : [];
  }

  if (pageName === "gametime") {
    const teamText = await fetchDataFile(`kbo_game_time_team_${metricState.season}.csv`);
    const yearlyText = await fetchDataFile("kbo_game_time_yearly.csv");
    metricState.gameTimeTeam = teamText ? parseCsv(teamText).map(normalizeRow) : [];
    metricState.gameTimeYearly = yearlyText ? parseCsv(yearlyText).map(normalizeRow) : [];
  }
}

function renderMetricRows() {
  if (pageName === "attendance") return renderAttendanceRows();
  if (pageName === "gametime") return renderGametimeRows();
  return renderDistanceRows();
}

function renderDistanceRows() {
  const map = new Map();
  metricState.games.forEach((game) => {
    if (!map.has(game.away_team)) map.set(game.away_team, []);
    map.get(game.away_team).push(game);
  });
  const rows = [...map.entries()].map(([team, games]) => ({
    team,
    count: games.length,
    parks: [...new Set(games.map((game) => game.Ballpark).filter(Boolean))],
  })).sort((a, b) => b.count - a.count);
  document.getElementById("metricRows").innerHTML = rows.map((row, index) => `
    <tr><td>${index + 1}</td><td><strong>${row.team}</strong></td><td>${row.count}</td><td>${row.parks.length}</td><td>${row.parks.slice(0, 6).join(", ")}</td></tr>
  `).join("");
}

function renderAttendanceRows() {
  const map = new Map();
  metricState.games.forEach((game) => {
    if (!map.has(game.home_team)) map.set(game.home_team, []);
    map.get(game.home_team).push(game);
  });
  const rows = metricState.attendance.map((row) => {
    const games = map.get(row.Team) || [];
    return {
      team: row.Team,
      attendance: row.Attendance,
      games: games.length,
      average: games.length ? row.Attendance / games.length : null,
      updatedAt: row.UpdatedAt || "-",
    };
  }).sort((a, b) => b.attendance - a.attendance);
  document.getElementById("metricRows").innerHTML = rows.map((row, index) => `
    <tr>
      <td>${index + 1}</td>
      <td><strong>${row.team}</strong></td>
      <td>${fmtNumber(row.attendance)}</td>
      <td>${row.games || "-"}</td>
      <td>${Number.isFinite(row.average) ? fmtNumber(row.average) : "-"}</td>
      <td>${row.updatedAt}</td>
    </tr>
  `).join("");
}

function renderGametimeRows() {
  const rows = [...metricState.gameTimeTeam].sort((a, b) => b.IncludeExtraMinutes - a.IncludeExtraMinutes);
  document.getElementById("metricRows").innerHTML = rows.map((row, index) => `
    <tr>
      <td>${index + 1}</td>
      <td><strong>${row.Team}</strong></td>
      <td>${row.RegularInningTime}</td>
      <td>${fmtNumber(row.RegularInningMinutes)}</td>
      <td>${row.IncludeExtraTime}</td>
      <td>${fmtNumber(row.IncludeExtraMinutes)}</td>
    </tr>
  `).join("");
  const yearlyRows = [...metricState.gameTimeYearly]
    .filter((row) => row.Season >= 2001)
    .sort((a, b) => b.Season - a.Season || String(a.Type).localeCompare(String(b.Type)))
    .slice(0, 40);
  document.getElementById("yearlyRows").innerHTML = yearlyRows.map((row) => `
    <tr>
      <td>${row.Season}</td>
      <td>${row.Type === "regular" ? "정규이닝" : "연장포함"}</td>
      <td>${row.AverageTime}</td>
      <td>${fmtNumber(row.AverageMinutes)}</td>
    </tr>
  `).join("");
}
