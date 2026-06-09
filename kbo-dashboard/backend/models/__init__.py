from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Team(Base):
    """팀 정보"""
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, index=True)  # 팀명 (시즌 무관 고유)

    # 관계설정
    standings = relationship("Standing", back_populates="team")
    schedules = relationship("Schedule", back_populates="home_team", foreign_keys="[Schedule.home_team_id]")

    def __repr__(self):
        return f"<Team {self.name}>"


class Standing(Base):
    """팀 순위"""
    __tablename__ = "standings"

    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, index=True)
    rank = Column(Integer)  # 순위
    team_id = Column(Integer, ForeignKey("teams.id"), index=True)
    games = Column(Integer)  # 경기
    wins = Column(Integer)  # 승
    losses = Column(Integer)  # 패
    draws = Column(Integer)  # 무
    win_rate = Column(Numeric(5, 3))  # 승률
    games_behind = Column(Numeric(5, 1))  # 게임차
    last_10_games = Column(String(100))  # 최근10경기
    streak = Column(String(50))  # 연속
    home_record = Column(String(50))  # 홈
    away_record = Column(String(50))  # 방문
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 관계설정
    team = relationship("Team", back_populates="standings")

    def __repr__(self):
        return f"<Standing {self.season} {self.rank}위>"


class Schedule(Base):
    """경기 일정"""
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, index=True)
    game_date = Column(Date, index=True)  # 경기일
    home_team_id = Column(Integer, ForeignKey("teams.id"))
    away_team_id = Column(Integer, ForeignKey("teams.id"))
    home_score = Column(Integer)  # 홈팀 점수
    away_score = Column(Integer)  # 원정팀 점수
    status = Column(String(20))  # 진행상태 (예정, 진행중, 완료)
    stadium = Column(String(100))  # 경기장
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 관계설정
    home_team = relationship("Team", foreign_keys=[home_team_id])
    away_team = relationship("Team", foreign_keys=[away_team_id])

    def __repr__(self):
        return f"<Schedule {self.game_date}>"


class Hitter(Base):
    """타자 통계"""
    __tablename__ = "hitters"

    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, index=True)
    rank = Column(Integer)  # 순위
    player_name = Column(String(100), index=True)  # 선수명
    team_id = Column(Integer, ForeignKey("teams.id"), index=True)
    avg = Column(Numeric(5, 3))  # 타율
    games = Column(Integer)  # 경기
    pa = Column(Integer)  # 타석
    ab = Column(Integer)  # 타수
    hits = Column(Integer)  # 안타
    doubles = Column(Integer)  # 2루타
    triples = Column(Integer)  # 3루타
    home_runs = Column(Integer)  # 홈런
    rbi = Column(Integer)  # 타점
    sb = Column(Integer)  # 도루
    cs = Column(Integer)  # 도루실
    bb = Column(Integer)  # 볼넷
    hbp = Column(Integer)  # 사구
    so = Column(Integer)  # 삼진
    gdp = Column(Integer)  # 병살
    errors = Column(Integer)  # 오류
    xbh = Column(Integer)  # 장타
    go = Column(Integer)
    ao = Column(Integer)
    go_ao = Column(Numeric(5, 2))  # GO/AO
    gw_rbi = Column(Integer)  # GW RBI
    bb_k = Column(Numeric(5, 2))  # BB/K
    p_pa = Column(Numeric(5, 2))  # P/PA
    isop = Column(Numeric(5, 3))  # ISOP
    xr = Column(Numeric(5, 1))  # XR
    gpa = Column(Numeric(5, 3))  # GPA
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 관계설정
    team = relationship("Team")

    def __repr__(self):
        return f"<Hitter {self.player_name} {self.avg}>"


class Pitcher(Base):
    """투수 통계"""
    __tablename__ = "pitchers"

    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, index=True)
    rank = Column(Integer)  # 순위
    player_name = Column(String(100), index=True)  # 선수명
    team_id = Column(Integer, ForeignKey("teams.id"), index=True)
    # 기본 통계
    games = Column(Integer)  # 경기
    games_started = Column(Integer)  # 선발
    wins = Column(Integer)  # 승
    losses = Column(Integer)  # 패
    saves = Column(Integer)  # 세이브
    holds = Column(Integer)  # 홀드
    era = Column(Numeric(5, 2))  # 평균자책점
    innings_pitched = Column(String(10))  # 이닝 (예: "159 2/3")
    hits_allowed = Column(Integer)  # 피안타
    runs_allowed = Column(Integer)  # 피득점
    earned_runs = Column(Integer)  # 자책점
    walks = Column(Integer)  # 볼넷
    strikeouts = Column(Integer)  # 삼진
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 관계설정
    team = relationship("Team")

    def __repr__(self):
        return f"<Pitcher {self.player_name} {self.era}>"


