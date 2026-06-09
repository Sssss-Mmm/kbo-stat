# kbo-stat

AI Baseball Lab prototype for KBO standings, schedule/results, team analysis,
player cards, player comparison, and story-driven baseball analysis.

## Local Web

Run from the repository root:

```bash
python3 -m http.server 8000 --bind 127.0.0.1
```

Open:

```text
http://127.0.0.1:8000/web/index.html
```

Pages:

- `web/index.html`: today's KBO dashboard
- `web/schedule.html`: KBO schedule and results
- `web/standings.html`: league standings board
- `web/batting.html`: hitter leaderboard
- `web/pitching.html`: pitcher leaderboard
- `web/distance.html`: away-game travel proxy
- `web/attendance.html`: KBO official team attendance
- `web/gametime.html`: KBO official average game time
- `web/lab.html`: data-backed AI analyst demo

## RAG Backend

The FastAPI backend exposes a CSV-backed RAG API. It retrieves evidence from:

- `data/raw/kbo_official/kbo_team_rank_2026.csv`
- `data/processed/kbo_team_games_2026.csv`
- `data/processed/kbo_team_monthly_2026.csv`
- `data/processed/kbo_hitter_metrics_2026.csv`

Run the backend from `kbo-dashboard/backend`:

```bash
cd kbo-dashboard/backend
venv/bin/python main.py
```

Backend URL:

```text
http://127.0.0.1:8001
```

When running inside WSL, Windows may need the WSL IP instead of localhost:

```bash
hostname -I | awk '{print $1}'
```

Then open the web page with the same host, for example:

```text
http://<WSL_IP>:8000/web/lab.html
```

Ask endpoint:

```bash
curl -X POST http://127.0.0.1:8001/api/rag/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"왜 LG가 강하지?","season":2026}'
```

Search endpoint:

```bash
curl "http://127.0.0.1:8001/api/rag/search?query=MVP&season=2026"
```

`web/lab.html` calls this backend first and falls back to the local browser-side
demo answer when the backend is not running.

## Docker

Run the full local stack:

```bash
cd kbo-dashboard
docker-compose up -d --build
```

Services:

- Web: `http://127.0.0.1:8000/web/index.html`
- Clean routes: `/schedule`, `/standings`, `/batting`, `/pitching`, `/distance`, `/attendance`, `/gametime`
- AI Lab: `http://127.0.0.1:8000/lab`
- API: `http://127.0.0.1:8001`
- pgAdmin: `http://127.0.0.1:5050`
- PostgreSQL: `127.0.0.1:5433`

If the web page opens but the RAG API does not connect from Windows, use the WSL
IP for both web and API:

```bash
hostname -I | awk '{print $1}'
```

Example:

```text
http://<WSL_IP>:8000/schedule#2026
```

Stop the stack:

```bash
cd kbo-dashboard
docker-compose down
```

## Daily Data Update

Fast daily refresh:

```bash
python3 src/update_daily.py --year 2026
```

This updates:

- `data/raw/kbo_official/kbo_team_rank_2026.csv`
- `data/raw/kbo_official/kbo_schedule_2026.csv`
- `data/raw/kbo_official/kbo_attendance_2026.csv`
- `data/raw/kbo_official/kbo_attendance_monthly_2026.csv`
- `data/raw/kbo_official/kbo_game_time_team_2026.csv`
- `data/raw/kbo_official/kbo_game_time_yearly.csv`
- `data/raw/kbo_official/kbo_team_rank_history_2026.csv`
- `data/raw/kbo_official/team_rank_snapshots/kbo_team_rank_YYYY-MM-DD.csv`
- `data/processed/kbo_team_games_2026.csv`
- `data/processed/kbo_team_monthly_2026.csv`
- `data/processed/kbo_hitter_metrics_2026.csv`

The history file is used by the web dashboard for real rank movement once at
least two daily snapshots exist.

The processed team game files are derived from schedule/results and power
monthly win rate, runs scored/allowed, run differential, and home/away views.
The hitter metrics file adds OBP, SLG, OPS, and WARProxy for player cards,
comparison, and AI answer evidence.

KBO official extras:

```bash
python3 src/crawl_kbo_attendance.py --year 2026
python3 src/crawl_kbo_game_time.py --year 2026
```

Full refresh including current-season hitter and pitcher leaderboards:

```bash
python3 src/update_daily.py --year 2026 --players
```

Load the refreshed CSVs into PostgreSQL in the same run (requires the backend
stack and `kbo-dashboard/backend/.env` `DATABASE_URL`):

```bash
python3 src/update_daily.py --year 2026 --players --db
```

## Cron Example

Run every day at 09:00 KST inside WSL/Linux:

```cron
0 9 * * * cd /home/sssssmmm/kbo-stat && /usr/bin/python3 src/update_daily.py --year 2026 >> logs/daily_update.log 2>&1
```

Create the log directory first:

```bash
mkdir -p logs
```

## Recommended Portfolio Path

Start simple:

- Python crawlers
- CSV files
- Static dashboard
- Daily cron update

Then upgrade:

- Spring Boot scheduler
- PostgreSQL storage
- Redis cache
- Next.js + TypeScript + Tailwind + Recharts frontend
- RAG-backed AI baseball analyst
