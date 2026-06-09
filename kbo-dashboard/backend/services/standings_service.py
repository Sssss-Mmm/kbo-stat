from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from models import Standing, Team
from utils import current_season


def _standing_to_dict(standing: Standing) -> dict:
    return {
        "season": standing.season,
        "rank": standing.rank,
        "team": standing.team.name,
        "games": standing.games,
        "wins": standing.wins,
        "losses": standing.losses,
        "draws": standing.draws,
        "win_rate": float(standing.win_rate) if standing.win_rate is not None else None,
        "games_behind": float(standing.games_behind) if standing.games_behind is not None else None,
        "last_10_games": standing.last_10_games,
        "streak": standing.streak,
        "home_record": standing.home_record,
        "away_record": standing.away_record,
    }


class StandingsService:
    def get_standings(self, db: Session, season: int = None):
        """현재 시즌 또는 지정된 시즌의 순위표를 조회합니다."""
        season = season or current_season()

        standings = (
            db.query(Standing)
            .options(joinedload(Standing.team))
            .filter(Standing.season == season)
            .order_by(Standing.rank)
            .all()
        )

        if not standings:
            raise HTTPException(status_code=404, detail=f"{season}시즌 순위 데이터가 없습니다.")

        data = [_standing_to_dict(standing) for standing in standings]
        return {"status": "success", "season": season, "count": len(data), "data": data}

    def get_team_standings(self, db: Session, team_name: str, season: int = None):
        """특정 팀의 상세 순위 정보를 조회합니다. (팀명으로 조회)"""
        season = season or current_season()

        standing = (
            db.query(Standing)
            .options(joinedload(Standing.team))
            .join(Team)
            .filter(Standing.season == season, Team.name.ilike(f"%{team_name}%"))
            .first()
        )

        if not standing:
            raise HTTPException(
                status_code=404,
                detail=f"팀 '{team_name}'의 {season}시즌 순위 데이터가 없습니다.",
            )

        return {"status": "success", "data": _standing_to_dict(standing)}
