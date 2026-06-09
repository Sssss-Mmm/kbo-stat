const scheduleState = { season: seasonFromHash(), games: [] };

initSchedule();

async function initSchedule() {
  setActiveNav("schedule");
  renderSeasonSelect(document.getElementById("seasonSelect"), scheduleState.season, async (season) => {
    scheduleState.season = season;
    await loadSchedule();
    renderSchedule();
  });
  await loadSchedule();
  renderSchedule();
}

async function loadSchedule() {
  const text = await fetchDataFile(`kbo_schedule_${scheduleState.season}.csv`);
  scheduleState.games = text ? parseCsv(text).map(normalizeRow) : [];
}

function renderSchedule() {
  const games = [...scheduleState.games].sort((a, b) => `${a.Date} ${a.Time}`.localeCompare(`${b.Date} ${b.Time}`));
  const byDate = new Map();
  games.forEach((game) => {
    if (!byDate.has(game.Date)) byDate.set(game.Date, []);
    byDate.get(game.Date).push(game);
  });
  document.getElementById("scheduleTitle").textContent = `${scheduleState.season} KBO 일정`;
  document.getElementById("scheduleNote").textContent = `${games.length}경기`;
  document.getElementById("scheduleList").innerHTML = [...byDate.entries()]
    .map(([date, rows]) => `
      <article class="vb-date-group">
        <h3>${date} <span>${rows[0]?.Weekday || ""}</span></h3>
        <div>
          ${rows.map(renderGame).join("")}
        </div>
      </article>
    `)
    .join("");
}

function renderGame(game) {
  const hasScore = Number.isFinite(game.away_score) && Number.isFinite(game.home_score);
  const middle = hasScore ? `${fmtNumber(game.away_score)} : ${fmtNumber(game.home_score)}` : (game.Time || "-");
  return `
    <div class="vb-game-row">
      <strong>${game.away_team}</strong>
      <span>${middle}</span>
      <strong>${game.home_team}</strong>
      <small>${game.Ballpark || "-"} · ${game.status || "-"}</small>
    </div>
  `;
}
