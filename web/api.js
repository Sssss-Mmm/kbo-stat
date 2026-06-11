// DB 단일화: web 은 정적 CSV 대신 백엔드 API에서 데이터를 가져온다.
// 기존 페이지 로직(parseCsv/normalizeRow)을 그대로 쓰도록, API JSON 을
// CSV 텍스트로 변환해 반환한다. 각 페이지의 fetchDataFile 은 이 함수를 호출.
const API_BASES = [
  `http://${window.location.hostname}:8001/api`,
  "http://127.0.0.1:8001/api",
  "http://localhost:8001/api",
];

// CSV 파일명 -> API 엔드포인트 경로 매핑.
function csvFileToEndpoint(fileName) {
  const match = fileName.match(/_(\d{4})\.csv$/);
  const season = match ? match[1] : "";
  const q = season ? `?season=${season}` : "";

  if (fileName.startsWith("kbo_team_rank_history_")) return `/team-rank-history${q}`;
  if (fileName.startsWith("kbo_team_rank_")) return `/team-rank${q}`;
  if (fileName.startsWith("kbo_team_games_")) return `/team-games${q}`;
  if (fileName.startsWith("kbo_team_monthly_")) return `/team-monthly${q}`;
  if (fileName.startsWith("kbo_hitter_metrics_")) return `/hitter-metrics${q}`;
  if (fileName.startsWith("kbo_schedule_")) return `/schedule-games${q}`;
  if (fileName.startsWith("kbo_pitcher_")) return `/pitchers-raw${q}`;
  if (fileName.startsWith("kbo_attendance_monthly_")) return `/attendance${q}`;
  if (fileName.startsWith("kbo_attendance_")) return `/attendance${q}&month=0`;
  if (fileName.startsWith("kbo_game_time_team_")) return `/game-time/team${q}`;
  if (fileName === "kbo_game_time_yearly.csv") return "/game-time/yearly";
  if (/^kbo_\d{4}\.csv$/.test(fileName)) return `/hitters-raw${q}`; // 타자 원본
  return null;
}

// API 응답(JSON rows)을 기존 parseCsv 가 읽을 수 있는 CSV 텍스트로 변환.
function rowsToCsv(rows) {
  if (!rows || !rows.length) return "";
  const headers = Object.keys(rows[0]);
  const cell = (value) => {
    if (value === null || value === undefined) return "";
    const text = String(value);
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const lines = [headers.join(",")];
  for (const row of rows) {
    lines.push(headers.map((header) => cell(row[header])).join(","));
  }
  return lines.join("\n");
}

function csvRoots(fileName) {
  if (
    fileName.startsWith("kbo_team_games_")
    || fileName.startsWith("kbo_team_monthly_")
    || fileName.startsWith("kbo_hitter_metrics_")
    || fileName.startsWith("kbo_batter_zones_")
    || fileName.startsWith("kbo_pitcher_zones_")
  ) {
    return ["../data/processed", "/data/processed", "/web/data/processed", "./data/processed"];
  }
  if (fileName.startsWith("naver_")) {
    return ["../data/raw/naver", "/data/raw/naver", "/web/data/raw/naver", "./data/raw/naver"];
  }
  return ["../data/raw/kbo_official", "/data/raw/kbo_official", "/web/data/raw/kbo_official", "./data/raw/kbo_official"];
}

async function localFetchCsv(fileName) {
  for (const root of csvRoots(fileName)) {
    try {
      const response = await fetch(`${root}/${fileName}`);
      if (response.ok) return await response.text();
    } catch {
      // 다음 로컬 경로 시도
    }
  }
  return null;
}

// 파일명에 해당하는 API 를 호출해 CSV 텍스트를 반환. 실패 시 null.
async function apiFetchCsv(fileName) {
  const endpoint = csvFileToEndpoint(fileName);
  if (endpoint) {
    for (const base of API_BASES) {
      try {
        const response = await fetch(base + endpoint);
        if (response.ok) {
          const json = await response.json();
          const csv = rowsToCsv(json.data || []);
          if (csv) return csv;
        }
      } catch {
        // 다음 베이스 시도
      }
    }
  }
  return localFetchCsv(fileName);
}
