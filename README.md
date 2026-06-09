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

## Daily Data Update

Fast daily refresh:

```bash
python3 src/update_daily.py --year 2026
```

This updates:

- `data/raw/kbo_official/kbo_team_rank_2026.csv`
- `data/raw/kbo_official/kbo_schedule_2026.csv`
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

Full refresh including current-season hitter and pitcher leaderboards:

```bash
python3 src/update_daily.py --year 2026 --players
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
