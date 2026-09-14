"""Deterministic baseball analysis. No generated SQL, Python or file paths."""
from calendar import monthrange
from datetime import date, timedelta
import json

import pandas as pd

from services.qa_models import AnalysisPlan


class AnalysisUnavailable(ValueError):
    pass


def clean(value):
    # pandas handles numpy scalars and NaN; JSON never contains NaN/Infinity.
    return json.loads(pd.Series([value]).to_json(orient="values", force_ascii=False))[0]


def record(rows):
    if rows.empty:
        return None
    wins, losses, draws = (int(rows[col].sum()) for col in ("Win", "Loss", "Draw"))
    return {
        "games": len(rows), "wins": wins, "losses": losses, "draws": draws,
        "win_rate": round(wins / (wins + losses), 3) if wins + losses else None,
        "runs_per_game": round(float(rows.RunsFor.mean()), 2),
        "allowed_per_game": round(float(rows.RunsAgainst.mean()), 2),
        "run_diff": int((rows.RunsFor - rows.RunsAgainst).sum()),
        "from": rows.Date.min().date().isoformat(), "through": rows.Date.max().date().isoformat(),
    }


def describe(label, stats):
    if stats is None:
        return f"{label}: 수집된 완료 경기가 없습니다."
    rate = f"{stats['win_rate']:.3f}" if stats['win_rate'] is not None else "계산 불가(승패 없음)"
    return (f"{label}: {stats['games']}경기 {stats['wins']}승 {stats['draws']}무 {stats['losses']}패, "
            f"승률 {rate}, 경기당 {stats['runs_per_game']:.2f}득점·{stats['allowed_per_game']:.2f}실점, "
            f"득실차 {stats['run_diff']:+d} ({stats['from']}~{stats['through']}).")


def period_rows(rows, plan, anchor):
    rows = rows.sort_values(["Date", "GameId"] if "GameId" in rows else ["Date"])
    if plan.period == "recent":
        n = plan.recent_games
        return rows.tail(n), rows.iloc[max(0, len(rows) - 2 * n):max(0, len(rows) - n)]
    if plan.period == "all":
        return rows, rows.iloc[:0]
    if plan.period == "month":
        if plan.month is None:
            raise AnalysisUnavailable("몇 월 기록을 비교할지 알려주세요.")
        start = date(plan.season, plan.month, 1)
        end = date(plan.season, plan.month, monthrange(plan.season, plan.month)[1])
        previous_end = start - timedelta(days=1)
        previous_start = previous_end.replace(day=1)
    else:
        try:
            start, end = date.fromisoformat(plan.start_date or ""), date.fromisoformat(plan.end_date or "")
        except ValueError:
            raise AnalysisUnavailable("비교할 시작일과 종료일을 YYYY-MM-DD로 알려주세요.") from None
        if start.year != plan.season or end.year != plan.season or start > end:
            raise AnalysisUnavailable("같은 시즌 안에서 시작일이 종료일보다 앞서야 합니다.")
        previous_end = start - timedelta(days=1)
        previous_start = start - (end - start) - timedelta(days=1)
    selected = rows[rows.Date.between(pd.Timestamp(start), pd.Timestamp(min(end, anchor)))]
    previous = rows[rows.Date.between(pd.Timestamp(previous_start), pd.Timestamp(previous_end))]
    return selected, previous


