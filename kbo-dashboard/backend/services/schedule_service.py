from sqlalchemy.orm import Session, joinedload

from models import Schedule, Team
from utils import current_season


def _schedule_to_dict(schedule: Schedule) -> dict:
    return {
        "date": schedule.game_date.isoformat() if schedule.game_date else None,
        "home_team": schedule.home_team.name,
        "away_team": schedule.away_team.name,
        "home_score": schedule.home_score,
        "away_score": schedule.away_score,
        "status": schedule.status,
        "stadium": schedule.stadium,
    }


class ScheduleService:
    def get_schedule(self, db: Session, season: int = None, team: str = None):
        """현재 시즌 또는 지정된 시즌의 경기 일정을 조회합니다."""
        season = season or current_season()

        query = (
            db.query(Schedule)
            .options(joinedload(Schedule.home_team), joinedload(Schedule.away_team))
            .filter(Schedule.season == season)
        )
        if team:
            # 홈/원정 어느 쪽이든 해당 팀이 포함된 경기를 조회.
            home = db.query(Team.id).filter(Team.name.ilike(f"%{team}%"))
            query = query.filter(
                (Schedule.home_team_id.in_(home)) | (Schedule.away_team_id.in_(home))
            )

        schedules = query.order_by(Schedule.game_date).all()
        data = [_schedule_to_dict(schedule) for schedule in schedules]
        return {"status": "success", "season": season, "count": len(data), "data": data}

    def get_schedule_by_date(self, db: Session, date: str):
        """특정 날짜의 경기 일정을 조회합니다."""
        schedules = (
            db.query(Schedule)
            .options(joinedload(Schedule.home_team), joinedload(Schedule.away_team))
            .filter(Schedule.game_date == date)
            .all()
        )
        data = [_schedule_to_dict(schedule) for schedule in schedules]
        return {"status": "success", "date": date, "count": len(data), "data": data}
