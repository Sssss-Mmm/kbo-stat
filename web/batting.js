const battingState = { season: seasonFromHash(), sort: "WARProxy", rows: [] };

initBatting();

async function initBatting() {
  setActiveNav("batting");
  renderSeasonSelect(document.getElementById("seasonSelect"), battingState.season, async (season) => {
    battingState.season = season;
    await loadBatting();
    renderBatting();
  });
  document.getElementById("sortSelect").addEventListener("change", (event) => {
    battingState.sort = event.target.value;
    renderBatting();
  });
  await loadBatting();
  renderBatting();
}

async function loadBatting() {
  const text = await fetchDataFile(`kbo_hitter_metrics_${battingState.season}.csv`, PROCESSED_ROOTS)
    || await fetchDataFile(`kbo_${battingState.season}.csv`);
  battingState.rows = text ? parseCsv(text).map(normalizeRow) : [];
}

function renderBatting() {
  const rows = [...battingState.rows].sort((a, b) => (b[battingState.sort] || 0) - (a[battingState.sort] || 0));
  document.getElementById("battingNote").textContent = `${rows.length}명 · ${battingState.sort} 기준`;
  document.getElementById("battingRows").innerHTML = rows.slice(0, 80).map((row, index) => `
    <tr>
      <td>${index + 1}</td>
      <td><strong>${row.Player || row["선수명"] || "-"}</strong></td>
      <td>${row.Team || row["팀명"] || "-"}</td>
      <td>${fmtNumber(row.PA)}</td>
      <td>${fmtRate(row.AVG)}</td>
      <td>${fmtRate(row.OBP)}</td>
      <td>${fmtRate(row.SLG)}</td>
      <td>${fmtRate(row.OPS)}</td>
      <td>${fmtNumber(row.HR)}</td>
      <td>${fmtNumber(row.RBI)}</td>
      <td>${Number.isFinite(row.WARProxy) ? row.WARProxy.toFixed(1) : "-"}</td>
    </tr>
  `).join("");
}