def analyze(plan: AnalysisPlan, data: dict):
    evidence, notes = [], []

    def add(title, body, source, payload):
        evidence.append({"id": f"E{len(evidence) + 1}", "title": title, "body": body,
                         "source": source, "score": 0, "payload": payload})

    if plan.kind == "player":
        return analyze_players(plan, data, add, evidence, notes)
    games = data["team_games"].copy()
    required = {"Team", "Date", "RunsFor", "RunsAgainst", "Win", "Loss", "Draw"}
    if not required.issubset(games.columns):
        raise AnalysisUnavailable("해당 시즌의 경기별 득실 기록이 없어 추세를 계산할 수 없습니다.")
    games["Date"] = pd.to_datetime(games.Date, errors="coerce")
    games = games.dropna(subset=["Date", "RunsFor", "RunsAgainst", "Win", "Loss", "Draw"])
    games = games[(games.Date.dt.year == plan.season) & ((games.Win + games.Loss + games.Draw) == 1)]
    if games.empty:
        raise AnalysisUnavailable("해당 시즌에 수집된 완료 경기가 없습니다.")
    anchor = games.Date.max().date()
    known_teams = set(games.Team)
    if any(team not in known_teams for team in plan.teams) or (plan.opponent and plan.opponent not in known_teams):
        raise AnalysisUnavailable("요청한 팀의 해당 시즌 경기 기록이 없습니다. 팀명과 시즌을 확인해 주세요.")
    if plan.opponent:
        if "Opponent" not in games:
            raise AnalysisUnavailable("상대 팀별 기록이 수집되지 않았습니다.")
        games = games[games.Opponent == plan.opponent]
    if plan.split != "all" and "HomeAway" not in games:
        raise AnalysisUnavailable("홈·원정 구분 기록이 없습니다.")
    if plan.split in ("home", "away"):
        games = games[games.HomeAway.str.lower() == plan.split]
    teams = plan.teams or sorted(games.Team.unique())
    summaries = []
    for team in teams:
        rows = games[games.Team == team]
        selected, previous = period_rows(rows, plan, anchor)
        stats = record(selected)
        if stats is None:
            notes.append(f"{team}: 요청 기간·조건에 수집된 완료 경기가 없습니다.")
            continue
        summaries.append((team, stats))
        add(f"{team} 조회 기간", describe(team, stats), f"kbo_team_games_{plan.season}.csv",
            {"type": "analysis", "team": team, **stats})
        if stats["games"] < 10:
            notes.append(f"{team}은 {stats['games']}경기 표본으로 장기 실력을 판단하기 어렵습니다.")
        if plan.period == "recent" and stats["games"] < plan.recent_games:
            notes.append(f"{team}: 요청한 최근 {plan.recent_games}경기 중 {stats['games']}경기만 있습니다.")
        if plan.split == "compare":
            for side, label in (("home", "홈"), ("away", "원정")):
                split = record(selected[selected.HomeAway.str.lower() == side])
                if split:
                    add(f"{team} {label}", describe(f"{team} {label}", split), f"kbo_team_games_{plan.season}.csv",
                        {"type": "analysis", "team": team, "split": label, **split})
        # Full-season questions also get recent change, instead of just season totals.
        current = selected
        if plan.period == "all":
            current, previous = period_rows(rows, plan.model_copy(update={"period": "recent"}), anchor)
        now, before = record(current), record(previous)
        if now and before:
            offense = round(now["runs_per_game"] - before["runs_per_game"], 2)
            defense = round(now["allowed_per_game"] - before["allowed_per_game"], 2)
            rate_delta = round(now["win_rate"] - before["win_rate"], 3) if now["win_rate"] is not None and before["win_rate"] is not None else None
            trend = "비교 승률을 계산할 수 없습니다." if rate_delta is None else (
                f"승률은 직전 구간보다 {abs(rate_delta):.3f} {'상승' if rate_delta > 0 else '하락' if rate_delta < 0 else '변동 없음'}했습니다.")
            body = (describe(f"{team} 최근 구간", now) + " " + describe("직전 구간", before) +
                    f" {trend} 경기당 득점 변화 {offense:+.2f}, 실점 변화 {defense:+.2f}입니다.")
            add(f"{team} 이전 구간 대비", body, f"kbo_team_games_{plan.season}.csv",
                {"type": "analysis", "team": team, "current": now, "previous": before,
                 "runs_per_game_change": offense, "allowed_per_game_change": defense, "win_rate_change": rate_delta})
            if min(now["games"], before["games"]) < 10:
                notes.append(f"{team} 전후 비교 표본은 {before['games']}경기와 {now['games']}경기로 작거나 다를 수 있습니다.")
        if plan.teams and plan.period == "all":
            monthly = []
            for month, month_rows in rows.groupby(rows.Date.dt.month):
                monthly.append({"month": int(month), **record(month_rows)})
            add(f"{team} 월별 흐름", " ".join(describe(f"{r['month']}월", r) for r in monthly),
                f"kbo_team_games_{plan.season}.csv", {"type": "analysis", "team": team, "monthly": monthly})
    if not summaries:
        raise AnalysisUnavailable("요청한 기간·조건에 수집된 경기가 없습니다. 다른 기간으로 질문해 주세요.")
    if len(summaries) >= 2:
        ordered = sorted(summaries, key=lambda pair: pair[1]["win_rate"] if pair[1]["win_rate"] is not None else -1, reverse=True)
        body = " / ".join(f"{team}: 승률 {stats['win_rate']}, 경기당 득점 {stats['runs_per_game']}, 실점 {stats['allowed_per_game']} ({stats['games']}경기)" for team, stats in ordered)
        add("같은 조회 조건의 팀 비교", body, f"kbo_team_games_{plan.season}.csv",
            {"type": "analysis", "comparison": [{"team": team, **stats} for team, stats in ordered]})
    if plan.teams and not plan.opponent:
        league_rows = pd.concat([period_rows(rows, plan, anchor)[0] for _, rows in games.groupby("Team")])
        league = record(league_rows)
        if league:
            add("리그 득실 환경", f"같은 조건에서 팀당 경기당 평균 득점은 {league['runs_per_game']:.2f}점, 평균 실점은 {league['allowed_per_game']:.2f}점입니다. 팀 경기 행 {league['games']}개 기준입니다.",
                f"kbo_team_games_{plan.season}.csv", {"type": "analysis", "league_runs_per_game": league["runs_per_game"], "league_allowed_per_game": league["allowed_per_game"], "team_game_rows": league["games"]})
            for team, stats in summaries:
                offense = round(stats['runs_per_game'] - league['runs_per_game'], 2)
                defense = round(stats['allowed_per_game'] - league['allowed_per_game'], 2)
                body = (f"{team}의 경기당 득점은 리그 평균보다 {abs(offense):.2f}점 {'많습니다' if offense > 0 else '적습니다' if offense < 0 else '차이가 없습니다'}. "
                        f"경기당 실점은 리그 평균보다 {abs(defense):.2f}점 {'많습니다' if defense > 0 else '적습니다' if defense < 0 else '차이가 없습니다'}. "
                        "실점은 적을수록 유리합니다. 득점과 실점 자체를 서로 비교해 실점이 높다고 판단하지 않습니다.")
                add(f"{team} 리그 평균 대비", body, f"kbo_team_games_{plan.season}.csv",
                    {"type": "analysis", "team": team, "finding": body})
    standings = data["standings"]
    if plan.period == "all" and plan.teams and {"팀명", "순위", "승", "패", "무", "승률"}.issubset(standings.columns):
        for _, row in standings[standings["팀명"].isin(plan.teams)].iterrows():
            values = {key: clean(row[key]) for key in ("팀명", "순위", "승", "패", "무", "승률")}
            body = " · ".join(f"{key} {value}" for key, value in values.items())
            if values['순위'] is not None and values['순위'] <= 3:
                body += ". 상위 3위 안의 성적입니다. '순위가 낮다'는 질문 전제를 그대로 받아들이면 안 됩니다."
            body += " 수집 시점의 순위이며 시즌 최종 순위라는 의미가 아닙니다."
            add(f"{row['팀명']} 시즌 순위 스냅샷", body,
                f"kbo_team_rank_{plan.season}.csv", {"type": "analysis", "finding": body, **values})
        notes.append("순위표는 별도 수집한 시즌 스냅샷으로 경기별 기록과 갱신 시점이 다를 수 있습니다.")
    notes += [f"최근은 오늘이 아니라 수집된 마지막 경기({anchor.isoformat()}) 기준입니다. 미수집 경기가 있으면 실제 성적과 다를 수 있습니다.",
              "실점은 투구·수비 등을 함께 반영합니다. 기록의 동반 변화만으로 부상·전술·감독 판단을 원인으로 단정할 수 없습니다."]
    return evidence, list(dict.fromkeys(notes)), f"{plan.season}시즌 · {anchor.isoformat()} 경기까지"


