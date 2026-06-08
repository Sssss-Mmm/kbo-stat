from sqlalchemy.orm import Session
from models import Hitter, Pitcher, Team
from datetime import datetime


class PlayerService:
    def get_hitters(self, db: Session, season: int = None, limit: int = 50):
        """
        시즌별 타자 순위를 조회합니다.
        """
        if season is None:
            season = datetime.now().year

        try:
            hitters = db.query(Hitter).filter(
                Hitter.season == season
            ).order_by(Hitter.rank).limit(limit).all()

            if not hitters:
                return {
                    "status": "error",
                    "message": f"{season}시즌 타자 데이터가 없습니다."
                }

            data = []
            for hitter in hitters:
                data.append({
                    "rank": hitter.rank,
                    "player_name": hitter.player_name,
                    "team": hitter.team.name,
                    "avg": float(hitter.avg) if hitter.avg else 0,
                    "games": hitter.games,
                    "pa": hitter.pa,
                    "ab": hitter.ab,
                    "hits": hitter.hits,
                    "home_runs": hitter.home_runs,
                    "rbi": hitter.rbi,
                    "sb": hitter.sb
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

    def get_pitchers(self, db: Session, season: int = None, limit: int = 50):
        """
        시즌별 투수 순위를 조회합니다.
        """
        if season is None:
            season = datetime.now().year

        try:
            pitchers = db.query(Pitcher).filter(
                Pitcher.season == season
            ).order_by(Pitcher.rank).limit(limit).all()

            if not pitchers:
                return {
                    "status": "error",
                    "message": f"{season}시즌 투수 데이터가 없습니다."
                }

            data = []
            for pitcher in pitchers:
                data.append({
                    "rank": pitcher.rank,
                    "player_name": pitcher.player_name,
                    "team": pitcher.team.name,
                    "wins": pitcher.wins,
                    "losses": pitcher.losses,
                    "era": float(pitcher.era) if pitcher.era else 0,
                    "strikeouts": pitcher.strikeouts,
                    "saves": pitcher.saves
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

    def get_player_by_name(self, db: Session, player_name: str, season: int = None):
        """
        선수명으로 검색합니다.
        """
        if season is None:
            season = datetime.now().year

        try:
            result = {"status": "success", "data": {}}

            # 타자 검색
            hitter = db.query(Hitter).filter(
                Hitter.season == season,
                Hitter.player_name.ilike(f"%{player_name}%")
            ).first()

            if hitter:
                result["data"]["hitter"] = {
                    "rank": hitter.rank,
                    "player_name": hitter.player_name,
                    "team": hitter.team.name,
                    "avg": float(hitter.avg) if hitter.avg else 0,
                    "games": hitter.games,
                    "home_runs": hitter.home_runs,
                    "rbi": hitter.rbi
                }

            # 투수 검색
            pitcher = db.query(Pitcher).filter(
                Pitcher.season == season,
                Pitcher.player_name.ilike(f"%{player_name}%")
            ).first()

            if pitcher:
                result["data"]["pitcher"] = {
                    "rank": pitcher.rank,
                    "player_name": pitcher.player_name,
                    "team": pitcher.team.name,
                    "wins": pitcher.wins,
                    "losses": pitcher.losses,
                    "era": float(pitcher.era) if pitcher.era else 0
                }

            if not result["data"]:
                return {
                    "status": "error",
                    "message": f"'{player_name}' 선수를 찾을 수 없습니다."
                }

            return result
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }

    def get_team_players(self, db: Session, team_name: str, season: int = None, player_type: str = "hitter"):
        """
        팀별 선수들을 조회합니다.
        """
        if season is None:
            season = datetime.now().year

        try:
            if player_type == "hitter":
                players = db.query(Hitter).join(Team).filter(
                    Hitter.season == season,
                    Team.name.ilike(f"%{team_name}%")
                ).order_by(Hitter.rank).all()

                data = []
                for player in players:
                    data.append({
                        "rank": player.rank,
                        "player_name": player.player_name,
                        "avg": float(player.avg) if player.avg else 0,
                        "games": player.games,
                        "home_runs": player.home_runs,
                        "rbi": player.rbi
                    })
            else:
                players = db.query(Pitcher).join(Team).filter(
                    Pitcher.season == season,
                    Team.name.ilike(f"%{team_name}%")
                ).order_by(Pitcher.rank).all()

                data = []
                for player in players:
                    data.append({
                        "rank": player.rank,
                        "player_name": player.player_name,
                        "wins": player.wins,
                        "losses": player.losses,
                        "era": float(player.era) if player.era else 0
                    })

            if not data:
                return {
                    "status": "error",
                    "message": f"팀 '{team_name}'의 {player_type} 데이터가 없습니다."
                }

            return {
                "status": "success",
                "team": team_name,
                "season": season,
                "player_type": player_type,
                "count": len(data),
                "data": data
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
