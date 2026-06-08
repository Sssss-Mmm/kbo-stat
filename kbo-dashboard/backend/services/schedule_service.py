from sqlalchemy.orm import Session
from models import Schedule, Team
from datetime import datetime


class ScheduleService:
    def get_schedule(self, db: Session, season: int = None, team: str = None):
        """
        현재 시즌 또는 지정된 시즌의 경기 일정을 조회합니다.
        """
        if season is None:
            season = datetime.now().year

        try:
            query = db.query(Schedule).filter(Schedule.season == season)
            
            # 팀으로 필터링
            if team:
                query = query.join(Team).filter(
                    (Team.name.ilike(f"%{team}%"))
                )

            schedules = query.order_by(Schedule.game_date).all()

            data = []
            for schedule in schedules:
                data.append({
                    "date": schedule.game_date.isoformat() if schedule.game_date else None,
                    "home_team": schedule.home_team.name,
                    "away_team": schedule.away_team.name,
                    "home_score": schedule.home_score,
                    "away_score": schedule.away_score,
                    "status": schedule.status,
                    "stadium": schedule.stadium
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

    def get_schedule_by_date(self, db: Session, date: str):
        """
        특정 날짜의 경기 일정을 조회합니다.
        """
        try:
            schedules = db.query(Schedule).filter(
                Schedule.game_date == date
            ).all()

            data = []
            for schedule in schedules:
                data.append({
                    "date": schedule.game_date.isoformat() if schedule.game_date else None,
                    "home_team": schedule.home_team.name,
                    "away_team": schedule.away_team.name,
                    "home_score": schedule.home_score,
                    "away_score": schedule.away_score,
                    "status": schedule.status,
                    "stadium": schedule.stadium
                })

            return {
                "status": "success",
                "date": date,
                "count": len(data),
                "data": data
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