def analyze_players(plan, data, add, evidence, notes):
    supported = {"hitter": {"OPS", "AVG", "HR", "RBI", "WAR", "WARProxy", "wRC+"},
                 "pitcher": {"ERA", "WHIP", "SO", "W", "SV", "HLD", "WAR"}}
    if plan.metric not in supported[plan.role]:
        raise AnalysisUnavailable("선수 유형에 맞는 지표를 지정해주세요. 타자는 OPS·WAR, 투수는 ERA·WHIP 등을 비교할 수 있습니다.")
    if plan.period != "all" or plan.split != "all" or plan.opponent:
        raise AnalysisUnavailable("선수 기록은 시즌 누적만 있어 최근·월별·홈원정·상대별 분석은 지원하지 않습니다. 시즌 전체로 비교할까요?")
    source_key = "pitchers" if plan.role == "pitcher" else "batters"
    rows = data.get(source_key, pd.DataFrame()).copy()
    metric = plan.metric
    if rows.empty and plan.role == "hitter":
        rows = data["hitters"].copy()
        source_key = "hitters"
        if metric == "WAR":
            raise AnalysisUnavailable("이 시즌은 공식 제공 WAR가 없습니다. 별도 근사 지표 WARProxy로 조회할 수 있습니다.")
    if metric == "WARProxy":
        rows = data["hitters"].copy()
        source_key = "hitters"
    rows = rows.rename(columns={"선수명": "Player", "팀명": "Team"})
    if rows.empty or not {"Player", "Team", metric}.issubset(rows.columns):
        raise AnalysisUnavailable(f"해당 시즌에 {plan.role} {metric} 기록이 없습니다.")
    if plan.teams:
        rows = rows[rows.Team.isin(plan.teams)]
    if plan.players:
        missing = set(plan.players) - set(rows.Player)
        if missing:
            raise AnalysisUnavailable(f"{', '.join(sorted(missing))}의 해당 시즌·팀 기록을 찾지 못했습니다.")
        rows = rows[rows.Player.isin(plan.players)]
        teams_by_name = rows.groupby("Player").Team.unique()
        ambiguous = {name: teams for name, teams in teams_by_name.items() if len(teams) > 1}
        if ambiguous:
            names = ", ".join(f"{name}({'·'.join(sorted(teams))})" for name, teams in ambiguous.items())
            raise AnalysisUnavailable(f"같은 이름의 선수가 여러 팀에 있습니다: {names}. 팀을 함께 알려주세요.")
    elif plan.qualified_only:
        if "규정충족" in rows:
            rows = rows[rows["규정충족"].astype(str).str.lower().isin(["true", "1"])]
            notes.append("선수 순위는 데이터 제공처의 규정 타석·이닝 충족 표시를 적용했습니다.")
        else:
            raise AnalysisUnavailable("이 시즌에는 규정 충족 정보가 없습니다. '규정 무관' 조건으로 조회할 수 있습니다.")
    else:
        notes.append("규정 타석·이닝 제한 없이 조회했습니다. 적은 표본의 비율 지표에 주의하세요.")
    rows[metric] = pd.to_numeric(rows[metric], errors="coerce")
    rows = rows.dropna(subset=[metric]).sort_values(metric, ascending=metric in ("ERA", "WHIP"))
    if rows.empty:
        raise AnalysisUnavailable("선택한 조건에 해당하는 선수 기록이 없습니다.")
    columns = [c for c in ("Player", "Team", "G", "PA", "IP", "OPS", "AVG", "HR", "RBI", "ERA", "WHIP", "SO", "W", "SV", "HLD", "WAR", "WARProxy", "wRC+") if c in rows]
    source = {"pitchers": "kbo_naver_pitchers", "batters": "kbo_naver_hitters", "hitters": "kbo_hitter_metrics"}[source_key]
    for _, row in rows.head(10).iterrows():
        payload = {key: clean(row[key]) for key in columns}
        metrics = ", ".join(f"{key} {round(value, 3) if isinstance(value, float) else value}" for key, value in payload.items() if key not in ("Player", "Team") and value is not None)
        add(f"{row.Player} ({row.Team})", metrics, f"{source}_{plan.season}.csv", {"type": "analysis", **payload})
    if metric == "WARProxy":
        notes.append("WARProxy는 공식 WAR가 아닌 프로젝트의 근사 지표입니다. MVP 수상 가능성으로 해석하지 않습니다.")
    notes.append("선수 기록은 수집된 시즌 누적 스냅샷입니다. 이 자료만으로 최근 변화나 부상·향후 성적을 판단할 수 없습니다.")
    return evidence, notes, f"{plan.season}시즌 누적 · {metric} {'오름차순' if metric in ('ERA', 'WHIP') else '내림차순'}"
