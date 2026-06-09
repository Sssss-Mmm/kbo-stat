const pitchingState = { season: seasonFromHash(), sort: "ERA", rows: [] };

initPitching();

async function initPitching() {
  setActiveNav("pitching");
  renderSeasonSelect(document.getElementById("seasonSelect"), pitchingState.season, async (season) => {
    pitchingState.season = season;
    await loadPitching();
    renderPitching();
  });
  document.getElementById("sortSelect").addEventListener("change", (event) => {
    pitchingState.sort = event.target.value;
    renderPitching();
  });
  await loadPitching();
  renderPitching();
}

async function loadPitching() {
  const text = await fetchDataFile(`kbo_pitcher_${pitchingState.season}.csv`);
  pitchingState.rows = text ? parseCsv(text).map(normalizeRow) : [];
}

function renderPitching() {
  const lowerIsBetter = ["ERA", "WHIP"].includes(pitchingState.sort);
  const rows = [...pitchingState.rows].sort((a, b) => lowerIsBetter
    ? (a[pitchingState.sort] || 999) - (b[pitchingState.sort] || 999)
    : (b[pitchingState.sort] || 0) - (a[pitchingState.sort] || 0));
  document.getElementById("pitchingNote").textContent = `${rows.length}명 · ${pitchingState.sort} 기준`;
  document.getElementById("pitchingRows").innerHTML = rows.slice(0, 80).map((row, index) => `
    <tr>
      <td>${index + 1}</td>
      <td><strong>${row["선수명"] || "-"}</strong></td>
      <td>${row["팀명"] || "-"}</td>
      <td>${fmtNumber(row.ERA, 2)}</td>
      <td>${fmtNumber(row.G)}</td>
      <td>${fmtNumber(row.W)}</td>
      <td>${fmtNumber(row.L)}</td>
      <td>${fmtNumber(row.SV)}</td>
      <td>${fmtNumber(row.HLD)}</td>
      <td>${row.IP || "-"}</td>
      <td>${fmtNumber(row.SO)}</td>
      <td>${fmtNumber(row.WHIP, 2)}</td>
    </tr>
  `).join("");
}