# ---------------------------------------------------------------------------
# 분석용 도메인 (CSV에서 파생된 비정규 데이터: team 은 FK 대신 팀명 문자열)
# ---------------------------------------------------------------------------


class TeamRankHistory(Base):
    """일자별 팀 순위 스냅샷 (kbo_team_rank_history)"""
    __tablename__ = "team_rank_history"

    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, index=True)
    date = Column(String(20), index=True)  # YYYY-MM-DD
    rank = Column(Integer)
    team = Column(String(50), index=True)
    games = Column(Integer)
    wins = Column(Integer)
    losses = Column(Integer)
    draws = Column(Integer)
    win_rate = Column(Numeric(5, 3))
    games_behind = Column(Numeric(5, 1))
    last_10_games = Column(String(100))
    streak = Column(String(50))
    home_record = Column(String(50))
    away_record = Column(String(50))


class TeamGame(Base):
    """팀별 경기 단위 결과 (kbo_team_games)"""
    __tablename__ = "team_games"

    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, index=True)
    date = Column(String(20))
    month = Column(String(2))
    game_id = Column(String(40))
    team = Column(String(50), index=True)
    opponent = Column(String(50))
    home_away = Column(String(10))
    ballpark = Column(String(50))
    runs_for = Column(Integer)
    runs_against = Column(Integer)
    run_diff = Column(Integer)
    result = Column(String(5))
    win = Column(Integer)
    loss = Column(Integer)
    draw = Column(Integer)


class TeamMonthly(Base):
    """팀별 월간 집계 (kbo_team_monthly)"""
    __tablename__ = "team_monthly"

    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, index=True)
    month = Column(String(2))
    team = Column(String(50), index=True)
    games = Column(Integer)
    wins = Column(Integer)
    losses = Column(Integer)
    draws = Column(Integer)
    runs_for = Column(Integer)
    runs_against = Column(Integer)
    run_diff = Column(Integer)
    win_rate = Column(Numeric(5, 3))


class HitterMetric(Base):
    """타자 파생 지표 OBP/SLG/OPS/WARProxy (kbo_hitter_metrics)"""
    __tablename__ = "hitter_metrics"

    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, index=True)
    rank = Column(Integer)
    player = Column(String(100), index=True)
    team = Column(String(50), index=True)
    pa = Column(Integer)
    avg = Column(Numeric(5, 3))
    obp = Column(Numeric(5, 3))
    slg = Column(Numeric(5, 3))
    hr = Column(Integer)
    rbi = Column(Integer)
    xr = Column(Numeric(6, 1))
    war_proxy = Column(Numeric(6, 3))
    ops = Column(Numeric(5, 3))


class Attendance(Base):
    """팀별 관중 (kbo_attendance, month=0 은 시즌 누계)"""
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, index=True)
    month = Column(Integer, index=True)
    team = Column(String(50), index=True)
    attendance = Column(Integer)
    updated_at = Column(String(40))


class GameTimeTeam(Base):
    """팀별 평균 경기시간 (kbo_game_time_team)"""
    __tablename__ = "game_time_team"

    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, index=True)
    team = Column(String(50), index=True)
    regular_inning_time = Column(String(10))
    regular_inning_minutes = Column(Integer)
    include_extra_time = Column(String(10))
    include_extra_minutes = Column(Integer)


class GameTimeYearly(Base):
    """연도별 평균 경기시간 (kbo_game_time_yearly)"""
    __tablename__ = "game_time_yearly"

    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, index=True)
    type = Column(String(20))
    average_time = Column(String(10))
    average_minutes = Column(Integer)


class ScheduleGame(Base):
    """경기 일정/결과 (kbo_schedule, 비정규 저장 - 팀명 문자열)"""
    __tablename__ = "schedule_games"

    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, index=True)
    date = Column(String(20), index=True)
    weekday = Column(String(5))
    time = Column(String(10))
    away_team = Column(String(50), index=True)
    home_team = Column(String(50), index=True)
    away_score = Column(Integer)
    home_score = Column(Integer)
    status = Column(String(20))
    ballpark = Column(String(50))
    game_id = Column(String(40))
