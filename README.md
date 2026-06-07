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
