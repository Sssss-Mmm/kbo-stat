from sqlalchemy.orm import Session
from models import Standing, Team
from datetime import datetime


class StandingsService:
    def get_standings(self, db: Session, season: int = None):
        """
        현재 시즌 또는 지정된 시즌의 순위표를 조회합니다.
        """
        if season is None:
            season = datetime.now().year

        try:
            standings = db.query(Standing).filter(
                Standing.season == season
            ).order_by(Standing.rank).all()

            if not standings:
                return {
                    "status": "error",
                    "message": f"{season}시즌 순위 데이터가 없습니다."
                }

            # ORM 객체를 딕셔너리로 변환
            data = []
            for standing in standings:
                data.append({
                    "rank": standing.rank,
                    "team": standing.team.name,
                    "games": standing.games,
                    "wins": standing.wins,
                    "losses": standing.losses,
                    "draws": standing.draws,
                    "win_rate": float(standing.win_rate),
                    "games_behind": float(standing.games_behind),
                    "last_10_games": standing.last_10_games,
                    "streak": standing.streak,
                    "home_record": standing.home_record,
                    "away_record": standing.away_record
                })

            return {
                "status": "success",
                "season": season,
                "count": len(data),
                "data": data
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }

    def get_team_standings(self, db: Session, team_name: str, season: int = None):
        """
        특정 팀의 상세 순위 정보를 조회합니다.
        """
        if season is None:
            season = datetime.now().year

        try:
            standing = db.query(Standing).join(Team).filter(
                Standing.season == season,
                Team.name.ilike(f"%{team_name}%")
            ).first()

            if not standing:
                return {
                    "status": "error",
                    "message": f"팀 '{team_name}'의 {season}시즌 순위 데이터가 없습니다."
                }

            return {
                "status": "success",
                "data": {
                    "season": standing.season,
                    "rank": standing.rank,
                    "team": standing.team.name,
                    "games": standing.games,
                    "wins": standing.wins,
                    "losses": standing.losses,
                    "draws": standing.draws,
                    "win_rate": float(standing.win_rate),
                    "games_behind": float(standing.games_behind),
                    "last_10_games": standing.last_10_games,
                    "streak": standing.streak,
                    "home_record": standing.home_record,
                    "away_record": standing.away_record
                }
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
