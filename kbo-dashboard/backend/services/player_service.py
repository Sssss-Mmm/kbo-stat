from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from models import Hitter, Pitcher, Team
from utils import current_season


def _hitter_to_dict(hitter: Hitter) -> dict:
    return {
        "rank": hitter.rank,
        "player_name": hitter.player_name,
        "team": hitter.team.name,
        "avg": float(hitter.avg) if hitter.avg is not None else 0,
        "games": hitter.games,
        "pa": hitter.pa,
        "ab": hitter.ab,
        "hits": hitter.hits,
        "home_runs": hitter.home_runs,
        "rbi": hitter.rbi,
        "sb": hitter.sb,
    }


def _pitcher_to_dict(pitcher: Pitcher) -> dict:
    return {
        "rank": pitcher.rank,
        "player_name": pitcher.player_name,
        "team": pitcher.team.name,
        "wins": pitcher.wins,
        "losses": pitcher.losses,
        "era": float(pitcher.era) if pitcher.era is not None else 0,
        "strikeouts": pitcher.strikeouts,
        "saves": pitcher.saves,
    }


class PlayerService:
    def get_hitters(self, db: Session, season: int = None, limit: int = 50):
        """시즌별 타자 순위를 조회합니다."""
        season = season or current_season()

        hitters = (
            db.query(Hitter)
            .options(joinedload(Hitter.team))
            .filter(Hitter.season == season)
            .order_by(Hitter.rank)
            .limit(limit)
            .all()
        )

        if not hitters:
            raise HTTPException(status_code=404, detail=f"{season}시즌 타자 데이터가 없습니다.")

        data = [_hitter_to_dict(hitter) for hitter in hitters]
        return {"status": "success", "season": season, "count": len(data), "data": data}

    def get_pitchers(self, db: Session, season: int = None, limit: int = 50):
        """시즌별 투수 순위를 조회합니다."""
        season = season or current_season()

        pitchers = (
            db.query(Pitcher)
            .options(joinedload(Pitcher.team))
            .filter(Pitcher.season == season)
            .order_by(Pitcher.rank)
            .limit(limit)
            .all()
        )

        if not pitchers:
            raise HTTPException(status_code=404, detail=f"{season}시즌 투수 데이터가 없습니다.")

        data = [_pitcher_to_dict(pitcher) for pitcher in pitchers]
        return {"status": "success", "season": season, "count": len(data), "data": data}

    def get_player_by_name(self, db: Session, player_name: str, season: int = None):
        """선수명으로 타자/투수를 검색합니다."""
        season = season or current_season()

        hitter = (
            db.query(Hitter)
            .options(joinedload(Hitter.team))
            .filter(Hitter.season == season, Hitter.player_name.ilike(f"%{player_name}%"))
            .first()
        )
        pitcher = (
            db.query(Pitcher)
            .options(joinedload(Pitcher.team))
            .filter(Pitcher.season == season, Pitcher.player_name.ilike(f"%{player_name}%"))
            .first()
        )

        data = {}
        if hitter:
            data["hitter"] = {
                "rank": hitter.rank,
                "player_name": hitter.player_name,
                "team": hitter.team.name,
                "avg": float(hitter.avg) if hitter.avg is not None else 0,
                "games": hitter.games,
                "home_runs": hitter.home_runs,
                "rbi": hitter.rbi,
            }
        if pitcher:
            data["pitcher"] = {
                "rank": pitcher.rank,
                "player_name": pitcher.player_name,
                "team": pitcher.team.name,
                "wins": pitcher.wins,
                "losses": pitcher.losses,
                "era": float(pitcher.era) if pitcher.era is not None else 0,
            }

        if not data:
            raise HTTPException(status_code=404, detail=f"'{player_name}' 선수를 찾을 수 없습니다.")

        return {"status": "success", "data": data}

    def get_team_players(
        self, db: Session, team_name: str, season: int = None, player_type: str = "hitter"
    ):
        """팀별 선수들을 조회합니다."""
        season = season or current_season()

        if player_type == "hitter":
            players = (
                db.query(Hitter)
                .options(joinedload(Hitter.team))
                .join(Team)
                .filter(Hitter.season == season, Team.name.ilike(f"%{team_name}%"))
                .order_by(Hitter.rank)
                .all()
            )
            data = [
                {
                    "rank": player.rank,
                    "player_name": player.player_name,
                    "avg": float(player.avg) if player.avg is not None else 0,
                    "games": player.games,
                    "home_runs": player.home_runs,
                    "rbi": player.rbi,
                }
                for player in players
            ]
        else:
            players = (
                db.query(Pitcher)
                .options(joinedload(Pitcher.team))
                .join(Team)
                .filter(Pitcher.season == season, Team.name.ilike(f"%{team_name}%"))
                .order_by(Pitcher.rank)
                .all()
            )
            data = [
                {
                    "rank": player.rank,
                    "player_name": player.player_name,
                    "wins": player.wins,
                    "losses": player.losses,
                    "era": float(player.era) if player.era is not None else 0,
                }
                for player in players
            ]

        if not data:
            raise HTTPException(
                status_code=404,
                detail=f"팀 '{team_name}'의 {player_type} 데이터가 없습니다.",
            )

        return {
            "status": "success",
            "team": team_name,
            "season": season,
            "player_type": player_type,
            "count": len(data),
            "data": data,
        }
